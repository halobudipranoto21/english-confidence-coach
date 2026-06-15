import anthropic
import requests
import os
import re
import json
import asyncio
import tempfile
import edge_tts
from datetime import datetime

# ── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN       = os.environ["GITHUB_TOKEN"]
GITHUB_REPO        = os.environ["GITHUB_REPO"]  # format: username/repo-name

TTS_VOICE          = "en-US-BrianNeural"
USED_WORDS_FILE    = "used_words.json"

# ── Day Counter ───────────────────────────────────────────────────────────────
def get_day_number():
    start_date = datetime(2026, 6, 4)
    today = datetime.utcnow()
    return (today - start_date).days + 1

# ── GitHub: Read & Write used_words.json ─────────────────────────────────────
def get_github_file():
    """Fetch used_words.json from GitHub repo. Returns (content_dict, sha)."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{USED_WORDS_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers, timeout=15)

    if resp.status_code == 404:
        return {"words": [], "verbs": [], "phrases": []}, None

    resp.raise_for_status()
    data = resp.json()
    import base64
    content = json.loads(base64.b64decode(data["content"]).decode("utf-8"))
    return content, data["sha"]

def save_github_file(content: dict, sha: str):
    """Save updated used_words.json back to GitHub repo."""
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{USED_WORDS_FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    encoded = base64.b64encode(json.dumps(content, indent=2).encode()).decode()

    payload = {
        "message": "Update used words list",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    print("✅ used_words.json updated on GitHub.")

# ── Extract new words from lesson and save ────────────────────────────────────
def extract_and_save_words(lesson_text: str, used_data: dict, sha: str):
    """Parse today's lesson, add new words to used_words.json."""
    verb_match  = re.search(r'(?:🔵.*?Word:|Verb of the Day\s*Word:)\s*(\w+)', lesson_text, re.IGNORECASE)
    word_match  = re.search(r'(?:🟢.*?Word:|Word of the Day\s*Word:)\s*(\w+)', lesson_text, re.IGNORECASE)
    phrase_match = re.search(r'(?:🟡.*?Phrase:|Phrase of the Day\s*Phrase:)\s*([\w\s]+)', lesson_text, re.IGNORECASE)

    if verb_match:
        verb = verb_match.group(1).lower().strip()
        if verb not in used_data["verbs"]:
            used_data["verbs"].append(verb)

    if word_match:
        word = word_match.group(1).lower().strip()
        if word not in used_data["words"]:
            used_data["words"].append(word)

    if phrase_match:
        phrase = phrase_match.group(1).lower().strip()
        if phrase not in used_data["phrases"]:
            used_data["phrases"].append(phrase)

    save_github_file(used_data, sha)

# ── Telegram Senders ──────────────────────────────────────────────────────────
def send_telegram_text(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    print("✅ Text message sent.")

def send_telegram_voice(audio_path: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVoice"
    with open(audio_path, "rb") as audio_file:
        resp = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID},
            files={"voice": ("lesson.mp3", audio_file, "audio/mpeg")},
            timeout=60,
        )
    resp.raise_for_status()
    print("✅ Voice note sent.")

# ── TTS Helpers ───────────────────────────────────────────────────────────────
def extract_vocab_for_tts(lesson_text: str) -> str:
    lines = lesson_text.split("\n")
    tts_lines = []
    in_section = False

    start_markers = ["verb of the day", "word of the day", "phrase of the day", "🔵", "🟢", "🟡"]
    stop_markers  = ["speaking challenge", "active recall", "native speaker", "reminder", "🗣", "✍️", "💡", "⚡"]

    for line in lines:
        line_lower = line.lower()
        if any(m in line_lower for m in start_markers):
            in_section = True
        if in_section and any(m in line_lower for m in stop_markers) and not any(m in line_lower for m in start_markers):
            in_section = False
        if in_section:
            clean = re.sub(r'[🔵🟢🟡📅⚡️✍️🗣💡💬🧠❓📚•]', '', line).strip()
            if clean and not clean.startswith("Day "):
                tts_lines.append(clean)

    result = "\n".join(tts_lines).strip()
    if len(result) < 30:
        result = "Here are today's words. Verb of the day, word of the day, and phrase of the day."
    return result

async def generate_voice(text: str, output_path: str):
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(output_path)

# ── Prompt Builder ────────────────────────────────────────────────────────────
def build_prompt(day: int, used_data: dict) -> str:
    used_verbs   = ", ".join(used_data["verbs"][-60:])   or "none yet"
    used_words   = ", ".join(used_data["words"][-60:])   or "none yet"
    used_phrases = ", ".join(used_data["phrases"][-60:]) or "none yet"

    return f"""
You are an English Confidence Coach for a senior digital strategist and branding professional in Indonesia.

Generate Day {day} of the daily English lesson.

User profile:
- Professional level: intermediate
- Background: 8+ years in digital strategy, branding, marketing
- Goal: build active vocabulary and speaking confidence for ALL situations
- Pain points: limited word recall during speaking, low spontaneous confidence

── WORD SELECTION RULES ──────────────────────────────────────────────────────

Choose words that are:
- Common and frequently used in everyday conversation AND professional settings
- Useful across multiple situations — not limited to one context
- Natural sounding — words a native speaker would use daily

Prioritize words that work naturally in BOTH of these worlds:
1. Daily life: morning routines, travel, eating out, catching up with friends, health, shopping, weekend plans, family
2. Business/marketing/branding: strategy sessions, client meetings, pitching ideas, campaign planning, leadership, brand positioning

AVOID:
- Rare or academic vocabulary
- Words too narrow for only one context
- Industry jargon that doesn't transfer to daily conversation

── ANTI-REPETITION ───────────────────────────────────────────────────────────

Do NOT use any of these already-used words:

Verbs already used: {used_verbs}
Words already used: {used_words}
Phrases already used: {used_phrases}

Pick entirely new words not on any of those lists.

── EXAMPLE RULES ────────────────────────────────────────────────────────────

Each word/phrase must have exactly 2 examples:
- Example 1: daily life situation
- Example 2: business/marketing/branding situation
- Both examples must feel natural and realistic — not forced
- NEVER use school or academic examples

── FORMAT ───────────────────────────────────────────────────────────────────

Use only plain text and emojis. No markdown, no asterisks. Max 350 words.

📅 Day {day} — Daily English

🔵 Verb of the Day
Word: [verb]
Meaning: [one line]
Example 1: [daily life]
Example 2: [business/branding context]
Use it when: [one practical tip for both situations]

🟢 Word of the Day
Word: [noun or adjective]
Meaning: [one line]
Example 1: [daily life]
Example 2: [business/branding context]
Use it when: [one practical tip for both situations]

🟡 Phrase of the Day
Phrase: [phrasal verb or common expression]
Meaning: [one line]
Example 1: [daily life]
Example 2: [business/branding context]
Use it when: [one practical tip for both situations]

🗣 Speaking Challenge (30–60 sec)
One question — alternates between daily life and professional topics across days.

✍️ Active Recall
Write 3 sentences:
1. One using the verb
2. One using the word
3. One using the phrase

💡 Native Speaker Tip
Tulis bagian ini dalam Bahasa Indonesia.
Satu tip singkat tentang penggunaan natural, kesalahan umum, atau alternatif kata.
Maksimal 2 kalimat.

⚡️ Reminder
One short motivational line. Max 10 words.
"""

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    day = get_day_number()

    # Load used words from GitHub
    print("📂 Loading used words from GitHub...")
    used_data, sha = get_github_file()

    # Build prompt with anti-repeat context
    prompt = build_prompt(day, used_data)

    # Generate lesson
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"📘 Generating lesson for Day {day}...")

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    lesson_text = message.content[0].text.strip()

    # Send text lesson
    send_telegram_text(lesson_text)

    # Generate and send voice note
    print("🎙 Generating voice note...")
    vocab_text = extract_vocab_for_tts(lesson_text)
    print(f"TTS text:\n{vocab_text}\n")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        audio_path = tmp.name

    asyncio.run(generate_voice(vocab_text, audio_path))
    send_telegram_voice(audio_path)
    os.unlink(audio_path)
    print("🗑 Temp audio file cleaned up.")

    # Save used words back to GitHub
    extract_and_save_words(lesson_text, used_data, sha)

if __name__ == "__main__":
    main()
