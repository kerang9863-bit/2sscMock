import os
import json
import requests
import hashlib
import time
import re
import random
from datetime import datetime
from typing import Optional, Tuple, List

# --- CONFIG ---
PROVIDERS = []

groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
for key in groq_keys:
    PROVIDERS.append({
        "name": "Groq",
        "key": key,
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        "format": "openai"
    })

openrouter_keys = [k.strip() for k in os.getenv("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
for key in openrouter_keys:
    PROVIDERS.append({
        "name": "OpenRouter",
        "key": key,
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "model": "google/gemini-2.0-flash-001",
        "headers": {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com",
            "X-Title": "SSC Quiz Factory"
        },
        "format": "openai"
    })

gemini_keys = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
for key in gemini_keys:
    PROVIDERS.append({
        "name": "Gemini",
        "key": key,
        "url": f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
        "model": "gemini-2.0-flash",
        "headers": {"Content-Type": "application/json"},
        "format": "gemini"
    })

TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RUN_DURATION_SECONDS = 110 * 60

# Prompts tuned for 10+ high quality items
SUBJECTS = {
    "GK_CurrentAffairs": "SSC level GK questions. Focus on Indian history, geography, polity, science, and static GK.",
    "English": "SSC level English questions focusing on Grammar, Vocabulary, Synonyms, Antonyms, or Narration.",
    "Math": "SSC level Arithmetic or Advance Math questions.",
    "Reasoning": "SSC level Verbal or Non-Verbal Reasoning questions requiring logical deduction."
}

# --- UTILITIES ---

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def load_json_safe(filepath: str, default=None):
    if not os.path.exists(filepath):
        return default if default is not None else []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"CORRUPTED {filepath}: {e}")
        backup = f"{filepath}.corrupt.{int(time.time())}"
        os.rename(filepath, backup)
        return default if default is not None else []

def save_json_atomic(filepath: str, data) -> None:
    tmp = f"{filepath}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)

def clean_json_string(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()

def validate_quiz_json(parsed_data) -> bool:
    if not isinstance(parsed_data, list) or len(parsed_data) == 0:
        return False
    for item in parsed_data:
        if not all(k in item for k in ("question", "options", "correct_option_idx", "explanation")):
            return False
        if not isinstance(item["options"], list) or len(item["options"]) != 4:
            return False
        if not isinstance(item["correct_option_idx"], int) or item["correct_option_idx"] >= 4:
            return False
        if len(item["question"]) > 300 or len(item["explanation"]) > 200:
            return False
    return True

# --- CORE LOGIC ---

def fetch_quiz_data(subject: str, prompt_detail: str, provider_idx: int, retries: int = 3) -> Tuple[Optional[List[dict]], bool]:
    if provider_idx >= len(PROVIDERS):
        return None, True

    provider = PROVIDERS[provider_idx]
    log(f"Provider: {provider['name']} | Subject: {subject}")

    # Forcing exactly 10 questions inside a structured json format
    full_prompt = (
        f"Generate exactly 10 completely unique {prompt_detail}\n\n"
        "STRICT SYSTEM OUTPUT FORMAT RULES:\n"
        "Return ONLY a raw valid JSON array containing objects with these exact keys. No markdown, no wrappers.\n"
        "[\n"
        "  {\n"
        "    \"question\": \"Question text (Max 300 chars, NO markdown like **)\",\n"
        "    \"options\": [\"Option A\", \"Option B\", \"Option C\", \"Option D\"],\n"
        "    \"correct_option_idx\": 0, (Integer index of the correct answer, 0 to 3)\n"
        "    \"explanation\": \"Short trick or explanation formula. (CRITICAL: MUST BE UNDER 200 CHARACTERS TOTAL)\"\n"
        "  }\n"
        "]"
    )

    for attempt in range(retries):
        try:
            if provider["format"] == "gemini":
                data = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {"temperature": 0.5, "responseMimeType": "application/json"}
                }
            else:
                data = {
                    "model": provider["model"],
                    "messages": [{"role": "user", "content": full_prompt}],
                    "temperature": 0.5,
                    "response_format": {"type": "json_object"} if "groq" in provider["url"] else None
                }

            res = requests.post(provider["url"], headers=provider["headers"], json=data, timeout=50)
            if res.status_code in [429, 402]:
                return None, True
            if res.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            if not res.ok:
                return None, False

            payload = res.json()
            raw_content = payload["candidates"][0]["content"]["parts"][0]["text"] if provider["format"] == "gemini" else payload["choices"][0]["message"]["content"]
            
            cleaned_content = clean_json_string(raw_content)
            parsed_json = json.loads(cleaned_content)

            if isinstance(parsed_json, dict) and "questions" in parsed_json:
                parsed_json = parsed_json["questions"]

            if validate_quiz_json(parsed_json):
                return parsed_json, False
            else:
                log(f"Validation schema failure on attempt {attempt+1}. Retrying...")
                time.sleep(2)
        except Exception as e:
            log(f"Error parsing data: {e}")
            time.sleep(2)

    return None, False

def build_and_send_txt_file(quiz_data: List[dict], subject: str) -> Optional[str]:
    """Generates a clean date-stamped text file for organized static study."""
    date_str = datetime.now().strftime("%d_%b_%Y")
    filename = f"{subject}_{date_str}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"=== SSC MTS {subject.upper()} STUDY SET - {datetime.now().strftime('%d %b %Y')} ===\n\n")
        for idx, item in enumerate(quiz_data):
            f.write(f"Q{idx+1}: {item['question']}\n")
            for o_idx, opt in enumerate(item['options']):
                prefix = ["A", "B", "C", "D"][o_idx]
                f.write(f"  {prefix}) {opt}\n")
            correct_letter = ["A", "B", "C", "D"][item['correct_option_idx']]
            f.write(f"CORRECT ANSWER: {correct_letter}) {item['options'][item['correct_option_idx']]}\n")
            f.write(f"EXPLANATION: {item['explanation']}\n")
            f.write("-" * 40 + "\n\n")
            
    # Send document to Telegram
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TG_TOKEN}/sendDocument"
    try:
        with open(filename, "rb") as doc:
            resp = requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": f"📖 {subject} Study Material ({datetime.now().strftime('%d %b %Y')})"}, files={"document": doc}, timeout=30)
            return filename if resp.ok else None
    except Exception as e:
        log(f"Failed sending study file: {e}")
        return None

def send_shuffled_quiz_to_telegram(quiz_item: dict) -> bool:
    """Shuffles options dynamically to maximize confusion and prevent layout dependency."""
    original_options = list(quiz_item["options"])
    correct_content = original_options[quiz_item["correct_option_idx"]]
    
    # Shuffle options list right before packing payload
    shuffled_options = list(original_options)
    random.shuffle(shuffled_options)
    new_correct_idx = shuffled_options.index(correct_content)

    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){TG_TOKEN}/sendPoll"
    payload = {
        "chat_id": TG_CHAT_ID,
        "question": quiz_item["question"],
        "options": json.dumps(shuffled_options),
        "is_anonymous": True,
        "type": "quiz",
        "correct_option_id": new_correct_idx,
        "explanation": quiz_item["explanation"]
    }

    try:
        resp = requests.post(url, json=payload, timeout=20)
        return resp.ok
    except Exception as e:
        log(f"Connection error deploying quiz: {e}")
        return False

# --- MAIN ENGINE ---

if __name__ == "__main__":
    start_time = time.time()
    provider_idx = 0
    memory = load_json_safe("global_memory.json")

    if not PROVIDERS:
        log("FATAL: Providers configured nahi hain.")
        exit(1)

    log(f"Starting Shuffled Quiz Factory with {len(PROVIDERS)} keys.")

    for subject, prompt_detail in SUBJECTS.items():
        if (time.time() - start_time) > RUN_DURATION_SECONDS:
            break
        if provider_idx >= len(PROVIDERS):
            break

        log(f"\nRunning 10-Question Engine for: {subject}")
        quiz_data, rotate = fetch_quiz_data(subject, prompt_detail, provider_idx)

        if rotate:
            provider_idx += 1
            continue
        if not quiz_data:
            continue

        valid_new_quizzes = []
        for item in quiz_data:
            q_hash = hashlib.md5(item["question"].encode()).hexdigest()
            if q_hash in memory:
                continue
            valid_new_quizzes.append(item)
            memory.append(q_hash)

        if len(valid_new_quizzes) >= 5:  # Ensure we have a decent sized dataset to send
            # Step 1: Send clean .txt file first
            txt_file = build_and_send_txt_file(valid_new_quizzes, subject)
            
            if txt_file:
                log(f"Txt file {txt_file} sent. Initiating confusing mock test poll stream...")
                # Step 2: Send interactive quiz stream with options shuffled
                for idx, quiz in enumerate(valid_new_quizzes):
                    send_shuffled_quiz_to_telegram(quiz)
                    time.sleep(3) # Anti flood delay mitigation
                    
            with open("ssc_question_db.json", "w") as f: # standard basic history logging
                json.dump(valid_new_quizzes, f, default=str)
            save_json_atomic("global_memory.json", memory[-30000:])
        else:
            log("Not enough unique questions generated in this cycle.")

    save_json_atomic("global_memory.json", memory[-30000:])
    log("\nAll workflows completed cleanly!")
