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
    ULTRA-SIMPLE MOCK TEST GENERATOR v3.3
    Designed for maximum compatibility with Telegram WebView / Android
    No fancy CSS, no pointer-events tricks, no event delegation
    Just plain old reliable HTML with inline onclick
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
            nav_buttons += f'                <button class="nav-btn" id="nav_{i}" onclick="goToQ({i})">{i+1}</button>\n'

        # Build question cards
        question_cards = ""
        for idx, q in enumerate(shuffled_questions):
            options_html = ""
            for o_idx, opt in enumerate(q["options"]):
                options_html += f"""
                    <button class="opt-btn" id="opt_{idx}_{o_idx}" onclick="selectOpt({idx},{o_idx})">
                        <span class="opt-letter">{chr(65+o_idx)}</span>
                        <span class="opt-text">{opt}</span>
                    </button>"""

            question_cards += f"""
            <div class="q-card" id="q_box_{idx}">
                <div class="q-header">
                    <span class="q-badge">QUESTION {idx+1}</span>
                    <span class="q-status" id="status_{idx}">Not answered</span>
                </div>
                <div class="q-text">{q['question']}</div>
                <input type="hidden" id="ans_key_{idx}" value="{q['correct_idx']}">
                <div class="opts">
                    {options_html}
                </div>
                <div class="exp-box" id="exp_{idx}">
                    <div class="exp-title">📖 Explanation</div>
                    <div class="exp-body">{q['explanation']}</div>
                </div>
            </div>"""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>SSC MTS {subject.upper()} Mock Test</title>
    <style>
        :root {{ --p: #1a365d; --pl: #2c5282; --a: #dd6b20; --ok: #276749; --okbg: #c6f6d5; --bad: #c53030; --badbg: #fed7d7; --bg: #f7fafc; --s: #fff; --t: #1a202c; --t2: #4a5568; --b: #e2e8f0; }}
        [data-theme="dark"] {{ --p: #63b3ed; --pl: #4299e1; --a: #f6ad55; --ok: #68d391; --okbg: #22543d; --bad: #fc8181; --badbg: #742a2a; --bg: #0d1117; --s: #161b22; --t: #e2e8f0; --t2: #a0aec0; --b: #30363d; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--t); line-height: 1.6; min-height: 100vh; }}
        .hdr {{ background: linear-gradient(135deg, var(--p) 0%, var(--pl) 100%); color: white; padding: 16px; position: sticky; top: 0; z-index: 100; }}
        .hdr-c {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .hdr h1 {{ font-size: 1.1rem; font-weight: 700; }}
        .hdr-m {{ font-size: 0.75rem; opacity: 0.9; margin-top: 2px; }}
        .hdr-btns {{ display: flex; gap: 8px; }}
        .ibtn {{ background: rgba(255,255,255,0.2); border: none; color: white; width: 36px; height: 36px; border-radius: 8px; font-size: 1.1rem; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
        .tmr {{ background: var(--s); border-bottom: 1px solid var(--b); padding: 10px 16px; position: sticky; top: 60px; z-index: 99; }}
        .tmr-c {{ max-width: 900px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
        .tmr-t {{ font-family: monospace; font-size: 1.3rem; font-weight: 700; color: var(--p); }}
        .tmr-t.red {{ color: var(--bad); animation: pulse 1s infinite; }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.5}} }}
        .nav {{ background: var(--s); border-bottom: 1px solid var(--b); padding: 12px 16px; position: sticky; top: 100px; z-index: 98; }}
        .nav-l {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase; color: var(--t2); margin-bottom: 8px; }}
        .nav-g {{ display: grid; grid-template-columns: repeat(10, 1fr); gap: 5px; }}
        .nav-btn {{ border: 2px solid var(--b); background: var(--s); color: var(--t); border-radius: 6px; font-family: monospace; font-weight: 600; font-size: 0.8rem; cursor: pointer; padding: 6px; }}
        .nav-btn.on {{ border-color: var(--ok); background: var(--okbg); color: var(--ok); }}
        .nav-btn.cur {{ box-shadow: 0 0 0 2px var(--a); }}
        .wrap {{ max-width: 900px; margin: 0 auto; padding: 16px 16px 100px; }}
        .q-card {{ background: var(--s); border: 1px solid var(--b); border-radius: 12px; padding: 18px; margin-bottom: 16px; scroll-margin-top: 160px; }}
        .q-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .q-badge {{ font-family: monospace; font-size: 0.7rem; font-weight: 600; color: var(--a); background: var(--bg); padding: 3px 10px; border-radius: 20px; }}
        .q-status {{ font-size: 0.75rem; color: var(--t2); }}
        .q-text {{ font-size: 1rem; font-weight: 600; line-height: 1.6; margin-bottom: 14px; }}
        .opts {{ display: flex; flex-direction: column; gap: 8px; }}
        .opt-btn {{ display: flex; align-items: center; gap: 12px; background: var(--bg); border: 2px solid var(--b); padding: 14px 16px; border-radius: 8px; cursor: pointer; font-family: inherit; font-size: 0.95rem; color: var(--t); text-align: left; width: 100%; }}
        .opt-btn:active {{ transform: scale(0.98); }}
        .opt-btn.sel {{ border-color: var(--p); background: rgba(26,54,93,0.08); }}
        .opt-btn.ok {{ border-color: var(--ok); background: var(--okbg); }}
        .opt-btn.bad {{ border-color: var(--bad); background: var(--badbg); }}
        .opt-letter {{ font-family: monospace; font-weight: 700; font-size: 0.9rem; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: var(--s); border: 2px solid var(--b); border-radius: 50%; flex-shrink: 0; }}
        .opt-btn.sel .opt-letter {{ background: var(--p); border-color: var(--p); color: white; }}
        .opt-btn.ok .opt-letter {{ background: var(--ok); border-color: var(--ok); color: white; }}
        .opt-btn.bad .opt-letter {{ background: var(--bad); border-color: var(--bad); color: white; }}
        .opt-text {{ flex: 1; }}
        .exp-box {{ display: none; margin-top: 14px; padding: 14px; background: #fff2cc; border-left: 4px solid var(--a); border-radius: 6px; }}
        .exp-title {{ font-weight: 700; color: var(--a); margin-bottom: 6px; }}
        .exp-body {{ color: var(--t2); font-size: 0.9rem; line-height: 1.6; }}
        .fab {{ position: fixed; bottom: 0; left: 0; right: 0; background: var(--s); border-top: 1px solid var(--b); padding: 12px 16px; box-shadow: 0 -4px 20px rgba(0,0,0,0.1); z-index: 1000; display: flex; justify-content: center; gap: 10px; }}
        .fab-c {{ max-width: 900px; width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
        .btn {{ padding: 12px 16px; border: none; border-radius: 8px; font-weight: 600; font-size: 0.85rem; cursor: pointer; flex: 1; text-align: center; font-family: inherit; }}
        .btn-p {{ background: linear-gradient(135deg, var(--p) 0%, var(--pl) 100%); color: white; }}
        .btn-s {{ background: var(--bg); color: var(--t); border: 2px solid var(--b); }}
        .btn:disabled {{ opacity: 0.5; }}
        .score {{ display: none; background: var(--okbg); border: 2px solid var(--ok); border-radius: 12px; padding: 24px; margin-bottom: 24px; text-align: center; }}
        .score-e {{ font-size: 2.5rem; margin-bottom: 8px; }}
        .score-p {{ font-family: monospace; font-size: 2rem; font-weight: 700; color: var(--ok); margin: 12px 0; }}
        .score-s {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }}
        .stat {{ background: var(--s); padding: 12px; border-radius: 8px; border: 1px solid var(--b); }}
        .stat-v {{ font-family: monospace; font-size: 1.3rem; font-weight: 700; }}
        .stat-l {{ font-size: 0.75rem; color: var(--t2); margin-top: 4px; }}
        .rev {{ display: none; justify-content: center; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
        .rev.on {{ display: flex; }}
        .rev-btn {{ padding: 8px 14px; border: 2px solid var(--b); background: var(--s); border-radius: 20px; cursor: pointer; font-size: 0.8rem; font-weight: 500; font-family: inherit; }}
        .rev-btn.on {{ border-color: var(--p); background: var(--p); color: white; }}
        @media (max-width: 600px) {{ .nav-g {{ grid-template-columns: repeat(5, 1fr); }} .hdr h1 {{ font-size: 1rem; }} .score-s {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <header class="hdr">
        <div class="hdr-c">
            <div>
                <h1>📋 SSC MTS {subject.upper()} Mock Test</h1>
                <div class="hdr-m">{datetime.now().strftime('%d %b %Y')} | {total_questions} Qs | 10 Min</div>
            </div>
            <div class="hdr-btns">
                <button class="ibtn" onclick="toggleTheme()">🌙</button>
                <button class="ibtn" onclick="window.print()">🖨️</button>
            </div>
        </div>
    </header>

    <div class="tmr">
        <div class="tmr-c">
            <div class="tmr-t" id="tmr">⏱️ <span id="tmrT">10:00</span></div>
            <div style="font-size:0.8rem;color:var(--t2);"><span id="ansC">0</span>/{total_questions} Answered</div>
        </div>
    </div>

    <div class="nav">
        <div class="nav-l">Question Navigator</div>
        <div class="nav-g" id="navG">
{nav_buttons}
        </div>
    </div>

    <div class="wrap">
        <div id="score" class="score">
            <div class="score-e" id="scE">🎉</div>
            <div id="scT">Test Completed!</div>
            <div class="score-p" id="scP">0%</div>
            <div id="scD">0 / 0 correct</div>
            <div class="score-s">
                <div class="stat"><div class="stat-v" id="stC" style="color:var(--ok)">0</div><div class="stat-l">Correct</div></div>
                <div class="stat"><div class="stat-v" id="stW" style="color:var(--bad)">0</div><div class="stat-l">Wrong</div></div>
                <div class="stat"><div class="stat-v" id="stTm">0:00</div><div class="stat-l">Time Taken</div></div>
            </div>
        </div>

        <div id="rev" class="rev">
            <button class="rev-btn on" onclick="filter('all')">All</button>
            <button class="rev-btn" onclick="filter('correct')">✓ Correct</button>
            <button class="rev-btn" onclick="filter('wrong')">✗ Wrong</button>
            <button class="rev-btn" onclick="filter('unattempted')">? Unattempted</button>
        </div>

        <div id="quiz">
{question_cards}
        </div>
    </div>

    <div class="fab">
        <div class="fab-c">
            <button class="btn btn-s" id="prevB" onclick="prevQ()">← Previous</button>
            <button class="btn btn-p" id="subB" onclick="submit()">🚀 Submit</button>
            <button class="btn btn-s" id="nextB" onclick="nextQ()">Next →</button>
        </div>
    </div>

    <script>
    // Safe storage wrapper
    var SS = {{
        m: {{}}, ok: false,
        init: function() {{ try {{ localStorage.setItem('__t','1'); localStorage.removeItem('__t'); this.ok=true; }} catch(e){{}} }},
        get: function(k) {{ if(this.ok) try {{ var v=localStorage.getItem(k); if(v) return v; }} catch(e){{}} return this.m[k]||null; }},
        set: function(k,v) {{ this.m[k]=v; if(this.ok) try {{ localStorage.setItem(k,v); }} catch(e){{}} }},
        del: function(k) {{ delete this.m[k]; if(this.ok) try {{ localStorage.removeItem(k); }} catch(e){{}} }}
    }};
    SS.init();

    var TOTAL = {total_questions};
    var TL = 600;
    var tLeft = TL;
    var tInt = null;
    var st = Date.now();
    var curQ = 0;
    var ans = {{}};
    var sub = false;

    function $(id) {{ return document.getElementById(id); }}

    // Theme
    function setTheme(th) {{ document.documentElement.setAttribute('data-theme', th); SS.set('th', th); }}
    function toggleTheme() {{ setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'); }}
    var sth = SS.get('th');
    if(sth) setTheme(sth);
    else if(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) setTheme('dark');

    // Timer
    function updTmr() {{
        var m = Math.floor(tLeft/60), s = tLeft%60;
        $('tmrT').textContent = m + ':' + (s<10?'0':'') + s;
        if(tLeft <= 60) $('tmr').classList.add('red');
    }}
    function updAns() {{ $('ansC').textContent = Object.keys(ans).length; }}
    function startTmr() {{
        if(tInt) return;
        tInt = setInterval(function() {{
            tLeft--; updTmr(); updAns();
            if(tLeft <= 0) {{ clearInterval(tInt); tInt=null; submit(true); }}
        }}, 1000);
    }}

    // Navigation
    function goToQ(idx) {{
        if(idx < 0 || idx >= TOTAL) return;
        curQ = idx;
        var el = $('q_box_' + idx);
        if(el) el.scrollIntoView({{behavior:'smooth', block:'center'}});
        updateNav();
    }}
    function updateNav() {{
        $('prevB').disabled = curQ === 0;
        $('nextB').textContent = curQ === TOTAL-1 ? 'Submit →' : 'Next →';
        var btns = document.querySelectorAll('.nav-btn');
        for(var i=0; i<btns.length; i++) btns[i].classList.toggle('cur', i === curQ);
    }}
    function prevQ() {{ goToQ(curQ - 1); }}
    function nextQ() {{ if(curQ < TOTAL-1) goToQ(curQ + 1); else submit(); }}

    // Option selection
    function selectOpt(qIdx, oIdx) {{
        if(sub) return;
        // Clear previous selection
        var qBox = $('q_box_' + qIdx);
        if(qBox) {{
            var btns = qBox.querySelectorAll('.opt-btn');
            for(var i=0; i<btns.length; i++) btns[i].classList.remove('sel');
        }}
        // Select new
        var btn = $('opt_' + qIdx + '_' + oIdx);
        if(btn) btn.classList.add('sel');
        // Record
        ans[qIdx] = oIdx;
        var nb = $('nav_' + qIdx);
        if(nb) nb.classList.add('on');
        var stEl = $('status_' + qIdx);
        if(stEl) stEl.textContent = 'Answered';
        if(qBox) qBox.setAttribute('data-st', 'answered');
        updAns();
        SS.set('prog', JSON.stringify(ans));
        // Auto advance
        if(qIdx < TOTAL-1) setTimeout(function() {{ goToQ(qIdx + 1); }}, 400);
    }}

    // Submit
    function submit(auto) {{
        var answered = Object.keys(ans).length;
        if(!auto && answered < TOTAL) {{
            if(!confirm(answered + '/' + TOTAL + ' answered. Submit anyway?')) return;
        }}
        sub = true;
        if(tInt) {{ clearInterval(tInt); tInt = null; }}

        var score = 0, correct = 0, wrong = 0;
        for(var i=0; i<TOTAL; i++) {{
            var ak = $('ans_key_' + i);
            if(!ak) continue;
            var ci = parseInt(ak.value);
            var sel = ans[i];
            var qBox = $('q_box_' + i);

            if(qBox) {{
                var btns = qBox.querySelectorAll('.opt-btn');
                for(var j=0; j<btns.length; j++) btns[j].classList.remove('sel');
            }}

            if(sel !== undefined) {{
                if(sel === ci) {{
                    score++; correct++;
                    var el = $('opt_' + i + '_' + sel);
                    if(el) el.classList.add('ok');
                }} else {{
                    wrong++;
                    var el1 = $('opt_' + i + '_' + sel);
                    if(el1) el1.classList.add('bad');
                    var el2 = $('opt_' + i + '_' + ci);
                    if(el2) el2.classList.add('ok');
                }}
            }} else {{
                var el = $('opt_' + i + '_' + ci);
                if(el) el.classList.add('ok');
            }}

            var exp = $('exp_' + i);
            if(exp) exp.style.display = 'block';
            if(qBox) qBox.setAttribute('data-st', sel===undefined ? 'unattempted' : (sel===ci ? 'correct' : 'wrong'));
        }}

        var pct = Math.round((score/TOTAL)*100);
        var tt = Math.round((Date.now()-st)/1000);
        var tm = Math.floor(tt/60), ts = tt%60;

        $('scE').textContent = pct>=80 ? '🏆' : pct>=60 ? '👍' : pct>=40 ? '📖' : '💪';
        $('scT').textContent = pct>=80 ? 'Outstanding!' : pct>=60 ? 'Good Job!' : pct>=40 ? 'Keep Practicing!' : "Don't Give Up!";
        $('scP').textContent = pct + '%';
        $('scD').textContent = score + ' / ' + TOTAL + ' correct';
        $('stC').textContent = correct;
        $('stW').textContent = wrong;
        $('stTm').textContent = tm + ':' + (ts<10?'0':'') + ts;

        $('score').style.display = 'block';
        $('rev').classList.add('on');
        $('subB').style.display = 'none';
        $('nextB').style.display = 'none';
        $('prevB').style.display = 'none';

        SS.set('last', JSON.stringify({{subject:'{subject}', score:score, total:TOTAL, pct:pct, correct:correct, wrong:wrong, tt:tt}}));
        SS.del('prog');
        window.scrollTo({{top:0, behavior:'smooth'}});
    }}

    // Review filters
    function filter(f) {{
        var btns = document.querySelectorAll('.rev-btn');
        for(var i=0; i<btns.length; i++) btns[i].classList.remove('on');
        event.target.classList.add('on');
        var cards = document.querySelectorAll('.q-card');
        for(var i=0; i<cards.length; i++) {{
            cards[i].style.display = (f === 'all' || cards[i].getAttribute('data-st') === f) ? 'block' : 'none';
        }}
    }}

    // Keyboard
    document.addEventListener('keydown', function(e) {{
        if(sub) return;
        var key = e.key;
        if(key >= '1' && key <= '4') {{ e.preventDefault(); selectOpt(curQ, parseInt(key)-1); }}
        if(key === 'ArrowDown' || key === 'ArrowRight') {{ e.preventDefault(); if(curQ < TOTAL-1) goToQ(curQ+1); }}
        if(key === 'ArrowUp' || key === 'ArrowLeft') {{ e.preventDefault(); if(curQ > 0) goToQ(curQ-1); }}
        if(key === 'Enter') {{ e.preventDefault(); if(curQ < TOTAL-1) goToQ(curQ+1); else submit(); }}
    }});

    // Scroll tracking
    window.addEventListener('scroll', function() {{
        var cards = document.querySelectorAll('.q-card');
        var c = window.scrollY + window.innerHeight/2;
        for(var i=0; i<cards.length; i++) {{
            var r = cards[i].getBoundingClientRect();
            var t = r.top + window.scrollY, b = r.bottom + window.scrollY;
            if(t <= c && b >= c) {{ curQ = i; updateNav(); break; }}
        }}
    }}, {{passive:true}});

    // Restore progress
    function restore() {{
        var saved = SS.get('prog');
        if(!saved) return;
        try {{
            var p = JSON.parse(saved);
            if(!p || Object.keys(p).length === 0) return;
            if(!confirm('Resume previous progress?')) {{ SS.del('prog'); return; }}
            ans = p;
            var keys = Object.keys(ans);
            for(var i=0; i<keys.length; i++) {{
                var qIdx = parseInt(keys[i]), oIdx = ans[keys[i]];
                var btn = $('opt_' + qIdx + '_' + oIdx);
                if(btn) btn.classList.add('sel');
                var nb = $('nav_' + qIdx);
                if(nb) nb.classList.add('on');
                var stEl = $('status_' + qIdx);
                if(stEl) stEl.textContent = 'Answered';
                var qBox = $('q_box_' + qIdx);
                if(qBox) qBox.setAttribute('data-st', 'answered');
            }}
            updAns();
        }} catch(e) {{ SS.del('prog'); }}
    }}

    // Init
    updTmr(); updAns(); updateNav(); startTmr();
    setTimeout(restore, 300);
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

        max_attempts = len(self.providers)
        attempt = 0
        quiz_data = None

        while attempt < max_attempts:
            if (time.time() - self.start_time) > ConfigManager.RUN_DURATION_SECONDS:
                Logger.warning("Time limit reached during retries. Stopping.", subject)
                return False

            quiz_data, rotate = self.provider_engine.fetch_quiz(
                subject, 
                subject_config["description"]
            )

            if quiz_data:
                break  # Success!

            if rotate:
                Logger.warning(f"Provider rotated (attempt {attempt + 1}/{max_attempts})", subject)
                attempt += 1
                continue

            # Not rotate but failed — try once more
            Logger.warning(f"Retry attempt {attempt + 1}/{max_attempts}", subject)
            attempt += 1

        if not quiz_data:
            Logger.error(f"Failed to generate quiz data after {max_attempts} attempts", subject)
            return True  # Continue to next subject

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
