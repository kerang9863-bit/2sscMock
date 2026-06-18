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

    def report_failure(self, provider: ProviderConfig, is_rate_limit: bool = False) -> None:
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
    """
    BULLETPROOF INTERACTIVE MOCK TEST GENERATOR v3.2
    Designed specifically for Telegram WebView / Android compatibility
    """

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
            nav_buttons += f'                <button class="nav-btn" id="nav_{i}">{i+1}</button>\n'

        # Build question cards
        question_cards = ""
        for idx, q in enumerate(shuffled_questions):
            options_html = ""
            for o_idx, opt in enumerate(q["options"]):
                options_html += f"""
                    <div class="option-label" id="label_{idx}_{o_idx}" data-q="{idx}" data-o="{o_idx}">
                        <input type="radio" name="question_{idx}" value="{o_idx}">
                        <span class="option-letter">{chr(65+o_idx)}</span>
                        <span class="option-text">{opt}</span>
                    </div>"""

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
    <title>SSC MTS {subject.upper()} — Mock Test</title>
    <style>
        :root {{ --primary: #1a365d; --primary-light: #2c5282; --accent: #dd6b20; --accent-light: #ed8936; --success: #276749; --success-bg: #c6f6d5; --error: #c53030; --error-bg: #fed7d7; --warning: #c05621; --warning-bg: #feebc8; --bg: #f7fafc; --surface: #ffffff; --text: #1a202c; --text-secondary: #4a5568; --border: #e2e8f0; --shadow: 0 4px 6px -1px rgba(0,0,0,0.1); --shadow-lg: 0 20px 25px -5px rgba(0,0,0,0.1); --radius: 12px; --radius-sm: 8px; }}
        [data-theme="dark"] {{ --primary: #63b3ed; --primary-light: #4299e1; --accent: #f6ad55; --success: #68d391; --success-bg: #22543d; --error: #fc8181; --error-bg: #742a2a; --warning: #fbd38d; --warning-bg: #744210; --bg: #0d1117; --surface: #161b22; --text: #e2e8f0; --text-secondary: #a0aec0; --border: #30363d; --shadow: 0 4px 6px -1px rgba(0,0,0,0.3); --shadow-lg: 0 20px 25px -5px rgba(0,0,0,0.4); }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh; transition: background 0.3s, color 0.3s; -webkit-touch-callout: none; user-select: none; }}
        .header {{ background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%); color: white; padding: 20px; position: sticky; top: 0; z-index: 100; box-shadow: var(--shadow-lg); }}
        .header-content {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
        .header h1 {{ font-size: 1.2rem; font-weight: 700; }}
        .header-meta {{ font-size: 0.8rem; opacity: 0.9; }}
        .header-controls {{ display: flex; gap: 8px; }}
        .btn-icon {{ background: rgba(255,255,255,0.15); border: none; color: white; width: 40px; height: 40px; border-radius: var(--radius-sm); cursor: pointer; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; touch-action: manipulation; -webkit-appearance: none; }}
        .timer-bar {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 20px; position: sticky; top: 64px; z-index: 99; }}
        .timer-content {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .timer-display {{ font-family: monospace; font-size: 1.4rem; font-weight: 700; color: var(--primary); }}
        .timer-display.urgent {{ color: var(--error); animation: pulse 1s infinite; }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.5}} }}
        .nav-palette {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 20px; position: sticky; top: 110px; z-index: 98; }}
        .nav-label {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 8px; }}
        .nav-grid {{ display: grid; grid-template-columns: repeat(10, 1fr); gap: 6px; }}
        .nav-btn {{ border: 2px solid var(--border); background: var(--surface); color: var(--text); border-radius: var(--radius-sm); font-family: monospace; font-weight: 600; font-size: 0.85rem; cursor: pointer; padding: 8px; touch-action: manipulation; -webkit-appearance: none; transition: all 0.2s; }}
        .nav-btn.answered {{ border-color: var(--success); background: var(--success-bg); color: var(--success); }}
        .nav-btn.current {{ box-shadow: 0 0 0 3px var(--accent); }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 20px 16px 100px; }}
        .q-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; box-shadow: var(--shadow); scroll-margin-top: 180px; }}
        .q-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .q-number {{ font-family: monospace; font-size: 0.75rem; font-weight: 600; color: var(--accent); background: var(--warning-bg); padding: 4px 10px; border-radius: 20px; }}
        .q-status {{ font-size: 0.75rem; color: var(--text-secondary); }}
        .q-text {{ font-size: 1.05rem; font-weight: 600; line-height: 1.6; margin-bottom: 16px; }}
        .options-grid {{ display: flex; flex-direction: column; gap: 8px; }}
        .option-label {{ display: flex; align-items: center; gap: 12px; background: var(--bg); border: 2px solid var(--border); padding: 14px 16px; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.2s; position: relative; touch-action: manipulation; }}
        .option-label.selected {{ border-color: var(--primary); background: rgba(26,54,93,0.08); }}
        .option-label.correct {{ border-color: var(--success); background: var(--success-bg); }}
        .option-label.incorrect {{ border-color: var(--error); background: var(--error-bg); }}
        .option-letter {{ font-family: monospace; font-weight: 700; font-size: 0.95rem; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: var(--surface); border: 2px solid var(--border); border-radius: 50%; flex-shrink: 0; pointer-events: none; }}
        .option-label.selected .option-letter {{ background: var(--primary); border-color: var(--primary); color: white; }}
        .option-label.correct .option-letter {{ background: var(--success); border-color: var(--success); color: white; }}
        .option-label.incorrect .option-letter {{ background: var(--error); border-color: var(--error); color: white; }}
        .option-text {{ font-size: 0.95rem; flex: 1; pointer-events: none; }}
        input[type="radio"] {{ position: absolute; opacity: 0; }}
        .explanation-box {{ display: none; margin-top: 16px; padding: 16px; background: var(--warning-bg); border-left: 4px solid var(--accent); border-radius: var(--radius-sm); }}
        .explanation-box .exp-header {{ font-weight: 700; color: var(--accent); margin-bottom: 6px; }}
        .explanation-box .exp-text {{ color: var(--text-secondary); font-size: 0.9rem; }}
        .fab {{ position: fixed; bottom: 0; left: 0; right: 0; background: var(--surface); border-top: 1px solid var(--border); padding: 12px 16px; box-shadow: 0 -4px 20px rgba(0,0,0,0.1); z-index: 1000; display: flex; justify-content: center; gap: 10px; }}
        .fab-content {{ max-width: 900px; width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
        .btn {{ padding: 12px 20px; border: none; border-radius: var(--radius-sm); font-weight: 600; font-size: 0.9rem; cursor: pointer; transition: all 0.2s; touch-action: manipulation; -webkit-appearance: none; flex: 1; text-align: center; }}
        .btn-primary {{ background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%); color: white; }}
        .btn-secondary {{ background: var(--bg); color: var(--text); border: 2px solid var(--border); }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .score-banner {{ display: none; background: linear-gradient(135deg, var(--success-bg) 0%, #b8e6c1 100%); border: 2px solid var(--success); border-radius: var(--radius); padding: 24px; margin-bottom: 24px; text-align: center; }}
        .score-banner .score-emoji {{ font-size: 2.5rem; margin-bottom: 8px; }}
        .score-banner .score-percentage {{ font-family: monospace; font-size: 2rem; font-weight: 700; color: var(--success); margin: 12px 0; }}
        .score-stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }}
        .stat-box {{ background: var(--surface); padding: 12px; border-radius: var(--radius-sm); border: 1px solid var(--border); }}
        .stat-value {{ font-family: monospace; font-size: 1.3rem; font-weight: 700; }}
        .stat-label {{ font-size: 0.75rem; color: var(--text-secondary); }}
        .review-controls {{ display: none; justify-content: center; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
        .review-controls.visible {{ display: flex; }}
        .review-filter {{ padding: 8px 14px; border: 2px solid var(--border); background: var(--surface); border-radius: 20px; cursor: pointer; font-size: 0.8rem; font-weight: 500; touch-action: manipulation; -webkit-appearance: none; }}
        .review-filter.active {{ border-color: var(--primary); background: var(--primary); color: white; }}
        @media (max-width: 600px) {{ .nav-grid {{ grid-template-columns: repeat(5, 1fr); }} .header h1 {{ font-size: 1rem; }} .score-stats {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <header class="header">
        <div class="header-content">
            <div>
                <h1>📋 SSC MTS {subject.upper()} Mock Test</h1>
                <div class="header-meta">{datetime.now().strftime('%d %b %Y')} | {total_questions} Qs | 10 Min</div>
            </div>
            <div class="header-controls">
                <button class="btn-icon" id="themeBtn">🌙</button>
                <button class="btn-icon" id="printBtn">🖨️</button>
            </div>
        </div>
    </header>

    <div class="timer-bar">
        <div class="timer-content">
            <div class="timer-display" id="timerDisplay">⏱️ <span id="timerText">10:00</span></div>
            <div style="font-size:0.85rem;color:var(--text-secondary);">
                <span id="answeredCount">0</span>/{total_questions} Answered
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
                <div class="stat-box"><div class="stat-value" id="statCorrect" style="color:var(--success)">0</div><div class="stat-label">Correct</div></div>
                <div class="stat-box"><div class="stat-value" id="statWrong" style="color:var(--error)">0</div><div class="stat-label">Wrong</div></div>
                <div class="stat-box"><div class="stat-value" id="statTime">0:00</div><div class="stat-label">Time Taken</div></div>
            </div>
        </div>

        <div id="reviewControls" class="review-controls">
            <button class="review-filter active" data-filter="all">All</button>
            <button class="review-filter" data-filter="correct">✓ Correct</button>
            <button class="review-filter" data-filter="wrong">✗ Wrong</button>
            <button class="review-filter" data-filter="unattempted">? Unattempted</button>
        </div>

        <form id="quizForm">
{question_cards}
        </form>
    </div>

    <div class="fab">
        <div class="fab-content">
            <button class="btn btn-secondary" id="prevBtn">← Previous</button>
            <button class="btn btn-primary" id="submitBtn">🚀 Submit</button>
            <button class="btn btn-secondary" id="nextBtn">Next →</button>
        </div>
    </div>

    <script>
    (function() {{
        'use strict';

        // ═══════════════════════════════════════════════════════════════════════
        //  SAFE STORAGE — Works even when localStorage is blocked
        // ═══════════════════════════════════════════════════════════════════════
        var SafeStorage = {{
            mem: {{}},
            ok: false,
            init: function() {{
                try {{ localStorage.setItem('__t', '1'); localStorage.removeItem('__t'); this.ok = true; }} catch(e) {{}}
            }},
            get: function(k) {{
                if (this.ok) try {{ var v = localStorage.getItem(k); if (v) return v; }} catch(e) {{}}
                return this.mem[k] || null;
            }},
            set: function(k, v) {{
                this.mem[k] = v;
                if (this.ok) try {{ localStorage.setItem(k, v); }} catch(e) {{}}
            }},
            del: function(k) {{
                delete this.mem[k];
                if (this.ok) try {{ localStorage.removeItem(k); }} catch(e) {{}}
            }}
        }};
        SafeStorage.init();

        // ═══════════════════════════════════════════════════════════════════════
        //  STATE
        // ═══════════════════════════════════════════════════════════════════════
        var TOTAL = {total_questions};
        var TIME_LIMIT = 600;
        var timeLeft = TIME_LIMIT;
        var timerInterval = null;
        var startTime = Date.now();
        var currentQuestion = 0;
        var answers = {{}};
        var isSubmitted = false;

        // ═══════════════════════════════════════════════════════════════════════
        //  DOM HELPERS
        // ═══════════════════════════════════════════════════════════════════════
        function $(id) {{ return document.getElementById(id); }}
        function $$(sel) {{ return document.querySelectorAll(sel); }}

        // ═══════════════════════════════════════════════════════════════════════
        //  THEME
        // ═══════════════════════════════════════════════════════════════════════
        function setTheme(theme) {{
            document.documentElement.setAttribute('data-theme', theme);
            SafeStorage.set('ssc-theme', theme);
        }}

        function toggleTheme() {{
            var cur = document.documentElement.getAttribute('data-theme');
            setTheme(cur === 'dark' ? 'light' : 'dark');
        }}

        var savedTheme = SafeStorage.get('ssc-theme');
        if (savedTheme) setTheme(savedTheme);
        else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) setTheme('dark');

        $('themeBtn').addEventListener('click', toggleTheme);
        $('printBtn').addEventListener('click', function() {{ window.print(); }});

        // ═══════════════════════════════════════════════════════════════════════
        //  TIMER
        // ═══════════════════════════════════════════════════════════════════════
        function updateTimer() {{
            var m = Math.floor(timeLeft / 60);
            var s = timeLeft % 60;
            $('timerText').textContent = m + ':' + (s < 10 ? '0' : '') + s;
            if (timeLeft <= 60) $('timerDisplay').classList.add('urgent');
        }}

        function updateAnswered() {{
            $('answeredCount').textContent = Object.keys(answers).length;
        }}

        function startTimer() {{
            if (timerInterval) return;
            timerInterval = setInterval(function() {{
                timeLeft--;
                updateTimer();
                updateAnswered();
                if (timeLeft <= 0) {{
                    clearInterval(timerInterval);
                    timerInterval = null;
                    submitQuiz(true);
                }}
            }}, 1000);
        }}

        // ═══════════════════════════════════════════════════════════════════════
        //  NAVIGATION
        // ═══════════════════════════════════════════════════════════════════════
        function scrollToQuestion(idx) {{
            if (idx < 0 || idx >= TOTAL) return;
            currentQuestion = idx;
            var el = $('q_box_' + idx);
            if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            updateNavButtons();
        }}

        function updateNavButtons() {{
            $('prevBtn').disabled = currentQuestion === 0;
            $('nextBtn').textContent = currentQuestion === TOTAL - 1 ? 'Submit →' : 'Next →';
            $$('.nav-btn').forEach(function(btn, i) {{
                btn.classList.toggle('current', i === currentQuestion);
            }});
        }}

        $('prevBtn').addEventListener('click', function() {{ scrollToQuestion(currentQuestion - 1); }});
        $('nextBtn').addEventListener('click', function() {{
            if (currentQuestion < TOTAL - 1) scrollToQuestion(currentQuestion + 1);
            else submitQuiz();
        }});

        // Nav buttons — use event delegation on container
        $('navGrid').addEventListener('click', function(e) {{
            var btn = e.target.closest('.nav-btn');
            if (!btn) return;
            var idx = parseInt(btn.id.replace('nav_', ''));
            if (!isNaN(idx)) scrollToQuestion(idx);
        }});

        // ═══════════════════════════════════════════════════════════════════════
        //  OPTION SELECTION — Event delegation on document
        // ═══════════════════════════════════════════════════════════════════════
        document.addEventListener('click', function(e) {{
            if (isSubmitted) return;
            var label = e.target.closest('.option-label');
            if (!label) return;

            var qIdx = parseInt(label.getAttribute('data-q'));
            var oIdx = parseInt(label.getAttribute('data-o'));
            if (isNaN(qIdx) || isNaN(oIdx)) return;

            // Remove previous selection in this question
            var qBox = $('q_box_' + qIdx);
            if (qBox) {{
                qBox.querySelectorAll('.option-label').forEach(function(l) {{ l.classList.remove('selected'); }});
            }}

            // Add selection
            label.classList.add('selected');
            var radio = label.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;

            // Record answer
            answers[qIdx] = oIdx;

            // Update UI
            var navBtn = $('nav_' + qIdx);
            if (navBtn) navBtn.classList.add('answered');
            var statusEl = $('status_' + qIdx);
            if (statusEl) statusEl.textContent = 'Answered';
            if (qBox) qBox.setAttribute('data-status', 'answered');
            updateAnswered();
            SafeStorage.set('ssc-quiz-progress', JSON.stringify(answers));

            // Auto-advance
            if (qIdx < TOTAL - 1) {{
                setTimeout(function() {{ scrollToQuestion(qIdx + 1); }}, 400);
            }}
        }});

        // ═══════════════════════════════════════════════════════════════════════
        //  SUBMIT
        // ═══════════════════════════════════════════════════════════════════════
        $('submitBtn').addEventListener('click', function() {{ submitQuiz(); }});

        function submitQuiz(auto) {{
            var answered = Object.keys(answers).length;
            if (!auto && answered < TOTAL) {{
                if (!window.confirm(answered + '/' + TOTAL + ' answered. Submit anyway?')) return;
            }}

            isSubmitted = true;
            if (timerInterval) {{ clearInterval(timerInterval); timerInterval = null; }}

            var score = 0, correct = 0, wrong = 0;

            for (var i = 0; i < TOTAL; i++) {{
                var ansKey = $('ans_key_' + i);
                if (!ansKey) continue;
                var correctIdx = parseInt(ansKey.value);
                var selected = answers[i];
                var qBox = $('q_box_' + i);

                if (qBox) {{
                    qBox.querySelectorAll('.option-label').forEach(function(l) {{ l.classList.remove('selected'); }});
                }}

                if (selected !== undefined) {{
                    if (selected === correctIdx) {{
                        score++; correct++;
                        var el = $('label_' + i + '_' + selected);
                        if (el) el.classList.add('correct');
                    }} else {{
                        wrong++;
                        var el1 = $('label_' + i + '_' + selected);
                        if (el1) el1.classList.add('incorrect');
                        var el2 = $('label_' + i + '_' + correctIdx);
                        if (el2) el2.classList.add('correct');
                    }}
                }} else {{
                    var el = $('label_' + i + '_' + correctIdx);
                    if (el) el.classList.add('correct');
                }}

                var expBox = $('exp_' + i);
                if (expBox) expBox.style.display = 'block';
                if (qBox) qBox.setAttribute('data-status', selected === undefined ? 'unattempted' : (selected === correctIdx ? 'correct' : 'wrong'));
            }}

            var pct = Math.round((score / TOTAL) * 100);
            var timeTaken = Math.round((Date.now() - startTime) / 1000);
            var tm = Math.floor(timeTaken / 60);
            var ts = timeTaken % 60;

            $('scoreEmoji').textContent = pct >= 80 ? '🏆' : pct >= 60 ? '👍' : pct >= 40 ? '📖' : '💪';
            $('scoreTitle').textContent = pct >= 80 ? 'Outstanding!' : pct >= 60 ? 'Good Job!' : pct >= 40 ? 'Keep Practicing!' : 'Don\'t Give Up!';
            $('scorePercentage').textContent = pct + '%';
            $('scoreDetail').textContent = score + ' / ' + TOTAL + ' correct';
            $('statCorrect').textContent = correct;
            $('statWrong').textContent = wrong;
            $('statTime').textContent = tm + ':' + (ts < 10 ? '0' : '') + ts;

            $('scoreBanner').style.display = 'block';
            $('reviewControls').classList.add('visible');
            $('submitBtn').style.display = 'none';
            $('nextBtn').style.display = 'none';
            $('prevBtn').style.display = 'none';

            SafeStorage.set('ssc-last-result', JSON.stringify({{subject: '{subject}', score: score, total: TOTAL, percentage: pct, correct: correct, wrong: wrong, timeTaken: timeTaken}}));
            SafeStorage.del('ssc-quiz-progress');
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        // ═══════════════════════════════════════════════════════════════════════
        //  REVIEW FILTERS
        // ═══════════════════════════════════════════════════════════════════════
        $('reviewControls').addEventListener('click', function(e) {{
            var btn = e.target.closest('.review-filter');
            if (!btn) return;
            $$('.review-filter').forEach(function(f) {{ f.classList.remove('active'); }});
            btn.classList.add('active');
            var filter = btn.getAttribute('data-filter');
            $$('.q-card').forEach(function(card) {{
                card.style.display = (filter === 'all' || card.getAttribute('data-status') === filter) ? 'block' : 'none';
            }});
        }});

        // ═══════════════════════════════════════════════════════════════════════
        //  KEYBOARD SHORTCUTS
        // ═══════════════════════════════════════════════════════════════════════
        document.addEventListener('keydown', function(e) {{
            if (isSubmitted) return;
            var key = e.key;
            if (key >= '1' && key <= '4') {{
                e.preventDefault();
                var label = $('label_' + currentQuestion + '_' + (parseInt(key) - 1));
                if (label) label.click();
            }}
            if (key === 'ArrowDown' || key === 'ArrowRight') {{
                e.preventDefault();
                if (currentQuestion < TOTAL - 1) scrollToQuestion(currentQuestion + 1);
            }}
            if (key === 'ArrowUp' || key === 'ArrowLeft') {{
                e.preventDefault();
                if (currentQuestion > 0) scrollToQuestion(currentQuestion - 1);
            }}
            if (key === 'Enter') {{
                e.preventDefault();
                if (currentQuestion < TOTAL - 1) scrollToQuestion(currentQuestion + 1);
                else submitQuiz();
            }}
        }});

        // ═══════════════════════════════════════════════════════════════════════
        //  SCROLL TRACKING
        // ═══════════════════════════════════════════════════════════════════════
        function updateCurrentFromScroll() {{
            var cards = $$('.q-card');
            var center = window.scrollY + window.innerHeight / 2;
            for (var i = 0; i < cards.length; i++) {{
                var rect = cards[i].getBoundingClientRect();
                var top = rect.top + window.scrollY;
                var bottom = rect.bottom + window.scrollY;
                if (top <= center && bottom >= center) {{
                    currentQuestion = i;
                    updateNavButtons();
                    break;
                }}
            }}
        }}

        window.addEventListener('scroll', updateCurrentFromScroll, {{ passive: true }});

        // ═══════════════════════════════════════════════════════════════════════
        //  RESTORE PROGRESS
        // ═══════════════════════════════════════════════════════════════════════
        function restoreProgress() {{
            var saved = SafeStorage.get('ssc-quiz-progress');
            if (!saved) return;
            try {{
                var parsed = JSON.parse(saved);
                if (!parsed || Object.keys(parsed).length === 0) return;
                if (window.confirm('Resume previous progress?')) {{
                    answers = parsed;
                    Object.keys(answers).forEach(function(k) {{
                        var qIdx = parseInt(k);
                        var oIdx = answers[k];
                        var label = $('label_' + qIdx + '_' + oIdx);
                        if (label) {{
                            label.classList.add('selected');
                            var radio = label.querySelector('input[type="radio"]');
                            if (radio) radio.checked = true;
                        }}
                        var navBtn = $('nav_' + qIdx);
                        if (navBtn) navBtn.classList.add('answered');
                        var statusEl = $('status_' + qIdx);
                        if (statusEl) statusEl.textContent = 'Answered';
                        var qBox = $('q_box_' + qIdx);
                        if (qBox) qBox.setAttribute('data-status', 'answered');
                    }});
                    updateAnswered();
                }} else {{
                    SafeStorage.del('ssc-quiz-progress');
                }}
            }} catch(e) {{ SafeStorage.del('ssc-quiz-progress'); }}
        }}

        // ═══════════════════════════════════════════════════════════════════════
        //  INIT
        // ═══════════════════════════════════════════════════════════════════════
        updateTimer();
        updateAnswered();
        updateNavButtons();
        startTimer();
        setTimeout(restoreProgress, 300);

    }})();
    </script>
</body>
</html>"""

        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        return filename


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
