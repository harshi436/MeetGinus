"""
parser.py
─────────
Extracts date and time from free-form user text.
 
AMBIGUITY RULE (DETERMINISTIC):
  When a numeric date has BOTH non-year parts ≤ 12,
  it is ALWAYS treated as ambiguous — no LLM call, no guessing.
  parse_meeting returns date_ambiguous=True and the caller asks
  the user to confirm day vs month.
 
  This applies to ALL numeric formats including year-first:
    YYYY-MM-DD → ambiguous if both MM and DD ≤ 12
    YYYY/MM/DD → ambiguous if both MM and DD ≤ 12
    DD-MM-YYYY → ambiguous if both DD and MM ≤ 12
    DD/MM/YYYY → ambiguous if both DD and MM ≤ 12
 
  The LLM is used ONLY in resolve_ambiguous_date(), after the
  user has replied, to interpret their natural language response.
 
KEY DESIGN:
  Time is extracted FIRST and its matched text is stripped from the
  input before date extraction runs. This prevents dateparser from
  confusing bare hour digits (e.g. "at 3") with day-of-month values.
 
  year_first flag is stored in ambiguous result so chat.py can show
  a format-appropriate confirmation message to the user.
 
SUPPORTED DATE FORMATS:
  YYYY-MM-DD         → ambiguous if both parts ≤ 12, else unambiguous
  YYYY/MM/DD         → ambiguous if both parts ≤ 12, else unambiguous
  DD-MM-YYYY         → unambiguous if day > 12
  MM-DD-YYYY         → unambiguous if month part > 12 is impossible
  DD/MM/YYYY         → same rules as DD-MM-YYYY
  Natural language   → "8 June 2026", "June 8, 2026" → always unambiguous
  Relative           → today, tomorrow, next monday, etc.
"""
 
import re
import json
import dateparser
from datetime import datetime, timedelta
from groq import Groq
from config.config import GROQ_API_KEY
 
_groq = Groq(api_key=GROQ_API_KEY)
 
 
# ═══════════════════════════════════════════════════════════
# LLM HELPER — used ONLY for interpreting user confirmation
# ═══════════════════════════════════════════════════════════
 
def _deterministic_confirm(reply: str):
    """
    Fast deterministic pre-filter for the most common user replies.
    Runs BEFORE the LLM to avoid unnecessary API calls and improve accuracy.
 
    Returns:
      True  → p1 (first non-year part) is the day
      False → p1 (first non-year part) is the month
      None  → cannot determine, must fall through to LLM
    """
    r = reply.strip().lower()
    r = re.sub(r'\b(is|the|a|an|us|that|it|number|no|yes|please|my|of)\b', ' ', r)
    r = re.sub(r'\s+', ' ', r).strip()
 
    # ── COMPOUND patterns — checked FIRST (most specific) ────────────
    COMPOUND_DAY = [
        r'\bday.?month\b',
        r'\bdate.?month\b',
        r'\bdd[-\s]mm\b',
        r'\bfirst.?day\b',
        r'\bfirst.?date\b',
        r'\bday.?first\b',
        r'\bdate.?first\b',
    ]
    COMPOUND_MONTH = [
        r'\bmonth.?day\b',
        r'\bmonth.?date\b',
        r'\bmm[-\s]dd\b',
        r'\bfirst.?month\b',
        r'\bmonth.?first\b',
    ]
 
    for pat in COMPOUND_DAY:
        if re.search(pat, r):
            return True
    for pat in COMPOUND_MONTH:
        if re.search(pat, r):
            return False
 
    # ── SINGLE-WORD fallbacks ─────────────────────────────────────────
    if re.search(r'\b(day|date)\b', r):
        return True
    if re.search(r'\bmonth\b', r):
        return False
    if re.search(r'\bdd\b', r):
        return True
    if re.search(r'\bmm\b', r):
        return False
 
    return None  # fall through to LLM
 
 
def _llm_interpret_confirm(user_reply: str, raw_date: str,
                            p1: int, p2: int, year: str):
    """
    Interprets the user's clarification reply.
 
    STEP 1: deterministic matching (fast, no API call).
    STEP 2: LLM fallback only if deterministic fails.
 
    Returns:
      True  → p1 is the day   (p2 is month)
      False → p1 is the month (p2 is day)
      None  → could not determine intent
    """
    det = _deterministic_confirm(user_reply)
    if det is not None:
        return det
 
    prompt = f"""You are a date format classifier. A user was asked:
"In the date {raw_date}, is {p1} the day or the month?"
 
The user replied: "{user_reply}"
 
Your task: Decide if the number ({p1}) is the DAY or the MONTH.
 
CONTEXT:
- Two ambiguous parts: first={p1}, second={p2}, year={year}
- "day" / "date" / "dd" → p1 is the DAY
- "month" / "mm"        → p1 is the MONTH
 
Reply ONLY with valid JSON:
{{
  "first_is_day": true
}}
OR
{{
  "first_is_day": false
}}
OR
{{
  "first_is_day": null
}}
 
Use null ONLY if completely unrelated (e.g. "banana").
day/date/dd → true. month/mm → false."""
 
    try:
        res = _groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON classifier. "
                        "Output ONLY a JSON object with key 'first_is_day'. "
                        "No markdown, no explanation, no extra text."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=20,
        )
        raw = res.choices[0].message.content.strip()
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(raw)
        val = data.get("first_is_day")
        if val is None:
            return None
        return bool(val)
    except Exception as e:
        print(f"[parser] LLM confirm interpret failed: {e}")
        return None
 
 
# ═══════════════════════════════════════════════════════════
# TIME EXTRACTION  (runs first)
# ═══════════════════════════════════════════════════════════
 
def _extract_time(text: str):
    """
    Returns (time_str, has_ampm, time_needs_ampm, consumed_span).
 
    consumed_span : (start, end) in original text. None if no time found.
    time_str      : "HH:MM" (24-hour) or None
    time_needs_ampm : True when hour 1-12 and no AM/PM given.
    """
    upper = text.upper()
 
    # 1. HH:MM[:SS] + optional AM/PM
    m = re.search(r'\b(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)?\b', upper)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        if ampm:
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
            return f"{min(hour,23):02d}:{minute:02d}", True, False, m.span()
        else:
            if hour >= 13:
                return f"{min(hour,23):02d}:{minute:02d}", False, False, m.span()
            else:
                return f"{hour:02d}:{minute:02d}", False, True, m.span()
 
    # 2. Bare hour WITH explicit AM/PM  ("5 pm", "10am")
    m = re.search(r'\b(\d{1,2})\s*(AM|PM)\b', upper)
    if m:
        hour, ampm = int(m.group(1)), m.group(2)
        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0
        return f"{min(hour,23):02d}:00", True, False, m.span()
 
    # 3. Bare hour WITHOUT AM/PM — only after keyword "at"
    m = re.search(r'\bAT\s+(\d{1,2})\b(?!\s*[-/]\d)', upper)
    if m:
        hour = int(m.group(1))
        if 1 <= hour <= 12:
            return f"{hour:02d}:00", False, True, m.span()
        if 13 <= hour <= 23:
            return f"{hour:02d}:00", False, False, m.span()
 
    return None, False, False, None
 
 
# ═══════════════════════════════════════════════════════════
# DATE EXTRACTION  (runs after time token is stripped)
# ═══════════════════════════════════════════════════════════
 
_MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|"
    "september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)
 
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday",
             "friday", "saturday", "sunday"]
 
_DP_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": False,
}
 
 
def _extract_date(text: str):
    """
    Returns one of:
      "YYYY-MM-DD"               — date clearly resolved
      None                       — no date found
      { "ambiguous": True, ... } — both non-year parts <= 12, must ask user
 
    The ambiguous dict now includes "year_first": bool so chat.py can
    show a format-appropriate confirmation message.
 
    AMBIGUITY RULE — applies to ALL numeric formats:
      p1 > 12  → p1 cannot be month → unambiguous
      p2 > 12  → p2 cannot be month → unambiguous
      both <= 12 → ALWAYS ambiguous, ask the user
 
    Examples:
      2026-05-06 → p1=05, p2=06, both ≤ 12 → ambiguous (year_first=True)
      2026/05/06 → p1=05, p2=06, both ≤ 12 → ambiguous (year_first=True)
      2026-08-14 → p2=14 > 12              → unambiguous (month=08, day=14)
      28-05-2026 → p1=28 > 12              → unambiguous (day=28, month=05)
      05-06-2026 → both ≤ 12               → ambiguous (year_first=False)
    """
    if not text or not text.strip():
        return None
 
    now   = datetime.now()
    lower = text.lower().strip()
 
    # 1. Keywords
    if "today" in lower:
        return now.strftime("%Y-%m-%d")
    if "tomorrow" in lower:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
 
    # 2. next <weekday> / bare <weekday>
    for i, wd in enumerate(_WEEKDAYS):
        if f"next {wd}" in lower:
            days = (i - now.weekday() + 7) % 7 or 7
            return (now + timedelta(days=days)).strftime("%Y-%m-%d")
        if re.search(rf'\b{wd}\b', lower):
            days = (i - now.weekday() + 7) % 7 or 7
            return (now + timedelta(days=days)).strftime("%Y-%m-%d")
 
    # 3a. YYYY-MM-DD (ISO with hyphens) — year_first=True
    m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', text)
    if m:
        year, p1, p2 = m.group(1), int(m.group(2)), int(m.group(3))
        raw = m.group(0)
        if p1 > 12:
            try:
                return datetime(int(year), p2, p1).strftime("%Y-%m-%d")
            except ValueError:
                return None
        elif p2 > 12:
            try:
                return datetime(int(year), p1, p2).strftime("%Y-%m-%d")
            except ValueError:
                return None
        else:
            return {
                "ambiguous":  True,
                "raw":        raw,
                "p1":         p1,
                "p2":         p2,
                "year":       year,
                "year_first": True,   # ← NEW: YYYY-MM-DD format
            }
 
    # 3b. YYYY/MM/DD — year-first with slashes — year_first=True
    m = re.search(r'\b(\d{4})/(\d{1,2})/(\d{1,2})\b', text)
    if m:
        year, p1, p2 = m.group(1), int(m.group(2)), int(m.group(3))
        raw = m.group(0)
        if p1 > 12:
            try:
                return datetime(int(year), p2, p1).strftime("%Y-%m-%d")
            except ValueError:
                return None
        elif p2 > 12:
            try:
                return datetime(int(year), p1, p2).strftime("%Y-%m-%d")
            except ValueError:
                return None
        else:
            return {
                "ambiguous":  True,
                "raw":        raw,
                "p1":         p1,
                "p2":         p2,
                "year":       year,
                "year_first": True,   # ← NEW: YYYY/MM/DD format
            }
 
    # 4. Numeric date: DD-MM-YYYY / DD/MM/YYYY — year_first=False
    m = re.search(r'\b(\d{1,2})([-/])(\d{1,2})\2(\d{4})\b', text)
    if m:
        p1, p2, year = int(m.group(1)), int(m.group(3)), m.group(4)
        raw = m.group(0)
        if p1 > 12:
            try:
                return datetime(int(year), p2, p1).strftime("%Y-%m-%d")
            except ValueError:
                return None
        elif p2 > 12:
            try:
                return datetime(int(year), p1, p2).strftime("%Y-%m-%d")
            except ValueError:
                return None
        else:
            return {
                "ambiguous":  True,
                "raw":        raw,
                "p1":         p1,
                "p2":         p2,
                "year":       year,
                "year_first": False,  # ← NEW: DD/MM/YYYY format
            }
 
    # 5. Natural language with month name — never ambiguous
    m = re.search(
        rf'\b(\d{{1,2}})\s+({_MONTH_NAMES})\s+(\d{{4}})\b'
        rf'|({_MONTH_NAMES})\s+(\d{{1,2}}),?\s+(\d{{4}})\b',
        lower
    )
    if m:
        parsed = dateparser.parse(m.group(0), settings=_DP_SETTINGS)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
 
    # 6. Full-text dateparser fallback (prefer DMY)
    for order in ("DMY", "MDY"):
        parsed = dateparser.parse(
            text,
            settings={**_DP_SETTINGS, "DATE_ORDER": order}
        )
        if parsed:
            return parsed.strftime("%Y-%m-%d")
 
    return None
 
 
# ═══════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════
 
def parse_meeting(user_id, text: str) -> dict:
    """
    Main entry point.
 
    Returns:
        date              : "YYYY-MM-DD" or None
        time              : "HH:MM" (24-hour) or None
        time_needs_ampm   : bool
        date_ambiguous    : bool
        ambiguous_year_first : bool  ← True when format was YYYY-MM-DD or YYYY/MM/DD
 
    Extra keys present only when date_ambiguous is True:
        ambiguous_raw        : original string e.g. "2026-05-06"
        ambiguous_p1         : int  (first non-year part)
        ambiguous_p2         : int  (second non-year part)
        ambiguous_year       : str
        ambiguous_year_first : bool
    """
    if not text:
        return {
            "date": None, "time": None,
            "time_needs_ampm": False, "date_ambiguous": False,
        }
 
    # Step 1: extract time first
    time_str, _has_ampm, time_needs_ampm, span = _extract_time(text)
 
    # Step 2: strip time token before date extraction
    text_for_date = (text[:span[0]] + " " + text[span[1]:]) if span else text
 
    # Step 3: extract date
    date_result = _extract_date(text_for_date)
 
    # Step 4: handle ambiguous date
    if isinstance(date_result, dict) and date_result.get("ambiguous"):
        return {
            "date":                  None,
            "time":                  time_str,
            "time_needs_ampm":       time_needs_ampm,
            "date_ambiguous":        True,
            "ambiguous_raw":         date_result["raw"],
            "ambiguous_p1":          date_result["p1"],
            "ambiguous_p2":          date_result["p2"],
            "ambiguous_year":        date_result["year"],
            "ambiguous_year_first":  date_result.get("year_first", False),  # ← NEW
        }
 
    return {
        "date":             date_result,
        "time":             time_str,
        "time_needs_ampm":  time_needs_ampm,
        "date_ambiguous":   False,
    }
 
 
def is_past(date_str: str, time_str: str) -> bool:
    """Returns True if the given date+time is already in the past."""
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        return dt < datetime.now()
    except Exception:
        return False
 
 
def resolve_ambiguous_date(p1: int, p2: int, year: str,
                           raw: str, user_reply: str,
                           year_first: bool = False):
    """
    Interprets the user's clarification and builds the final YYYY-MM-DD date.
 
    year_first=True  (YYYY-MM-DD / YYYY/MM/DD):
      first_is_day=False → p1=month, p2=day  → datetime(year, p1, p2)  ← standard
      first_is_day=True  → p1=day,   p2=month → datetime(year, p2, p1)  ← rare
 
    year_first=False (DD-MM-YYYY / DD/MM/YYYY):
      first_is_day=True  → p1=day,   p2=month → datetime(year, p2, p1)
      first_is_day=False → p1=month, p2=day   → datetime(year, p1, p2)
 
    Both cases use the same formula:
      day, month = (p1, p2) if first_is_day else (p2, p1)
    which is correct for both year-first and day-first layouts.
 
    Returns "YYYY-MM-DD" or None if resolution failed.
    """
    first_is_day = _llm_interpret_confirm(user_reply, raw, p1, p2, year)
 
    if first_is_day is None:
        return None   # caller will ask again
 
    day, month = (p1, p2) if first_is_day else (p2, p1)
    try:
        return datetime(int(year), month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None
 