import anthropic
import requests
import os
import re
import asyncio
import tempfile
import edge_tts
from datetime import datetime

# ── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

TTS_VOICE = "en-US-BrianNeural"

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_day_number():
    start_date = datetime(2026, 6, 4)
    today = datetime.utcnow()
    delta = (today - start_date).days + 1
    return delta

def is_friday():
    return datetime.utcnow().weekday() == 4

def is_sunday():
    return datetime.utcnow().weekday() == 6

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

def extract_vocab_for_tts(lesson_text: str) -> str:
    lines = lesson_text.split("\n")
    tts_lines = []
    in_section = False

    start_markers = [
        "verb of the day", "word of the day", "phrase of the day",
        "🔵", "🟢", "🟡"
    ]
    stop_markers = [
        "speaking challenge", "active recall", "native speaker",
        "reminder", "🗣", "✍️", "💡", "⚡"
    ]

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
def build_prompt(day: int) -> str:

    if is_sunday():
        return f"""
You are an English Confidence Coach for a senior digital strategist and branding professional in Indonesia.

Today is Sunday — generate a SUNDAY REFLECTION lesson (Day {day}).

Rules:
- Write entirely in English
- Mix contexts: some words relate to daily life, some to professional situations
- Keep it mobile-friendly: short paragraphs, clear sections, no walls of text
- Use only plain text and emojis for formatting (no markdown, no asterisks)
- Total length: max 300 words

Format exactly like this:

📅 Day {day} — Sunday Reflection

🧠 This Week's Words
List 5 words learned recently (practical verbs or vocabulary). One line each:
• [word] — [one-line meaning]

🗣 Speaking Challenge (2 minutes)
Write ONE open question about the user's week — can be personal or professional. Keep it conversational.

💬 Reflection Prompt
One sentence asking the user to reflect on something they experienced this week, in English.

⚡️ Reminder
One short motivational line. Max 10 words.
"""

    if is_friday():
        return f"""
You are an English Confidence Coach for a senior digital strategist and branding professional in Indonesia.

Today is Friday — generate a WEEKLY REVIEW lesson (Day {day}).

Rules:
- Write entirely in English
- Mix contexts: some quiz sentences relate to daily life, some to professional situations
- Keep it mobile-friendly: short paragraphs, clear sections, no walls of text
- Use only plain text and emojis for formatting (no markdown, no asterisks)
- Total length: max 350 words

Format exactly like this:

📅 Day {day} — Weekly Review

📚 Words This Week
List 5 words (mix of verbs, vocabulary, phrases). One line each:
• [word] — [one-line meaning]

❓ Mini Quiz
Give 3 fill-in-the-blank sentences using words from this week.
Mix the contexts: at least 1 daily life sentence, at least 1 professional sentence.
Answers listed below the sentences.

🗣 Speaking Challenge (1 minute)
One question — can be about daily life or professional life. Keep it easy to answer out loud.

💡 Reflection
One short question asking what the user will practice next week.

⚡️ Reminder
One short motivational line. Max 10 words.
"""

    # Regular daily lesson
    return f"""
You are an English Confidence Coach for a senior digital strategist and branding professional in Indonesia.

Generate Day {day} of the daily English lesson.

User profile:
- Professional level: intermediate
- Background: 8+ years in digital strategy, branding, marketing
- Goal: build active vocabulary and speaking confidence for ALL situations
- Pain points: limited word recall during speaking, low spontaneous confidence

Example context rules — STRICTLY follow this balance:
- Each word or phrase must have exactly 2 examples
- Example 1: always a DAILY LIFE situation (morning routines, travel, eating out, catching up with friends, making decisions, navigating cities, shopping, weekend plans, family, health)
- Example 2: always a PROFESSIONAL situation (strategy, branding, client meetings, pitching, leadership, marketing)
- Alternate which comes first to avoid feeling repetitive over time
- NEVER use school or academic examples

Other rules:
- Write entirely in English
- Keep it mobile-friendly: short paragraphs, clear sections
- Use only plain text and emojis for formatting (no markdown, no asterisks)
- Total length: max 350 words
- Stay practical, never academic

Format exactly like this:

📅 Day {day} — Daily English

🔵 Verb of the Day
Word: [verb]
Meaning: [one line]
Example 1: [daily life context]
Example 2: [professional context]
Use it when: [one practical tip covering both situations]

🟢 Word of the Day
Word: [noun or adjective]
Meaning: [one line]
Example 1: [daily life context]
Example 2: [professional context]
Use it when: [one practical tip covering both situations]

🟡 Phrase of the Day
Phrase: [phrasal verb or expression]
Meaning: [one line]
Example 1: [daily life context]
Example 2: [professional context]
Use it when: [one practical tip covering both situations]

🗣 Speaking Challenge (30–60 sec)
One question that could relate to daily life OR professional life. Easy to answer out loud. Alternate between the two across days.

✍️ Active Recall
Write 3 sentences:
1. One using the verb
2. One using the word
3. One using the phrase

💡 Native Speaker Tip
Tulis bagian ini dalam Bahasa Indonesia.
Satu tip singkat tentang penggunaan natural, kesalahan umum, atau alternatif kata — dari sudut pandang native speaker.
Maksimal 2 kalimat.

⚡️ Reminder
One short motivational line. Max 10 words.
"""

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    day = get_day_number()
    prompt = build_prompt(day)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"📘 Generating lesson for Day {day}...")

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    lesson_text = message.content[0].text.strip()

    # 1. Send text lesson
    send_telegram_text(lesson_text)

    # 2. Generate and send voice note (daily lesson only, not Friday/Sunday)
    if not is_friday() and not is_sunday():
        print("🎙 Generating voice note...")
        vocab_text = extract_vocab_for_tts(lesson_text)
        print(f"TTS text:\n{vocab_text}\n")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            audio_path = tmp.name

        asyncio.run(generate_voice(vocab_text, audio_path))
        send_telegram_voice(audio_path)
        os.unlink(audio_path)
        print("🗑 Temp audio file cleaned up.")

if __name__ == "__main__":
    main()
