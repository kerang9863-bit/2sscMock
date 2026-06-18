import os
import json
import requests
import hashlib
import time
import random
import html as html_module
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Set
from dataclasses import dataclass
from enum import Enum
import threading

# ═══════════════════════════════════════════════════════════════════════════════
#  SSC MTS QUIZ FACTORY PRO — v3.0
#  Professional Grade | Production Ready | Fully Upgraded
# ═══════════════════════════════════════════════════════════════════════════════

class LogLevel(Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"

@dataclass
class ProviderConfig:
    name: str
    key: str
    url: str
    model: str
    headers: dict
    format: str
    weight: int = 1
    fail_count: int = 0

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class ConfigManager:
    RUN_DURATION_SECONDS = 110 * 60
    MAX_QUESTIONS_PER_BATCH = 10
    MIN_UNIQUE_THRESHOLD = 5
    MEMORY_LIMIT = 30000
    DB_LIMIT = 10000
    MAX_RETRIES = 3
    REQUEST_TIMEOUT = 50
    TELEGRAM_TIMEOUT = 30

    SUBJECTS = {
        "GK_CurrentAffairs": {
            "description": "SSC level GK questions. Focus on Indian history, geography, polity, science, and static GK.",
            "icon": "🌍"
        },
        "English": {
            "description": "SSC level English questions focusing on Grammar, Vocabulary, Synonyms, Antonyms, or Narration.",
            "icon": "📚"
        },
        "Math": {
            "description": "SSC level Arithmetic or Advance Math questions.",
            "icon": "🔢"
        },
        "Reasoning": {
            "description": "SSC level Verbal or Non-Verbal Reasoning questions requiring logical deduction.",
            "icon": "🧩"
        }
    }

    @classmethod
    def load_providers(cls) -> List[ProviderConfig]:
        providers = []

        groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
        for idx, key in enumerate(groq_keys):
            providers.append(ProviderConfig(
                name=f"Groq-{idx+1}",
                key=key,
                url="https://api.groq.com/openai/v1/chat/completions",
                model="llama-3.3-70b-versatile",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                format="openai",
                weight=2
            ))

        openrouter_keys = [k.strip() for k in os.getenv("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
        for idx, key in enumerate(openrouter_keys):
            providers.append(ProviderConfig(
                name=f"OpenRouter-{idx+1}",
                key=key,
                url="https://openrouter.ai/api/v1/chat/completions",
                model="google/gemini-2.0-flash-001",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "SSC HTML Factory Pro"
                },
                format="openai",
                weight=2
            ))

        gemini_keys = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
        for idx, key in enumerate(gemini_keys):
            providers.append(ProviderConfig(
                name=f"Gemini-{idx+1}",
                key=key,
                url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                model="gemini-2.0-flash",
                headers={"Content-Type": "application/json"},
                format="gemini",
                weight=3
            ))

        return providers

# ═══════════════════════════════════════════════════════════════════════════════
#  LOGGING & TELEMETRY
# ═══════════════════════════════════════════════════════════════════════════════

class Logger:
    COLORS = {
        LogLevel.INFO: "\033[36m",
        LogLevel.SUCCESS: "\033[32m",
        LogLevel.WARNING: "\033[33m",
        LogLevel.ERROR: "\033[31m",
        LogLevel.FATAL: "\033[35m"
    }
    RESET = "\033[0m"

    @classmethod
    def log(cls, msg: str, level: LogLevel = LogLevel.INFO, subject: str = "") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = f"[{timestamp}]"
        color = cls.COLORS.get(level, "")
        subject_tag = f" [{subject}]" if subject else ""
        output = f"{color}{prefix}{subject_tag} [{level.value}] {msg}{cls.RESET}"
        print(output, flush=True)
        with open("factory.log", "a", encoding="utf-8") as f:
            f.write(f"{prefix}{subject_tag} [{level.value}] {msg}\n")

    @classmethod
    def info(cls, msg: str, subject: str = ""): cls.log(msg, LogLevel.INFO, subject)
    @classmethod
    def success(cls, msg: str, subject: str = ""): cls.log(msg, LogLevel.SUCCESS, subject)
    @classmethod
    def warning(cls, msg: str, subject: str = ""): cls.log(msg, LogLevel.WARNING, subject)
    @classmethod
    def error(cls, msg: str, subject: str = ""): cls.log(msg, LogLevel.ERROR, subject)
    @classmethod
    def fatal(cls, msg: str, subject: str = ""): cls.log(msg, LogLevel.FATAL, subject)

# ═══════════════════════════════════════════════════════════════════════════════
#  DATA PERSISTENCE LAYER
# ═══════════════════════════════════════════════════════════════════════════════

class AtomicJSONStore:
    _locks: Dict[str, threading.Lock] = {}

    @classmethod
    def _get_lock(cls, filepath: str) -> threading.Lock:
        if filepath not in cls._locks:
            cls._locks[filepath] = threading.Lock()
        return cls._locks[filepath]

    @classmethod
    def load(cls, filepath: str, default=None):
        with cls._get_lock(filepath):
            if not os.path.exists(filepath):
                return default if default is not None else []
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                Logger.error(f"CORRUPTED {filepath}: {e}")
                backup = f"{filepath}.corrupt.{int(time.time())}"
                try:
                    os.rename(filepath, backup)
                except Exception:
                    pass
                return default if default is not None else []

    @classmethod
    def save(cls, filepath: str, data) -> None:
        with cls._get_lock(filepath):
            tmp = f"{filepath}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, filepath)

class MemoryManager:
    def __init__(self, filepath: str = "global_memory.json", limit: int = 30000):
        self.filepath = filepath
        self.limit = limit
        raw = AtomicJSONStore.load(filepath, [])
        self._memory_set: Set[str] = set(raw)
        self._memory_list: List[str] = list(self._memory_set)

    def exists(self, q_hash: str) -> bool:
        return q_hash in self._memory_set

    def add(self, q_hash: str) -> None:
        if q_hash not in self._memory_set:
            self._memory_set.add(q_hash)
            self._memory_list.append(q_hash)

    def save(self) -> None:
        trimmed = self._memory_list[-self.limit:]
        AtomicJSONStore.save(self.filepath, trimmed)
        self._memory_set = set(trimmed)
        self._memory_list = trimmed

class QuestionDatabase:
    def __init__(self, filepath: str = "ssc_question_db.json", limit: int = 10000):
        self.filepath = filepath
        self.limit = limit

    def append(self, entries: List[dict]) -> None:
        db = AtomicJSONStore.load(self.filepath, [])
        db.extend(entries)
        AtomicJSONStore.save(self.filepath, db[-self.limit:])

# ═══════════════════════════════════════════════════════════════════════════════
#  AI PROVIDER ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderEngine:
    def __init__(self, providers: List[ProviderConfig]):
        self.providers = providers
        self.current_idx = 0
        self.health_status = {p.name: {"healthy": True, "consecutive_fails": 0} for p in providers}

    def get_next_provider(self) -> Optional[ProviderConfig]:
        attempts = 0
        while attempts < len(self.providers):
            provider = self.providers[self.current_idx]
            self.current_idx = (self.current_idx + 1) % len(self.providers)
            if self.health_status[provider.name]["healthy"]:
                return provider
            attempts += 1
        Logger.warning("All providers marked unhealthy. Resetting health status.")
        for name in self.health_status:
            self.health_status[name]["healthy"] = True
            self.health_status[name]["consecutive_fails"] = 0
        return self.providers[0] if self.providers else None

    def report_success(self, provider: ProviderConfig) -> None:
        self.health_status[provider.name]["consecutive_fails"] = 0
        self.health_status[provider.name]["healthy"] = True

    def report_failure(self, provider: ProviderConfig) -> None:
        self.health_status[provider.name]["consecutive_fails"] += 1
        if self.health_status[provider.name]["consecutive_fails"] >= 3:
            self.health_status[provider.name]["healthy"] = False
            Logger.error(f"Provider {provider.name} marked unhealthy after 3 consecutive failures")

    def build_prompt(self, subject: str, prompt_detail: str, count: int = 10) -> str:
        return (
            f"Generate exactly {count} completely unique {prompt_detail}\n\n"
            "STRICT SYSTEM OUTPUT FORMAT RULES:\n"
            "Return ONLY a raw valid JSON array. No markdown, no code blocks, no wrappers, no explanations outside JSON.\n"
            "Each object MUST have these exact keys:\n"
            "[\n"
            "  {\n"
            '    "question": "Clear question text (NO markdown bold **, use plain text)",\n'
            '    "options": ["Option A", "Option B", "Option C", "Option D"],\n'
            '    "correct_option_idx": 0,  // Integer 0-3\n'
            '    "explanation": "Detailed solution with short-trick or formula if applicable"\n'
            "  }\n"
            "]\n\n"
            "REQUIREMENTS:\n"
            "- All questions must be factually accurate and SSC MTS exam level\n"
            "- Options must be plausible distractors, not obviously wrong\n"
            "- Explanations should teach the concept, not just state the answer\n"
            "- Use standard Unicode characters only"
        )

    def fetch_quiz(self, subject: str, prompt_detail: str, retries: int = 3) -> Tuple[Optional[List[dict]], bool]:
        provider = self.get_next_provider()
        if not provider:
            Logger.fatal("No providers available")
            return None, True

        Logger.info(f"Using provider: {provider.name} | Subject: {subject}", subject)
        full_prompt = self.build_prompt(subject, prompt_detail)

        for attempt in range(retries):
            try:
                if provider.format == "gemini":
                    data = {
                        "contents": [{"parts": [{"text": full_prompt}]}],
                        "generationConfig": {
                            "temperature": 0.4,
                            "responseMimeType": "application/json",
                            "maxOutputTokens": 8192
                        }
                    }
                else:
                    data = {
                        "model": provider.model,
                        "messages": [
                            {"role": "system", "content": "You are a professional SSC exam question generator. Always output valid JSON arrays only."},
                            {"role": "user", "content": full_prompt}
                        ],
                        "temperature": 0.4,
                        "max_tokens": 4096
                    }
                    if "groq" in provider.url:
                        data["response_format"] = {"type": "json_object"}

                res = requests.post(
                    provider.url,
                    headers=provider.headers,
                    json=data,
                    timeout=ConfigManager.REQUEST_TIMEOUT
                )

                if res.status_code == 429:
                    Logger.warning(f"Rate limited on {provider.name}", subject)
                    self.report_failure(provider, is_rate_limit=True)
                    return None, True

                if res.status_code == 402:
                    Logger.error(f"Payment required on {provider.name}", subject)
                    self.report_failure(provider)
                    return None, True

                if res.status_code >= 500:
                    Logger.warning(f"Server error {res.status_code} on {provider.name}, retrying...", subject)
                    time.sleep(2 ** attempt)
                    continue

                if not res.ok:
                    Logger.error(f"HTTP {res.status_code} from {provider.name}: {res.text[:200]}", subject)
                    self.report_failure(provider)
                    return None, False

                payload = res.json()

                if provider.format == "gemini":
                    raw_content = payload["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    raw_content = payload["choices"][0]["message"]["content"]

                cleaned = self._clean_json_string(raw_content)
                parsed = json.loads(cleaned)

                if isinstance(parsed, dict) and "questions" in parsed:
                    parsed = parsed["questions"]

                if self._validate_quiz_json(parsed):
                    self.report_success(provider)
                    Logger.success(f"Generated {len(parsed)} valid questions via {provider.name}", subject)
                    return parsed, False
                else:
                    Logger.warning(f"Invalid quiz structure from {provider.name}, retrying...", subject)
                    time.sleep(2)

            except json.JSONDecodeError as e:
                Logger.error(f"JSON parse error: {e}", subject)
                time.sleep(2)
            except requests.exceptions.Timeout:
                Logger.warning(f"Timeout on {provider.name}, retrying...", subject)
                time.sleep(2 ** attempt)
            except Exception as e:
                Logger.error(f"Unexpected error: {e}", subject)
                time.sleep(2)

        self.report_failure(provider)
        return None, False

    def _clean_json_string(self, raw_text: str) -> str:
        cleaned = raw_text.strip()
        for prefix in ["```json", "```JSON", "```"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("\ufeff"):
            cleaned = cleaned[1:]
        return cleaned

    def _validate_quiz_json(self, parsed_data) -> bool:
        if not isinstance(parsed_data, list) or len(parsed_data) == 0:
            return False
        for item in parsed_data:
            if not all(k in item for k in ("question", "options", "correct_option_idx", "explanation")):
                return False
            if not isinstance(item["options"], list) or len(item["options"]) != 4:
                return False
            if not isinstance(item["correct_option_idx"], int) or not (0 <= item["correct_option_idx"] <= 3):
                return False
            if not isinstance(item["question"], str) or len(item["question"].strip()) < 10:
                return False
        return True

# ═══════════════════════════════════════════════════════════════════════════════
#  TELEGRAM DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════

class TelegramDispatcher:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_document(self, filepath: str, caption: str, retries: int = 2) -> bool:
        url = f"{self.base_url}/sendDocument"
        for attempt in range(retries + 1):
            try:
                with open(filepath, "rb") as doc:
                    resp = requests.post(
                        url,
                        data={"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"},
                        files={"document": doc},
                        timeout=ConfigManager.TELEGRAM_TIMEOUT
                    )
                if resp.ok:
                    Logger.success(f"Sent {os.path.basename(filepath)} to Telegram")
                    return True
                else:
                    Logger.error(f"Telegram API error: {resp.status_code} - {resp.text[:200]}")
                    if attempt < retries:
                        time.sleep(2 ** attempt)
            except Exception as e:
                Logger.error(f"Failed sending document: {e}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
        return False

# ═══════════════════════════════════════════════════════════════════════════════
#  CONTENT GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════

class TextStudyGenerator:
    @staticmethod
    def generate(quiz_data: List[dict], subject: str) -> Optional[str]:
        date_str = datetime.now().strftime("%d_%b_%Y")
        filename = f"{subject}_{date_str}.txt"

        lines = [
            "=" * 70,
            f"  SSC MTS {subject.upper()} STUDY SET",
            f"  Generated: {datetime.now().strftime('%d %B %Y at %I:%M %p')}",
            f"  Questions: {len(quiz_data)}",
            "=" * 70,
            ""
        ]

        for idx, item in enumerate(quiz_data):
            correct_letter = ["A", "B", "C", "D"][item["correct_option_idx"]]
            correct_text = item["options"][item["correct_option_idx"]]
            lines.extend([
                f"Q{idx+1}. {item['question']}",
                ""
            ])
            for o_idx, opt in enumerate(item["options"]):
                lines.append(f"   ({['A', 'B', 'C', 'D'][o_idx]}) {opt}")
            lines.extend([
                "",
                f"   ✓ CORRECT ANSWER: ({correct_letter}) {correct_text}",
                "",
                f"   📖 EXPLANATION: {item['explanation']}",
                "",
                "─" * 70,
                ""
            ])

        lines.extend(["", "=" * 70, "  END OF STUDY SET — Keep Practicing! 💪", "=" * 70])

        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filename

class HTMLMockTestGenerator:
    @staticmethod
    def generate(quiz_data: List[dict], subject: str) -> Optional[str]:
        date_str = datetime.now().strftime("%d_%b_%Y")
        filename = f"{subject}_MOCK_TEST_{date_str}.html"

        shuffled_questions = []
        for item in quiz_data:
            opts = list(item["options"])
            correct_content = opts[item["correct_option_idx"]]
            random.shuffle(opts)
            shuffled_questions.append({
                "question": html_module.escape(item["question"]),
                "options": [html_module.escape(opt) for opt in opts],
                "correct_idx": opts.index(correct_content),
                "explanation": html_module.escape(item["explanation"])
            })

        total_questions = len(shuffled_questions)

        # Build nav buttons
        nav_buttons = ""
        for i in range(total_questions):
            nav_buttons += f'                <button class="nav-btn" id="nav_{i}" onclick="scrollToQuestion({i})">{i+1}</button>\n'

        # Build question cards
        question_cards = ""
        for idx, q in enumerate(shuffled_questions):
            options_html = ""
            for o_idx, opt in enumerate(q["options"]):
                options_html += f"""
                    <label class="option-label" id="label_{idx}_{o_idx}" onclick="selectOption({idx}, {o_idx})">
                        <input type="radio" name="question_{idx}" value="{o_idx}" onchange="onOptionChange({idx}, {o_idx})">
                        <span class="option-letter">{chr(65+o_idx)}</span>
                        <span class="option-text">{opt}</span>
                    </label>"""

            question_cards += f"""
            <div class="q-card" id="q_box_{idx}" data-status="unattempted">
                <div class="q-header">
                    <span class="q-number">QUESTION {idx+1}</span>
                    <span class="q-status" id="status_{idx}">Not answered</span>
                </div>
                <div class="q-text">{q['question']}</div>
                <input type="hidden" id="ans_key_{idx}" value="{q['correct_idx']}">
                <div class="options-grid">
                    {options_html}
                </div>
                <div class="explanation-box" id="exp_{idx}">
                    <div class="exp-header">📖 Explanation & Short-Trick</div>
                    <div class="exp-text">{q['explanation']}</div>
                </div>
            </div>"""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>SSC MTS {subject.upper()} — Professional Mock Test</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{ --primary: #1a365d; --primary-light: #2c5282; --accent: #dd6b20; --accent-light: #ed8936; --success: #276749; --success-bg: #c6f6d5; --error: #c53030; --error-bg: #fed7d7; --warning: #c05621; --warning-bg: #feebc8; --bg: #f7fafc; --surface: #ffffff; --text: #1a202c; --text-secondary: #4a5568; --border: #e2e8f0; --shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); --shadow-lg: 0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04); --radius: 12px; --radius-sm: 8px; }}
        [data-theme="dark"] {{ --primary: #63b3ed; --primary-light: #4299e1; --accent: #f6ad55; --accent-light: #fbd38d; --success: #68d391; --success-bg: #22543d; --error: #fc8181; --error-bg: #742a2a; --warning: #fbd38d; --warning-bg: #744210; --bg: #0d1117; --surface: #161b22; --text: #e2e8f0; --text-secondary: #a0aec0; --border: #30363d; --shadow: 0 4px 6px -1px rgba(0,0,0,0.3); --shadow-lg: 0 20px 25px -5px rgba(0,0,0,0.4); }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh; transition: background 0.3s, color 0.3s; }}
        .header {{ background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%); color: white; padding: 24px 20px; position: sticky; top: 0; z-index: 100; box-shadow: var(--shadow-lg); }}
        .header-content {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
        .header h1 {{ font-size: 1.4rem; font-weight: 700; letter-spacing: -0.02em; }}
        .header-meta {{ font-size: 0.85rem; opacity: 0.9; font-family: 'JetBrains Mono', monospace; }}
        .header-controls {{ display: flex; gap: 8px; align-items: center; }}
        .btn-icon {{ background: rgba(255,255,255,0.15); border: none; color: white; width: 36px; height: 36px; border-radius: var(--radius-sm); cursor: pointer; font-size: 1.1rem; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }}
        .btn-icon:hover {{ background: rgba(255,255,255,0.25); transform: scale(1.05); }}
        .timer-bar {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 20px; position: sticky; top: 76px; z-index: 99; }}
        .timer-content {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .timer-display {{ font-family: 'JetBrains Mono', monospace; font-size: 1.5rem; font-weight: 700; color: var(--primary); display: flex; align-items: center; gap: 8px; }}
        .timer-display.urgent {{ color: var(--error); animation: pulse 1s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .progress-ring {{ width: 40px; height: 40px; }}
        .progress-ring circle {{ fill: none; stroke-width: 3; }}
        .progress-ring .bg {{ stroke: var(--border); }}
        .progress-ring .fg {{ stroke: var(--primary); stroke-linecap: round; transition: stroke-dashoffset 1s; }}
        .nav-palette {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 20px; position: sticky; top: 132px; z-index: 98; }}
        .nav-content {{ max-width: 900px; margin: 0 auto; }}
        .nav-label {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-bottom: 10px; }}
        .nav-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(40px, 1fr)); gap: 6px; }}
        .nav-btn {{ aspect-ratio: 1; border: 2px solid var(--border); background: var(--surface); color: var(--text); border-radius: var(--radius-sm); font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; }}
        .nav-btn:hover {{ border-color: var(--primary); transform: translateY(-2px); }}
        .nav-btn.active {{ border-color: var(--primary); background: var(--primary); color: white; }}
        .nav-btn.answered {{ border-color: var(--success); background: var(--success-bg); color: var(--success); }}
        .nav-btn.current {{ box-shadow: 0 0 0 3px var(--accent); }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 24px 20px 100px; }}
        .q-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 28px; margin-bottom: 20px; box-shadow: var(--shadow); scroll-margin-top: 200px; transition: all 0.3s; opacity: 0; transform: translateY(20px); animation: slideIn 0.5s forwards; }}
        @keyframes slideIn {{ to {{ opacity: 1; transform: translateY(0); }} }}
        .q-card:hover {{ box-shadow: var(--shadow-lg); }}
        .q-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .q-number {{ font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; font-weight: 600; color: var(--accent); background: var(--warning-bg); padding: 4px 12px; border-radius: 20px; }}
        .q-status {{ font-size: 0.75rem; color: var(--text-secondary); display: flex; align-items: center; gap: 4px; }}
        .q-text {{ font-size: 1.1rem; font-weight: 600; line-height: 1.7; color: var(--text); margin-bottom: 20px; }}
        .options-grid {{ display: flex; flex-direction: column; gap: 10px; }}
        .option-label {{ display: flex; align-items: center; gap: 14px; background: var(--bg); border: 2px solid var(--border); padding: 16px 20px; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s; position: relative; overflow: hidden; }}
        .option-label::before {{ content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: transparent; transition: background 0.2s; }}
        .option-label:hover {{ border-color: var(--primary-light); background: var(--surface); transform: translateX(4px); }}
        .option-label:hover::before {{ background: var(--primary-light); }}
        .option-label.selected {{ border-color: var(--primary); background: rgba(26, 54, 93, 0.05); }}
        .option-label.selected::before {{ background: var(--primary); }}
        .option-label.correct {{ border-color: var(--success); background: var(--success-bg); }}
        .option-label.correct::before {{ background: var(--success); }}
        .option-label.incorrect {{ border-color: var(--error); background: var(--error-bg); }}
        .option-label.incorrect::before {{ background: var(--error); }}
        .option-letter {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 1rem; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; background: var(--surface); border: 2px solid var(--border); border-radius: 50%; flex-shrink: 0; transition: all 0.2s; }}
        .option-label:hover .option-letter {{ border-color: var(--primary-light); color: var(--primary-light); }}
        .option-label.selected .option-letter {{ background: var(--primary); border-color: var(--primary); color: white; }}
        .option-label.correct .option-letter {{ background: var(--success); border-color: var(--success); color: white; }}
        .option-label.incorrect .option-letter {{ background: var(--error); border-color: var(--error); color: white; }}
        .option-text {{ font-size: 1rem; color: var(--text); flex: 1; }}
        input[type="radio"] {{ position: absolute; opacity: 0; pointer-events: none; }}
        .explanation-box {{ display: none; margin-top: 20px; padding: 20px; background: var(--warning-bg); border-left: 4px solid var(--accent); border-radius: var(--radius-sm); animation: fadeIn 0.4s; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(-10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .explanation-box .exp-header {{ font-weight: 700; color: var(--accent); margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }}
        .explanation-box .exp-text {{ color: var(--text-secondary); line-height: 1.7; font-size: 0.95rem; }}
        .fab {{ position: fixed; bottom: 0; left: 0; right: 0; background: var(--surface); border-top: 1px solid var(--border); padding: 16px 20px; box-shadow: 0 -4px 20px rgba(0,0,0,0.1); z-index: 1000; display: flex; justify-content: center; gap: 12px; }}
        .fab-content {{ max-width: 900px; width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
        .btn {{ padding: 12px 24px; border: none; border-radius: var(--radius-sm); font-family: 'Inter', sans-serif; font-weight: 600; font-size: 0.95rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 8px; }}
        .btn-primary {{ background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%); color: white; box-shadow: 0 4px 12px rgba(26, 54, 93, 0.3); }}
        .btn-primary:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(26, 54, 93, 0.4); }}
        .btn-primary:active {{ transform: translateY(0); }}
        .btn-secondary {{ background: var(--bg); color: var(--text); border: 2px solid var(--border); }}
        .btn-secondary:hover {{ border-color: var(--primary); color: var(--primary); }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; transform: none !important; }}
        .score-banner {{ display: none; background: linear-gradient(135deg, var(--success-bg) 0%, #b8e6c1 100%); border: 2px solid var(--success); border-radius: var(--radius); padding: 32px; margin-bottom: 32px; text-align: center; animation: slideDown 0.6s cubic-bezier(0.16, 1, 0.3, 1); }}
        @keyframes slideDown {{ from {{ opacity: 0; transform: translateY(-30px) scale(0.95); }} to {{ opacity: 1; transform: translateY(0) scale(1); }} }}
        .score-banner .score-emoji {{ font-size: 3rem; margin-bottom: 12px; }}
        .score-banner .score-title {{ font-size: 1.3rem; font-weight: 700; color: var(--success); margin-bottom: 8px; }}
        .score-banner .score-detail {{ font-size: 1rem; color: var(--text-secondary); }}
        .score-banner .score-percentage {{ font-family: 'JetBrains Mono', monospace; font-size: 2.5rem; font-weight: 700; color: var(--success); margin: 16px 0; }}
        .score-stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 20px; }}
        .stat-box {{ background: var(--surface); padding: 16px; border-radius: var(--radius-sm); border: 1px solid var(--border); }}
        .stat-value {{ font-family: 'JetBrains Mono', monospace; font-size: 1.5rem; font-weight: 700; }}
        .stat-label {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px; }}
        .review-controls {{ display: none; justify-content: center; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
        .review-controls.visible {{ display: flex; }}
        .review-filter {{ padding: 8px 16px; border: 2px solid var(--border); background: var(--surface); border-radius: 20px; cursor: pointer; font-size: 0.85rem; font-weight: 500; transition: all 0.2s; }}
        .review-filter:hover, .review-filter.active {{ border-color: var(--primary); background: var(--primary); color: white; }}
        .keyboard-hint {{ position: fixed; bottom: 80px; right: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 16px; font-size: 0.75rem; color: var(--text-secondary); box-shadow: var(--shadow); opacity: 0.7; transition: opacity 0.2s; }}
        .keyboard-hint:hover {{ opacity: 1; }}
        .keyboard-hint kbd {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; }}
        @media print {{ .header, .timer-bar, .nav-palette, .fab, .keyboard-hint, .btn-icon {{ display: none !important; }} .q-card {{ break-inside: avoid; box-shadow: none; border: 1px solid #ddd; }} .explanation-box {{ display: block !important; page-break-inside: avoid; }} body {{ background: white; }} .container {{ padding: 20px; max-width: 100%; }} }}
        @media (max-width: 600px) {{ .header h1 {{ font-size: 1.1rem; }} .timer-display {{ font-size: 1.2rem; }} .q-card {{ padding: 20px; }} .option-label {{ padding: 14px 16px; }} .score-stats {{ grid-template-columns: 1fr; }} .keyboard-hint {{ display: none; }} }}
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--text-secondary); }}
    </style>
</head>
<body>
    <header class="header">
        <div class="header-content">
            <div>
                <h1>📋 SSC MTS {subject.upper()} Mock Test</h1>
                <div class="header-meta">Generated: {datetime.now().strftime('%d %B %Y')} | {total_questions} Questions | 10 Minutes</div>
            </div>
            <div class="header-controls">
                <button class="btn-icon" onclick="toggleTheme()" title="Toggle Dark Mode">🌙</button>
                <button class="btn-icon" onclick="window.print()" title="Print">🖨️</button>
            </div>
        </div>
    </header>

    <div class="timer-bar">
        <div class="timer-content">
            <div class="timer-display" id="timerDisplay">
                <span>⏱️</span>
                <span id="timerText">10:00</span>
            </div>
            <div style="display:flex;align-items:center;gap:12px;">
                <span style="font-size:0.85rem;color:var(--text-secondary);">
                    <span id="answeredCount">0</span>/{total_questions} Answered
                </span>
                <svg class="progress-ring" viewBox="0 0 40 40">
                    <circle class="bg" cx="20" cy="20" r="16"/>
                    <circle class="fg" id="progressCircle" cx="20" cy="20" r="16" stroke-dasharray="100.53" stroke-dashoffset="100.53"/>
                </svg>
            </div>
        </div>
    </div>

    <div class="nav-palette">
        <div class="nav-content">
            <div class="nav-label">Question Navigator</div>
            <div class="nav-grid" id="navGrid">
{nav_buttons}
            </div>
        </div>
    </div>

    <div class="container">
        <div id="scoreBanner" class="score-banner">
            <div class="score-emoji" id="scoreEmoji">🎉</div>
            <div class="score-title" id="scoreTitle">Test Completed!</div>
            <div class="score-percentage" id="scorePercentage">0%</div>
            <div class="score-detail" id="scoreDetail">0 / 0 correct</div>
            <div class="score-stats">
                <div class="stat-box">
                    <div class="stat-value" id="statCorrect" style="color:var(--success)">0</div>
                    <div class="stat-label">Correct</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="statWrong" style="color:var(--error)">0</div>
                    <div class="stat-label">Wrong</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="statTime">0:00</div>
                    <div class="stat-label">Time Taken</div>
                </div>
            </div>
        </div>

        <div id="reviewControls" class="review-controls">
            <button class="review-filter active" onclick="filterQuestions('all')">All</button>
            <button class="review-filter" onclick="filterQuestions('correct')">✓ Correct</button>
            <button class="review-filter" onclick="filterQuestions('wrong')">✗ Wrong</button>
            <button class="review-filter" onclick="filterQuestions('unattempted')">? Unattempted</button>
        </div>

        <form id="quizForm">
{question_cards}
        </form>
    </div>

    <div class="fab">
        <div class="fab-content">
            <button type="button" class="btn btn-secondary" id="prevBtn" onclick="prevQuestion()" disabled>← Previous</button>
            <button type="button" class="btn btn-primary" id="submitBtn" onclick="checkQuiz()">🚀 Submit Test</button>
            <button type="button" class="btn btn-secondary" id="nextBtn" onclick="nextQuestion()">Next →</button>
        </div>
    </div>

    <div class="keyboard-hint">
        <kbd>1</kbd>-<kbd>4</kbd> Select &nbsp; <kbd>↑</kbd><kbd>↓</kbd> Navigate &nbsp; <kbd>Enter</kbd> Next/Submit
    </div>

    <script>
    const TOTAL = {total_questions};
    const TIME_LIMIT = 600;
    let timeLeft = TIME_LIMIT;
    let timerInterval;
    let startTime = Date.now();
    let currentQuestion = 0;
    let answers = {{}};
    let isSubmitted = false;

    function toggleTheme() {{
        const html = document.documentElement;
        const current = html.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem('ssc-theme', next);
    }}

    const savedTheme = localStorage.getItem('ssc-theme');
    if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
    else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {{
        document.documentElement.setAttribute('data-theme', 'dark');
    }}

    function startTimer() {{
        timerInterval = setInterval(() => {{
            timeLeft--;
            updateTimerDisplay();
            updateProgressRing();
            if (timeLeft <= 0) {{ clearInterval(timerInterval); checkQuiz(true); }}
        }}, 1000);
    }}

    function updateTimerDisplay() {{
        const m = Math.floor(timeLeft / 60);
        const s = timeLeft % 60;
        document.getElementById('timerText').textContent = `${{m}}:${{s.toString().padStart(2, '0')}}`;
        if (timeLeft <= 60) document.getElementById('timerDisplay').classList.add('urgent');
    }}

    function updateProgressRing() {{
        const answered = Object.keys(answers).length;
        document.getElementById('answeredCount').textContent = answered;
        const pct = answered / TOTAL;
        const circumference = 2 * Math.PI * 16;
        document.getElementById('progressCircle').style.strokeDashoffset = circumference - (pct * circumference);
    }}

    function scrollToQuestion(idx) {{
        currentQuestion = idx;
        document.getElementById(`q_box_${{idx}}`).scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        updateNavHighlight();
        updateNavButtons();
    }}

    function updateNavHighlight() {{
        document.querySelectorAll('.nav-btn').forEach((btn, i) => {{
            btn.classList.toggle('current', i === currentQuestion);
        }});
    }}

    function updateNavButtons() {{
        document.getElementById('prevBtn').disabled = currentQuestion === 0;
        document.getElementById('nextBtn').textContent = currentQuestion === TOTAL - 1 ? 'Submit →' : 'Next →';
    }}

    function nextQuestion() {{
        if (currentQuestion < TOTAL - 1) scrollToQuestion(currentQuestion + 1);
        else checkQuiz();
    }}

    function prevQuestion() {{
        if (currentQuestion > 0) scrollToQuestion(currentQuestion - 1);
    }}

    function selectOption(qIdx, oIdx) {{
        if (isSubmitted) return;
        document.querySelectorAll(`#q_box_${{qIdx}} .option-label`).forEach(l => l.classList.remove('selected'));
        document.getElementById(`label_${{qIdx}}_${{oIdx}}`).classList.add('selected');
        document.querySelector(`input[name="question_${{qIdx}}"][value="${{oIdx}}"]`).checked = true;
        onOptionChange(qIdx, oIdx);
    }}

    function onOptionChange(qIdx, oIdx) {{
        if (isSubmitted) return;
        answers[qIdx] = oIdx;
        const navBtn = document.getElementById(`nav_${{qIdx}}`);
        navBtn.classList.add('answered');
        navBtn.classList.remove('current');
        document.getElementById(`status_${{qIdx}}`).textContent = 'Answered';
        document.getElementById(`q_box_${{qIdx}}`).setAttribute('data-status', 'answered');
        updateProgressRing();
        localStorage.setItem('ssc_quiz_progress', JSON.stringify(answers));
        if (qIdx < TOTAL - 1) {{
            clearTimeout(window.autoAdvanceTimer);
            window.autoAdvanceTimer = setTimeout(() => scrollToQuestion(qIdx + 1), 500);
        }}
    }}

    function checkQuiz(autoSubmit = false) {{
        const answered = Object.keys(answers).length;
        if (!autoSubmit && answered < TOTAL) {{
            const unans = TOTAL - answered;
            if (!confirm(`${{unans}} question(s) still unanswered. Submit anyway?`)) return;
        }}
        isSubmitted = true;
        clearInterval(timerInterval);
        let score = 0, correct = 0, wrong = 0;
        for (let i = 0; i < TOTAL; i++) {{
            const correctIdx = parseInt(document.getElementById(`ans_key_${{i}}`).value);
            const selected = answers[i];
            const expBox = document.getElementById(`exp_${{i}}`);
            document.querySelectorAll(`#q_box_${{i}} .option-label`).forEach(l => l.classList.remove('selected'));
            if (selected !== undefined) {{
                if (selected == correctIdx) {{ score++; correct++; document.getElementById(`label_${{i}}_${{selected}}`).classList.add('correct'); }}
                else {{ wrong++; document.getElementById(`label_${{i}}_${{selected}}`).classList.add('incorrect'); document.getElementById(`label_${{i}}_${{correctIdx}}`).classList.add('correct'); }}
            }} else {{
                document.getElementById(`label_${{i}}_${{correctIdx}}`).classList.add('correct');
            }}
            expBox.style.display = 'block';
            document.getElementById(`q_box_${{i}}`).setAttribute('data-status', selected === undefined ? 'unattempted' : (selected == correctIdx ? 'correct' : 'wrong'));
        }}
        const percentage = Math.round((score / TOTAL) * 100);
        const timeTaken = Math.round((Date.now() - startTime) / 1000);
        const timeM = Math.floor(timeTaken / 60);
        const timeS = timeTaken % 60;
        let emoji = percentage >= 80 ? '🏆' : percentage >= 60 ? '👍' : percentage >= 40 ? '📖' : '💪';
        let title = percentage >= 80 ? 'Outstanding Performance!' : percentage >= 60 ? 'Good Job!' : percentage >= 40 ? 'Keep Practicing!' : 'Don\'t Give Up!';
        document.getElementById('scoreEmoji').textContent = emoji;
        document.getElementById('scoreTitle').textContent = title;
        document.getElementById('scorePercentage').textContent = percentage + '%';
        document.getElementById('scoreDetail').textContent = `${{score}} / ${{TOTAL}} correct`;
        document.getElementById('statCorrect').textContent = correct;
        document.getElementById('statWrong').textContent = wrong;
        document.getElementById('statTime').textContent = `${{timeM}}:${{timeS.toString().padStart(2,'0')}}`;
        document.getElementById('scoreBanner').style.display = 'block';
        document.getElementById('reviewControls').classList.add('visible');
        document.getElementById('submitBtn').style.display = 'none';
        document.getElementById('nextBtn').style.display = 'none';
        document.getElementById('prevBtn').style.display = 'none';
        localStorage.setItem('ssc_last_result', JSON.stringify({{subject: '{subject}', score, total: TOTAL, percentage, correct, wrong, timeTaken, date: new Date().toISOString()}}));
        localStorage.removeItem('ssc_quiz_progress');
        window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function filterQuestions(filter) {{
        document.querySelectorAll('.review-filter').forEach(f => f.classList.remove('active'));
        event.target.classList.add('active');
        document.querySelectorAll('.q-card').forEach(card => {{
            const status = card.getAttribute('data-status');
            card.style.display = (filter === 'all' || status === filter) ? 'block' : 'none';
        }});
    }}

    document.addEventListener('keydown', (e) => {{
        if (isSubmitted) return;
        const key = e.key;
        if (key >= '1' && key <= '4') {{ e.preventDefault(); selectOption(currentQuestion, parseInt(key) - 1); }}
        if (key === 'ArrowDown' || key === 'ArrowRight') {{ e.preventDefault(); if (currentQuestion < TOTAL - 1) scrollToQuestion(currentQuestion + 1); }}
        if (key === 'ArrowUp' || key === 'ArrowLeft') {{ e.preventDefault(); if (currentQuestion > 0) scrollToQuestion(currentQuestion - 1); }}
        if (key === 'Enter') {{ e.preventDefault(); nextQuestion(); }}
    }});

    const observer = new IntersectionObserver((entries) => {{
        entries.forEach(entry => {{
            if (entry.isIntersecting) {{
                const idx = parseInt(entry.target.id.replace('q_box_', ''));
                currentQuestion = idx;
                updateNavHighlight();
                updateNavButtons();
            }}
        }});
    }}, {{ threshold: 0.5 }});
    document.querySelectorAll('.q-card').forEach(card => observer.observe(card));

    const savedProgress = localStorage.getItem('ssc_quiz_progress');
    if (savedProgress) {{
        try {{
            const saved = JSON.parse(savedProgress);
            if (confirm('You have saved progress. Resume from where you left off?')) {{
                answers = saved;
                Object.entries(answers).forEach(([qIdx, oIdx]) => selectOption(parseInt(qIdx), oIdx));
            }} else {{ localStorage.removeItem('ssc_quiz_progress'); }}
        }} catch(e) {{ localStorage.removeItem('ssc_quiz_progress'); }}
    }}

    updateTimerDisplay();
    updateProgressRing();
    updateNavHighlight();
    updateNavButtons();
    startTimer();
    </script>
</body>
</html>"""

        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        return filename

# ═══════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class QuizFactory:
    def __init__(self):
        self.providers = ConfigManager.load_providers()
        self.provider_engine = ProviderEngine(self.providers)
        self.memory = MemoryManager()
        self.database = QuestionDatabase()
        self.telegram = TelegramDispatcher(
            os.getenv("TELEGRAM_TOKEN", ""),
            os.getenv("TELEGRAM_CHAT_ID", "")
        )
        self.start_time = time.time()
        self.stats = {"subjects_processed": 0, "questions_generated": 0, "files_sent": 0}

    def deduplicate(self, quiz_data: List[dict]) -> List[dict]:
        valid_new = []
        for item in quiz_data:
            q_hash = hashlib.md5(item["question"].encode()).hexdigest()
            if self.memory.exists(q_hash):
                continue
            valid_new.append(item)
            self.memory.add(q_hash)
        return valid_new

    def save_to_database(self, quiz_list: List[dict], subject: str) -> None:
        entries = []
        for quiz in quiz_list:
            entries.append({
                "timestamp": datetime.now().isoformat(),
                "subject": subject,
                "hash": hashlib.md5(quiz["question"].encode()).hexdigest(),
                "data": quiz
            })
        self.database.append(entries)

    def cleanup_file(self, filepath: str) -> None:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                Logger.success(f"Cleaned up {os.path.basename(filepath)}")
        except Exception as e:
            Logger.error(f"Failed to cleanup {filepath}: {e}")

    def run_subject(self, subject: str, subject_config: dict) -> bool:
        if (time.time() - self.start_time) > ConfigManager.RUN_DURATION_SECONDS:
            Logger.warning("Time limit reached. Stopping.")
            return False

        Logger.info(f"\n{'='*60}", subject)
        Logger.info(f"🚀 Starting generation for: {subject}", subject)
        Logger.info(f"{'='*60}", subject)

        quiz_data, rotate = self.provider_engine.fetch_quiz(
            subject, 
            subject_config["description"]
        )

        if rotate:
            Logger.warning("Provider rotation triggered", subject)
            return True  # Continue to next subject with new provider

        if not quiz_data:
            Logger.error("Failed to generate quiz data", subject)
            return True

        valid_new = self.deduplicate(quiz_data)
        Logger.info(f"Deduplication: {len(quiz_data)} generated → {len(valid_new)} unique", subject)

        if len(valid_new) < ConfigManager.MIN_UNIQUE_THRESHOLD:
            Logger.warning(f"Only {len(valid_new)} unique questions. Skipping.", subject)
            return True

        # Generate and send text file
        txt_file = TextStudyGenerator.generate(valid_new, subject)
        if txt_file:
            caption = f"📖 <b>{subject}</b> Study Material ({datetime.now().strftime('%d %b %Y')})\n\n{subject_config['icon']} {len(valid_new)} unique questions generated."
            if self.telegram.send_document(txt_file, caption):
                self.stats["files_sent"] += 1
            self.cleanup_file(txt_file)

        # Generate and send HTML mock test
        html_file = HTMLMockTestGenerator.generate(valid_new, subject)
        if html_file:
            caption = f"📝 <b>{subject}</b> Interactive Mock Test ({datetime.now().strftime('%d %b %Y')})\n\n{subject_config['icon']} {len(valid_new)} questions | 10 min timer | Keyboard shortcuts | Dark mode | Review filters"
            if self.telegram.send_document(html_file, caption):
                self.stats["files_sent"] += 1
            self.cleanup_file(html_file)

        self.save_to_database(valid_new, subject)
        self.stats["subjects_processed"] += 1
        self.stats["questions_generated"] += len(valid_new)

        Logger.success(f"✅ Subject {subject} completed successfully", subject)
        return True

    def run(self):
        Logger.info("\n" + "="*70)
        Logger.info("  SSC MTS QUIZ FACTORY PRO v3.0")
        Logger.info("  Professional Grade Quiz Generation System")
        Logger.info("="*70)

        if not self.providers:
            Logger.fatal("FATAL: No API providers configured. Set GROQ_API_KEYS, OPENROUTER_API_KEYS, or GEMINI_API_KEYS.")
            exit(1)

        if not os.getenv("TELEGRAM_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
            Logger.fatal("FATAL: Telegram credentials missing. Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.")
            exit(1)

        Logger.info(f"Loaded {len(self.providers)} API provider(s)")
        Logger.info(f"Subjects configured: {list(ConfigManager.SUBJECTS.keys())}")
        Logger.info(f"Runtime limit: {ConfigManager.RUN_DURATION_SECONDS // 60} minutes")
        Logger.info("="*70 + "\n")

        for subject, config in ConfigManager.SUBJECTS.items():
            if not self.run_subject(subject, config):
                break

        self.memory.save()

        elapsed = time.time() - self.start_time
        Logger.info("\n" + "="*70)
        Logger.info("  SESSION SUMMARY")
        Logger.info("="*70)
        Logger.info(f"  Subjects processed: {self.stats['subjects_processed']}")
        Logger.info(f"  Questions generated: {self.stats['questions_generated']}")
        Logger.info(f"  Files sent: {self.stats['files_sent']}")
        Logger.info(f"  Time elapsed: {elapsed//60:.0f}m {elapsed%60:.0f}s")
        Logger.info("="*70)
        Logger.success("All workflows completed successfully! 🎯")

# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    factory = QuizFactory()
    factory.run()
