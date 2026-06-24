from fastapi import APIRouter
from pydantic import BaseModel
from services.pdf_qa_service import ask_pdf
from services.meeting_service import handle_meeting
from services.scheduler_service import add_scheduled_meeting
from services.parser import parse_meeting, is_past, resolve_ambiguous_date
 
from db.mongo import chat_collection, report_collection, meeting_collection
from state.chat_state import set_state, get_state, clear_state
from services.groq_client import ask_llm
import os
import re
import datetime
 
router = APIRouter()
 
 
class ChatRequest(BaseModel):
    user_id: str
    message: str
 
 
# =========================
# SAVE BOT RESPONSE
# =========================
def save_bot(user_id, msg):
    chat_collection.update_one(
        {"user_id": user_id},
        {"$push": {"messages": {"role": "bot", "message": msg}}},
        upsert=True
    )
 
 
# =========================
# NORMALIZERS
# =========================
def normalize_date(date_str):
    if not date_str:
        return None
    date_str = str(date_str).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str
    if re.match(r"^\d{1,2}-\d{2}-\d{4}$", date_str):
        try:
            return datetime.datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
        except ValueError:
            return date_str
    if re.match(r"^\d{1,2}/\d{2}/\d{4}$", date_str):
        try:
            return datetime.datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return date_str
    return date_str
 
 
def normalize_time(time_str):
    if not time_str:
        return None
    s = str(time_str).strip().lower().replace(".", "")
    for fmt in ("%I %p", "%I:%M %p"):
        try:
            return datetime.datetime.strptime(s.upper(), fmt).strftime("%H:%M")
        except Exception:
            pass
    try:
        return datetime.datetime.strptime(s, "%H:%M").strftime("%H:%M")
    except Exception:
        pass
    return None
 
 
# =========================
# PAST VALIDATION
# =========================
def validate_future(date_str, time_str):
    try:
        dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        now = datetime.datetime.now()
        if dt < now:
            if date_str < now.strftime("%Y-%m-%d"):
                return "date_past"
            return "time_past"
    except Exception:
        pass
    return None
 
 
# =========================
# APPLY AM/PM TO RAW HOUR
# =========================
def apply_ampm(raw_hour: int, ampm: str) -> str:
    hour = raw_hour
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"
 
 
# =========================
# SCHEDULE HELPER
# =========================
def do_schedule(user_id, date, time):
    return handle_meeting(user_id, f"schedule meeting {date} {time}")
 
 
# =========================
# CHECK IF MESSAGE IS MEANINGFUL DATETIME INPUT
# =========================
def _has_datetime_content(message: str) -> bool:
    parsed = parse_meeting(None, message)
    return bool(
        parsed.get("date") or
        parsed.get("time") or
        parsed.get("date_ambiguous") or
        message.strip().lower() in ("today", "tomorrow", "am", "pm")
    )
 
 
def _is_meeting_intent(msg_lower: str) -> bool:
    prompt = f"""You are an intent detector for a meeting scheduling chatbot.
 
User message: "{msg_lower}"
 
Does this message show intent to SCHEDULE, CREATE, BOOK, or ARRANGE a meeting or call?
 
RETURN YES if user wants to:
- Schedule/create/book/fix/arrange/plan a meeting or call
- Generate a meeting link
- Meet with someone (milna hai, milte hain, call karna, baat karni hai, etc.)
- Any English, Hindi, or Hinglish variation of the above
 
RETURN NO if user is:
- Asking a general knowledge question (what is a meeting, how long should meetings be)
- Talking about something completely unrelated
- Just saying or chatting
 
Return ONLY one word: YES or NO"""
 
    try:
        res = ask_llm(prompt)
        result = res.strip().upper()
        if "YES" in result:
            return True
        return False
    except Exception:
        return False


def _extract_month_hint(message: str):
    months = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    lower = message.strip().lower()
    for name, number in months.items():
        if re.search(rf"\b{name}\b", lower):
            return number
    return None


def _extract_year_hint(message: str):
    m = re.search(r"\b(20\d{2})\b", message)
    return int(m.group(1)) if m else None


def _extract_day_hint(message: str):
    cleaned = message.strip().lower()
    cleaned = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}\s*(?:am|pm)\b", " ", cleaned)
    cleaned = re.sub(r"\b(st|nd|rd|th)\b", "", cleaned)
    cleaned = re.sub(r"\b20\d{2}\b", " ", cleaned)
    numbers = re.findall(r"\b([0-3]?\d)\b", cleaned)
    valid_days = [int(n) for n in numbers if 1 <= int(n) <= 31]
    return valid_days[0] if len(valid_days) == 1 else None


def _resolve_bare_day(day: int):
    now = datetime.datetime.now()
    year = now.year
    month = now.month

    for _ in range(24):
        try:
            candidate = datetime.datetime(year, month, day)
            if candidate.date() >= now.date():
                return candidate.strftime("%Y-%m-%d")
        except ValueError:
            pass

        month += 1
        if month > 12:
            month = 1
            year += 1

    return None


def _resolve_month_day(month: int, day: int, year: int = None):
    now = datetime.datetime.now()
    candidate_year = year or now.year
    try:
        candidate = datetime.datetime(candidate_year, month, day)
    except ValueError:
        return None
    if year is None and candidate.date() < now.date():
        try:
            candidate = datetime.datetime(candidate_year + 1, month, day)
        except ValueError:
            return None
    return candidate.strftime("%Y-%m-%d")


def _is_smalltalk(message: str) -> bool:
    msg = re.sub(r"[^a-zA-Z\s]", " ", message.lower())
    msg = re.sub(r"\s+", " ", msg).strip()
    smalltalk_phrases = {
        "hi", "hello", "hey", "hii", "hiii", "good morning", "good afternoon",
        "good evening", "how are you", "how r you", "what's up", "whats up",
        "great", "thanks", "thank you", "ok", "okay",
    }
    return msg in smalltalk_phrases


def _has_collected_datetime_data(state: dict) -> bool:
    partial = state.get("partial") or {}
    return any(
        partial.get(key)
        for key in ("date", "time", "month_hint", "year_hint")
    ) or state.get("awaiting_ampm") or state.get("awaiting_date_confirm")
 
 
# =========================
# BUILD AMBIGUOUS CONFIRM MESSAGE
# =========================
def _ambiguous_confirm_msg(raw: str, p1: int, p2: int, year: str,
                            year_first: bool) -> str:
    if year_first:
        return (
            f"📅 Please confirm: in **{raw}**, "
            f"is **{p1:02d}** the month and **{p2:02d}** the day?\n"
            f'• Reply **"yes"** → {year}-{p1:02d}-{p2:02d} '
            f'(month={p1:02d}, day={p2:02d})\n'
            f'• Reply **"no"**  → {year}-{p2:02d}-{p1:02d} '
            f'(month={p2:02d}, day={p1:02d})'
        )
    else:
        return (
            f"📅 I need to confirm: in **{raw}**, "
            f"is **{p1}** the day or the month?\n"
            f'• Reply **"day"** or **"first is day"**   → '
            f'day={p1:02d}, month={p2:02d} ({p1:02d}-{p2:02d}-{year})\n'
            f'• Reply **"month"** or **"first is month"** → '
            f'day={p2:02d}, month={p1:02d} ({p2:02d}-{p1:02d}-{year})'
        )
 
 
def _ambiguous_retry_msg(raw: str, p1: int, p2: int, year: str,
                          year_first: bool) -> str:
    if year_first:
        return (
            f"❓ I couldn't understand. For **{raw}**, please reply:\n"
            f'• **"yes"** → {year}-{p1:02d}-{p2:02d} '
            f'(treats {p1:02d} as month, {p2:02d} as day)\n'
            f'• **"no"**  → {year}-{p2:02d}-{p1:02d} '
            f'(treats {p2:02d} as month, {p1:02d} as day)'
        )
    else:
        return (
            f"❓ I couldn't understand. For **{raw}**, please reply:\n"
            f'• "first is day"   → day={p1:02d}, month={p2:02d}\n'
            f'• "first is month" → day={p2:02d}, month={p1:02d}'
        )
 
 
# =========================
# LLM-BASED YES/NO DETECTION
# Positive response = YES, Negative response = NO
# Works for English, Hindi, Hinglish, mixed language
# =========================
def detect_yes_no_llm(message: str) -> str:
    """
    Returns: YES / NO / OTHER
    Positive/agreeing responses → YES
    Negative/disagreeing responses → NO
    Anything else → OTHER
    """
    prompt = f"""You are a response classifier. Your job is to detect if the user's message is a POSITIVE (agreeing) response or a NEGATIVE (disagreeing) response.
 
User message: "{message}"
 
Rules:
- POSITIVE responses mean: yes, agree, confirm, ok, sure, haan, bilkul, theek hai, kar do, ho jay, correct, right, sahi, proceed, go ahead, done, perfect, fine, absolutely, definitely — anything that shows AGREEMENT or CONFIRMATION
- NEGATIVE responses mean: no, disagree, nahi, mat karo, don't, not now, na, nope, cancel, wrong, incorrect, deny — anything that shows DISAGREEMENT or REFUSAL
- OTHER means: the message is a question, command, random text, or something completely unrelated to yes/no
 
Return ONLY one word: YES or NO or OTHER
Do not explain. Do not add punctuation."""
 
    try:
        res = ask_llm(prompt)
        result = res.strip().upper()
        if result in ("YES", "NO", "OTHER"):
            return result
        # Fallback parsing if model adds extra text
        if "YES" in result:
            return "YES"
        if "NO" in result:
            return "NO"
        return "OTHER"
    except Exception:
        return "OTHER"
 
 
# =========================
# LLM-BASED FLOW INTENT DETECTION
# Detects if user wants to CONTINUE, EXIT, or SWITCH
# =========================
# def detect_flow_intent_llm(message: str, current_step: str) -> str:
def detect_flow_intent_llm(message: str, current_step: str, state: dict = None) -> str:
    """
    Returns: CONTINUE / EXIT / SWITCH
    """
    # Hard-coded guard: bare yes/no (any language) is ALWAYS CONTINUE —
    # the step handler itself decides what to do with yes/no.
    _bare = message.strip().lower()
    _YES_WORDS = {
        "yes", "y", "yeah", "yep", "yup", "ok", "okay", "sure", "fine",
        "haan", "ha", "han", "bilkul", "theek hai", "theek", "kar do",
        "ho jay", "ho jaye", "correct", "right", "sahi", "proceed",
        "go ahead", "done", "perfect", "absolutely", "definitely",
    }
    _NO_WORDS = {
        "no", "n", "nope", "nah", "nahi", "na", "mat", "mat karo",
        "don't", "dont", "not now",
    }
    if _bare in _YES_WORDS or _bare in _NO_WORDS:
        return "CONTINUE"
 
    prompt = f"""You are an intelligent intent classifier for a chatbot assistant.
 
The user is currently in the middle of a process: "{current_step}"
User message: "{message}"
 
Your task is to classify the user's intent into ONE of these:
 
1. CONTINUE → User is providing the required information for the current step, or answering what was asked
   Examples: giving a date, giving a time, saying yes/no to a confirmation, answering am/pm, providing a day/month clarification
 
2. EXIT → User wants to stop, cancel, quit, or leave the current process entirely
   Examples (any language):
   - "stop", "cancel", "leave it", "chhodo", "nahi karna", "band karo", "baad mein", "rehne do", "mat karo", "quit", "exit", "not now", "forget it", "ignore it", "ruk jao"
 
3. SWITCH → User wants to do something completely different (a new task/command unrelated to current step)
   Examples:
   - "show report", "history dikhao", "new meeting schedule karo", "kuch aur batao", asking an unrelated question
 
IMPORTANT RULES:
- If user provides date, time, day, month, year → ALWAYS return CONTINUE
- If user says am/pm → ALWAYS return CONTINUE
- If user gives a positive/negative response (yes/no/haan/nahi) → ALWAYS return CONTINUE (they are answering a confirmation question)
- A single word "no" or "nahi" means the user is ANSWERING a yes/no question → return CONTINUE
- Only return EXIT if user says multi-word exit phrases like "cancel karo", "rehne do", "chhod do", "mat banao", "band karo"
- Only return SWITCH if user clearly wants a COMPLETELY DIFFERENT task
- When in doubt between CONTINUE and EXIT, prefer CONTINUE
- User can use English, Hindi, Hinglish, or mixed language
 
Return ONLY one word: CONTINUE or EXIT or SWITCH"""
 
    try:
        res = ask_llm(prompt)
        result = res.strip().upper()
        if result in ("CONTINUE", "EXIT", "SWITCH"):
            return result
        if "EXIT" in result:
            return "EXIT"
        if "SWITCH" in result:
            return "SWITCH"
        return "CONTINUE"
    except Exception:
        return "CONTINUE"
 
 
# =========================
# GENERATE EXIT RESPONSE
# =========================
def generate_exit_response(message: str, step: str, state: dict) -> str:
    prompt = f"""You are a friendly assistant.
 
The user was in the middle of: "{step}"
The user said: "{message}"
 
The user wants to stop/exit the current process.
 
Generate a natural, human-like response that:
- Acknowledges the exit politely
- Is short (1-2 lines max)
- Varies in tone (not repetitive)
- Can be in the same language the user used (English/Hindi/Hinglish)
 
Examples of good responses:
- "Alright, we can skip this for now."
- "No worries, we'll continue later."
- "Theek hai, chhod dete hain abhi."
- "Got it, stopping here."
 
Now generate a response:"""
 
    try:
        return ask_llm(prompt)
    except Exception:
        return "Okay, stopping here. Let me know if you need anything else."
 
 
# =========================
# SHARED COLLECT LOGIC
# =========================
def collect_datetime(message: str, state: dict) -> dict:
    partial   = dict(state.get("partial", {}))
    msg_lower = message.strip().lower()
    month_hint = _extract_month_hint(message)
    year_hint = _extract_year_hint(message)

    if month_hint:
        partial["month_hint"] = month_hint
    if year_hint:
        partial["year_hint"] = year_hint
 
    # Handle AM/PM answer
    if state.get("awaiting_ampm") and msg_lower in ("am", "pm"):
        raw_hour = state.get("raw_hour")
        if raw_hour is not None:
            partial["time"] = apply_ampm(int(raw_hour), msg_lower)
            partial["awaiting_ampm"] = False
 
    else:
        parsed = parse_meeting(None, message)
 
        # Ambiguous numeric date
        if parsed.get("date_ambiguous"):
            if parsed.get("time") and not partial.get("time"):
                if not parsed.get("time_needs_ampm"):
                    partial["time"] = normalize_time(parsed["time"]) or parsed["time"]
 
            year_first = parsed.get("ambiguous_year_first", False)
 
            new_state = {
                **state,
                "partial":               partial,
                "awaiting_ampm":         False,
                "awaiting_date_confirm": True,
                "ambiguous_p1":          parsed["ambiguous_p1"],
                "ambiguous_p2":          parsed["ambiguous_p2"],
                "ambiguous_year":        parsed["ambiguous_year"],
                "ambiguous_raw":         parsed["ambiguous_raw"],
                "ambiguous_year_first":  year_first,
            }
            return {
                "ready":     False,
                "message":   _ambiguous_confirm_msg(
                                 parsed["ambiguous_raw"],
                                 parsed["ambiguous_p1"],
                                 parsed["ambiguous_p2"],
                                 parsed["ambiguous_year"],
                                 year_first,
                             ),
                "new_state": new_state,
            }
 
        day_hint = _extract_day_hint(message)
        hinted_date = None
        if partial.get("month_hint") and day_hint:
            hinted_date = _resolve_month_day(
                int(partial["month_hint"]),
                int(day_hint),
                partial.get("year_hint"),
            )
        elif day_hint and not month_hint and not year_hint:
            hinted_date = _resolve_bare_day(int(day_hint))

        # Normal date
        if hinted_date:
            partial["date"] = hinted_date
        elif parsed.get("date"):
            new_date = normalize_date(parsed["date"])
            partial["date"] = new_date
 
        # Time
        if parsed.get("time"):
            if parsed.get("time_needs_ampm"):
                raw_hour_str = parsed["time"].split(":")[0]
                return {
                    "ready":   False,
                    "message": "🕐 Should I schedule this in AM or PM?",
                    "new_state": {
                        **state,
                        "partial":       partial,
                        "awaiting_ampm": True,
                        "raw_hour":      int(raw_hour_str),
                    }
                }
            else:
                partial["time"] = normalize_time(parsed["time"]) or parsed["time"]
 
    date = partial.get("date")
    time = partial.get("time")
 
    base_new_state = {
        **state,
        "partial":       partial,
        "awaiting_ampm": False,
    }
 
    if not date:
        return {
            "ready":     False,
            "message":   "📅 Please provide the date for the meeting (along with year and month)",
            "new_state": base_new_state,
        }
 
    if not time:
        return {
            "ready":     False,
            "message":   "⏰ Please provide the time for the meeting (like 3 pm or 3:00 pm)",
            "new_state": base_new_state,
        }
 
    err = validate_future(date, time)
    if err == "date_past":
        partial["date"] = None
        partial["time"] = None
        return {
            "ready":   False,
            "message": "⚠️ This date has already passed. Please provide a future date.",
            "new_state": {
                **state,
                "partial":       partial,
                "awaiting_ampm": False,
                "raw_hour":      None,
            },
        }
    elif err == "time_past":
        partial["time"] = None
        return {
            "ready":   False,
            "message": "⚠️ This time has already passed today. Please provide a future time.",
            "new_state": {
                **state,
                "partial":       partial,
                "awaiting_ampm": False,
                "raw_hour":      None,
            },
        }
 
    return {"ready": True, "date": date, "time": time}
 
 
# =========================
# HANDLE DATE CONFIRM REPLY
# =========================
def handle_date_confirm(message: str, state: dict) -> dict:
    year_first = state.get("ambiguous_year_first", False)
    p1         = state["ambiguous_p1"]
    p2         = state["ambiguous_p2"]
    year       = state["ambiguous_year"]
    raw        = state["ambiguous_raw"]
 
    msg_lower  = message.strip().lower()
 
    # Use LLM-based yes/no for year_first confirmation
    if year_first:
        yn = detect_yes_no_llm(message)
        if yn == "YES":
            first_is_day = False  # yes → p1 is month, p2 is day
        elif yn == "NO":
            first_is_day = True   # no → p1 is day, p2 is month
        else:
            first_is_day = None
 
        if first_is_day is not None:
            day, month = (p1, p2) if first_is_day else (p2, p1)
            try:
                resolved = datetime.datetime.strptime(
                    f"{year}-{month:02d}-{day:02d}", "%Y-%m-%d"
                ).strftime("%Y-%m-%d")
            except ValueError:
                resolved = None
        else:
            resolved = None
    else:
        resolved = resolve_ambiguous_date(
            p1=p1, p2=p2, year=year, raw=raw,
            user_reply=message,
            year_first=year_first,
        )
 
    if resolved is None:
        return {
            "ready":   False,
            "message": _ambiguous_retry_msg(raw, p1, p2, year, year_first),
            "new_state": state,
        }
 
    partial = dict(state.get("partial", {}))
    partial["date"] = resolved
 
    new_state = {
        **state,
        "partial":               partial,
        "awaiting_date_confirm": False,
        "ambiguous_p1":          None,
        "ambiguous_p2":          None,
        "ambiguous_year":        None,
        "ambiguous_raw":         None,
        "ambiguous_year_first":  None,
    }
 
    time = partial.get("time")
    if not time:
        return {
            "ready":     False,
            "message":   "⏰ Please provide the time for the meeting (e.g. 3 pm, 14:00)",
            "new_state": new_state,
        }
 
    err = validate_future(resolved, time)
    if err == "date_past":
        partial["date"] = None
        partial["time"] = None
        return {
            "ready":   False,
            "message": "⚠️ This date has already passed. Please provide a future date.",
            "new_state": {**new_state, "partial": partial, "awaiting_ampm": False},
        }
    elif err == "time_past":
        partial["time"] = None
        return {
            "ready":   False,
            "message": "⚠️ This time has already passed today. Please provide a future time.",
            "new_state": {**new_state, "partial": partial, "awaiting_ampm": False},
        }
 
    return {"ready": True, "date": resolved, "time": time}
 
 
# =========================
# SHARED STEP HANDLER
# =========================
def run_collect(message: str, state: dict):
    if state.get("awaiting_date_confirm"):
        return handle_date_confirm(message, state), True
    return collect_datetime(message, state), False
 
 
# =========================
# MAIN API
# =========================
@router.post("/chat")
def chat(req: ChatRequest):
 
    user_id   = req.user_id
    message   = req.message.strip()
    msg_lower = message.lower()
 
    chat_collection.update_one(
        {"user_id": user_id},
        {"$push": {"messages": {"role": "user", "message": message}}},
        upsert=True
    )
 
    state = get_state(user_id) or {}
 
    final_response = None
 
    NGROK_URL = "https://thud-delicate-emptiness.ngrok-free.dev"

    if (
        state.get("step") in ("collect", "update_collect")
        and not _has_collected_datetime_data(state)
        and _is_smalltalk(message)
    ):
        clear_state(user_id)
        state = {}
 
    # =========================
    # 🔥 FLOW CONTROL
    # Runs first whenever a step is active.
    # Uses LLM to detect if user wants to EXIT or SWITCH.
    # If user is CONTINUING the flow, let it fall through normally.
    # =========================
 
    step = state.get("step")
 
    if step:
        flow_intent = detect_flow_intent_llm(message, step)
 
        # 🚪 EXIT FLOW — user wants to stop current process
        if flow_intent == "EXIT":
            clear_state(user_id)
            final_response = generate_exit_response(message, step, state)
            save_bot(user_id, final_response)
            return {"message": final_response}
 
        # 🔄 SWITCH FLOW — user wants to do something else entirely
        elif flow_intent == "SWITCH":
            clear_state(user_id)
            state = {}
            step  = None
            # DO NOT RETURN — let message fall through to below logic
 
        # ✅ CONTINUE — user is providing required info, handle normally below
 
    # =====================================================
    # REPORT FLOW
    # =====================================================
    if "report" in msg_lower:
 
        report = report_collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)]
        )
 
        if not report or not report.get("pdf_report_path"):
            final_response = "📭 No report found"
        else:
            pdf_path = report.get("pdf_report_path")
            filename = os.path.basename(pdf_path).replace("\\", "/")
            pdf_url  = f"{NGROK_URL}/reports/{filename}"
 
            set_state(user_id, {"step": "pdf_confirm", "pdf_path": pdf_path})
 
            final_response = (
                f"📄 Report ready\n👉 {pdf_url}\n\n"
                f"❓ Do you want to ask questions from this PDF? (yes/no)"
            )
 
    # =====================================================
    # PDF CONFIRM
    # Uses LLM-based yes/no — positive = YES, negative = NO
    # =====================================================
    elif state.get("step") == "pdf_confirm":
 
        decision = detect_yes_no_llm(message)
 
        if decision == "YES":
            from services.pdf_qa_service import create_vector_db
            create_vector_db(user_id, state["pdf_path"])
 
            set_state(user_id, {
                "step":     "pdf_qa",
                "pdf_path": state["pdf_path"]
            })
 
            final_response = "🧠 Ask your question"
 
        elif decision == "NO":
            clear_state(user_id)
            final_response = "👍 Okay"
 
        else:
            # Still in flow — user didn't answer yes/no clearly, keep asking
            final_response = "❓ Please answer yes or no — do you want to ask questions from this PDF?"
 
    # =====================================================
    # PDF QA
    # EXIT is handled above in FLOW CONTROL
    # =====================================================
    elif state.get("step") == "pdf_qa":
        final_response = ask_pdf(user_id, message)
 
    # =====================================================
    # HISTORY
    # =====================================================
    elif "history" in msg_lower:
 
        doc = chat_collection.find_one({"user_id": user_id})
        if not doc:
            final_response = "📭 No history"
        else:
            msgs = doc.get("messages", [])[-10:]
            final_response = "\n".join([f"{m['role']}: {m['message']}" for m in msgs])
 
    # =====================================================
    # PREVIOUS MEETING
    # =====================================================
    elif any(k in msg_lower for k in ("previous meeting", "last meeting", "show my meeting")):
 
        meeting = meeting_collection.find_one(
            {"user_id": user_id},
            sort=[("created_at", -1)]
        )
 
        if not meeting:
            final_response = "📭 No meeting found"
        else:
            set_state(user_id, {"step": "ask_update", "meeting_data": meeting})
 
            final_response = (
                f"📅 Last Meeting:\n"
                f"📅 Date: {meeting.get('date')}\n"
                f"⏰ Time: {meeting.get('time')}\n"
                f"👉 {meeting.get('meeting_url')}\n\n"
                f"Do you want to update this meeting? (yes/no)"
            )
 
    # =====================================================
    # ASK UPDATE
    # Uses LLM-based yes/no
    # =====================================================
    elif state.get("step") == "ask_update":
 
        decision = detect_yes_no_llm(message)
 
        if decision == "YES":
            set_state(user_id, {
                "step":                  "update_collect",
                "meeting_data":          state.get("meeting_data"),
                "partial":               {},
                "awaiting_ampm":         False,
                "awaiting_date_confirm": False,
                "ambiguous_year_first":  None,
                "raw_hour":              None,
            })
            final_response = "🔄 Please provide the new date and time for the meeting"
 
        elif decision == "NO":
            clear_state(user_id)
            final_response = "👍 Okay"
 
        else:
            # Keep user in flow — they didn't answer clearly
            meeting = state.get("meeting_data", {})
            final_response = (
                f"❓ Please reply yes or no — do you want to update this meeting?\n"
                f"📅 Date: {meeting.get('date')}\n"
                f"⏰ Time: {meeting.get('time')}"
            )
 
    # =====================================================
    # UPDATE COLLECT
    # =====================================================
    # =====================================================
    # UPDATE COLLECT
    # EXIT/SWITCH already handled above in FLOW CONTROL.
    # Always call run_collect — it decides what to ask next.
    # =====================================================
    elif state.get("step") == "update_collect":
 
        result, _ = run_collect(message, state)
 
        if not result["ready"]:
            set_state(user_id, result["new_state"])
            final_response = result["message"]
        else:
            date, time = result["date"], result["time"]
            old = state.get("meeting_data", {})
            set_state(user_id, {
                "step":         "update_confirm",
                "meeting_data": old,
                "new_data":     {"date": date, "time": time},
            })
            final_response = (
                f"📌 Updated Preview:\n"
                f"📅 Date: {date}\n"
                f"⏰ Time: {time}\n"
                f"👉 {old.get('meeting_url')}\n\n"
                f"Confirm update? (yes/no)"
            )
 
    # =====================================================
    # UPDATE CONFIRM
    # Uses LLM-based yes/no
    # =====================================================
    elif state.get("step") == "update_confirm":
 
        decision = detect_yes_no_llm(message)
 
        if decision == "YES":
 
            new_data = state.get("new_data", {})
            old      = state.get("meeting_data", {})
 
            set_state(user_id, {
                "event_id": old.get("event_id"),
                "new_meeting": {
                    "date": new_data["date"],
                    "time": new_data["time"],
                },
            })
 
            res = handle_meeting(user_id, "update_meeting")
 
            if not res or not res.get("meeting_url"):
                return {"message": "❌ Failed to update meeting"}
 
            meeting_url = old.get("meeting_url") or res.get("meeting_url")
            event_id    = old.get("event_id") or res.get("event_id")
 
            set_state(user_id, {
                "step": "bot_join_confirm",
                "meeting_data": {
                    **res,
                    "event_id":    event_id,
                    "meeting_url": meeting_url,
                    "date":        new_data["date"],
                    "time":        new_data["time"],
                }
            })
 
            final_response = (
                f"✅ Meeting Updated\n"
                f"📅 Date: {new_data['date']}\n"
                f"⏰ Time: {new_data['time']}\n"
                f"👉 {meeting_url}\n\n"
                f"🤖 Should the bot join this meeting? (yes/no)"
            )
 
        elif decision == "NO":
            # Go back to re-enter date/time
            set_state(user_id, {
                "step":                  "update_collect",
                "meeting_data":          state.get("meeting_data"),
                "partial":               {},
                "awaiting_ampm":         False,
                "awaiting_date_confirm": False,
                "ambiguous_year_first":  None,
                "raw_hour":              None,
            })
            final_response = "🔄 Please enter the new date and time again"
 
        else:
            # Keep user in flow — didn't answer clearly
            new_data = state.get("new_data", {})
            old_mtg  = state.get("meeting_data", {})
            final_response = (
                f"📌 Please reply yes or no to confirm this update:\n"
                f"📅 Date: {new_data.get('date')}\n"
                f"⏰ Time: {new_data.get('time')}\n"
                f"👉 {old_mtg.get('meeting_url')}"
            )
 
    # =====================================================
    # NEW MEETING — Trigger detection
    # Handles English + Hindi + Hinglish scheduling intent
    # =====================================================
    elif state.get("step") != "collect" and _is_meeting_intent(msg_lower):
 
        fresh_state = {
            "step":                  "collect",
            "partial":               {},
            "awaiting_ampm":         False,
            "awaiting_date_confirm": False,
            "ambiguous_year_first":  None,
            "raw_hour":              None,
        }
 
        result, _ = run_collect(message, fresh_state)
 
        if not result["ready"]:
            set_state(user_id, result["new_state"])
            final_response = result["message"]
        else:
            date, time = result["date"], result["time"]
            set_state(user_id, {
                "step":         "new_meeting_confirm",
                "pending_date": date,
                "pending_time": time,
            })
            final_response = (
                f"📋 Meeting Details:\n"
                f"📅 Date: {date}\n"
                f"⏰ Time: {time}\n\n"
                f"Do you want to confirm this meeting? (yes/no)"
            )
 
    # =====================================================
    # COLLECT (follow-up messages for missing date/time)
    # EXIT/SWITCH already handled above in FLOW CONTROL.
    # Always call run_collect — it decides what to ask next.
    # =====================================================
    elif state.get("step") == "collect":
 
        result, _ = run_collect(message, state)
 
        if not result["ready"]:
            set_state(user_id, result["new_state"])
            final_response = result["message"]
        else:
            date, time = result["date"], result["time"]
            set_state(user_id, {
                "step":         "new_meeting_confirm",
                "pending_date": date,
                "pending_time": time,
            })
            final_response = (
                f"📋 Meeting Details:\n"
                f"📅 Date: {date}\n"
                f"⏰ Time: {time}\n\n"
                f"Do you want to confirm this meeting? (yes/no)"
            )
 
    # =====================================================
    # NEW MEETING CONFIRM
    # Uses LLM-based yes/no
    # =====================================================
    elif state.get("step") == "new_meeting_confirm":
 
        date = state.get("pending_date")
        time = state.get("pending_time")
 
        decision = detect_yes_no_llm(message)
 
        if decision == "YES":
 
            res = do_schedule(user_id, date, time)
 
            if not res or not res.get("meeting_url"):
                return {"message": "❌ Failed to create meeting"}
 
            set_state(user_id, {
                "step":         "bot_join_confirm",
                "meeting_data": {**res, "date": date, "time": time},
            })
 
            final_response = (
                f"📅 Meeting Created\n"
                f"📅 Date: {date}\n"
                f"⏰ Time: {time}\n"
                f"👉 {res['meeting_url']}\n\n"
                f"🤖 Should the bot join this meeting? (yes/no)"
            )
 
        elif decision == "NO":
            set_state(user_id, {
                "step":                  "collect",
                "partial":               {},
                "awaiting_ampm":         False,
                "awaiting_date_confirm": False,
                "ambiguous_year_first":  None,
                "raw_hour":              None,
            })
            final_response = "🔄 Please provide a new date and time for the meeting"
 
        else:
            # Keep user in flow — didn't answer clearly
            final_response = (
                f"📋 Please reply yes or no to confirm this meeting:\n"
                f"📅 Date: {date}\n"
                f"⏰ Time: {time}"
            )
 
    # =====================================================
    # BOT JOIN CONFIRM
    # Reached from BOTH new meeting and update meeting flows.
    # Uses LLM-based yes/no
    # =====================================================
    elif state.get("step") == "bot_join_confirm":
 
        data     = state.get("meeting_data") or {}
        decision = detect_yes_no_llm(message)
 
        if decision == "YES":
 
            raw_time = normalize_time(data.get("time"))
            if not raw_time:
                set_state(user_id, {
                    "step":                  "update_collect",
                    "meeting_data":          data,
                    "partial":               {"date": data.get("date")},
                    "awaiting_ampm":         False,
                    "awaiting_date_confirm": False,
                    "ambiguous_year_first":  None,
                    "raw_hour":              None,
                })
                return {"message": "❌ Invalid time. Please re-enter (e.g. 7 pm or 14:00)"}
 
            try:
                start_dt = datetime.datetime.strptime(
                    f"{data['date']} {raw_time}", "%Y-%m-%d %H:%M"
                )
            except Exception:
                set_state(user_id, {
                    "step":                  "update_collect",
                    "meeting_data":          data,
                    "partial":               {},
                    "awaiting_ampm":         False,
                    "awaiting_date_confirm": False,
                    "ambiguous_year_first":  None,
                    "raw_hour":              None,
                })
                return {"message": "❌ Invalid date/time. Please re-enter"}
 
            add_scheduled_meeting(
                job_id=data["event_id"],
                meeting_url=data["meeting_url"],
                scheduled_at_iso=start_dt.isoformat(),
                user_id=user_id,
            )
 
            clear_state(user_id)
 
            final_response = (
                f"🤖 Bot Scheduled\n"
                f"👉 {data.get('meeting_url')}\n"
                f"🕒 {data.get('date')} {data.get('time')}"
            )
 
        elif decision == "NO":
            clear_state(user_id)
 
            final_response = (
                f"✅ Meeting Confirmed (No Bot)\n"
                f"👉 {data.get('meeting_url')}\n"
                f"🕒 {data.get('date')} {data.get('time')}"
            )
 
        else:
            # Keep user in flow — didn't answer clearly
            final_response = (
                f"❓ Please reply yes or no:\n"
                f"🤖 Should the bot join this meeting at {data.get('time')} on {data.get('date')}?"
            )
 
    # =====================================================
    # FALLBACK — LLM (Maya)
    # Only reached when NO flow is active
    # =====================================================
    if final_response is None:
        final_response = ask_llm(message)
 
    save_bot(user_id, final_response)
    return {"message": final_response}
 
