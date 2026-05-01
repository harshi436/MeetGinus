# from fastapi import APIRouter
# from pydantic import BaseModel
# from services.pdf_qa_service import ask_pdf
# from services.meeting_service import handle_meeting
# from services.scheduler_service import add_scheduled_meeting
# from services.parser import parse_meeting, is_past
 
# from db.mongo import chat_collection, report_collection, meeting_collection
# from state.chat_state import set_state, get_state, clear_state
# from services.groq_client import ask_llm
# import os
# import re
# import datetime
 
# router = APIRouter()
 
 
# class ChatRequest(BaseModel):
#     user_id: str
#     message: str
 
 
# # =========================
# # SAVE BOT RESPONSE
# # =========================
# def save_bot(user_id, msg):
#     chat_collection.update_one(
#         {"user_id": user_id},
#         {"$push": {"messages": {"role": "bot", "message": msg}}},
#         upsert=True
#     )
 
 
# # =========================
# # NORMALIZERS
# # =========================
# def normalize_date(date_str):
#     if not date_str:
#         return None
#     try:
#         if re.match(r"\d{1,2}-\d{2}-\d{4}", date_str):
#             return datetime.datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
#         if re.match(r"\d{1,2}/\d{2}/\d{4}", date_str):
#             return datetime.datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
#         return date_str
#     except:
#         return date_str
 
 
# def normalize_time(time_str):
#     if not time_str:
#         return None
#     s = str(time_str).strip().lower().replace(".", "")
#     for fmt in ("%I %p", "%I:%M %p"):
#         try:
#             return datetime.datetime.strptime(s.upper(), fmt).strftime("%H:%M")
#         except:
#             pass
#     try:
#         return datetime.datetime.strptime(s, "%H:%M").strftime("%H:%M")
#     except:
#         pass
#     return None
 
 
# # =========================
# # PAST VALIDATION
# # =========================
# def validate_future(date_str, time_str):
#     try:
#         dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
#         now = datetime.datetime.now()
#         if dt < now:
#             if date_str < now.strftime("%Y-%m-%d"):
#                 return "⚠️ This date has already passed. Please provide a future date."
#             return "⚠️ This time has already passed. Please provide a valid future time."
#     except:
#         pass
#     return None
 
 
# # =========================
# # APPLY AM/PM TO RAW HOUR
# # =========================
# def apply_ampm(raw_hour: int, ampm: str) -> str:
#     hour = raw_hour
#     if ampm == "pm" and hour != 12:
#         hour += 12
#     elif ampm == "am" and hour == 12:
#         hour = 0
#     return f"{hour:02d}:00"
 
 
# # =========================
# # SCHEDULE HELPER  (actual Google Calendar call + DB save)
# # =========================
# def do_schedule(user_id, date, time):
#     return handle_meeting(user_id, f"schedule meeting {date} {time}")
 
 
# # =========================
# # SHARED COLLECT LOGIC
# # =========================
# def collect_datetime(message: str, state: dict) -> dict:
#     """
#     Merges new message into state's partial.
#     Returns:
#       { "ready": True,  "date": ..., "time": ... }
#       { "ready": False, "message": "...", "new_state": {...} }
#     """
#     partial = dict(state.get("partial", {}))
#     msg_lower = message.strip().lower()
 
#     # --- Handle AM/PM answer ---
#     if state.get("awaiting_ampm") and msg_lower in ("am", "pm"):
#         raw_hour = state.get("raw_hour")
#         if raw_hour is not None:
#             partial["time"] = apply_ampm(int(raw_hour), msg_lower)
#             partial["awaiting_ampm"] = False
 
#     else:
#         parsed = parse_meeting(None, message)
 
#         if parsed.get("date"):
#             partial["date"] = normalize_date(parsed["date"])
 
#         if parsed.get("time"):
#             if parsed.get("time_needs_ampm"):
#                 raw_hour_str = parsed["time"].split(":")[0]
#                 return {
#                     "ready": False,
#                     "message": "🕐 Should I schedule this in AM or PM?",
#                     "new_state": {
#                         **state,
#                         "partial": partial,
#                         "awaiting_ampm": True,
#                         "raw_hour": int(raw_hour_str),
#                     }
#                 }
#             else:
#                 partial["time"] = normalize_time(parsed["time"]) or parsed["time"]
 
#     date = partial.get("date")
#     time = partial.get("time")
 
#     if not date:
#         return {
#             "ready": False,
#             "message": "📅 Please provide the date (e.g. 28-05-2026 or tomorrow)",
#             "new_state": {**state, "partial": partial, "awaiting_ampm": False}
#         }
 
#     if not time:
#         return {
#             "ready": False,
#             "message": "⏰ Please provide the time (e.g. 3 pm or 15:00)",
#             "new_state": {**state, "partial": partial, "awaiting_ampm": False}
#         }
 
#     err = validate_future(date, time)
#     if err:
#         return {
#             "ready": False,
#             "message": err,
#             "new_state": {**state, "partial": {}, "awaiting_ampm": False, "raw_hour": None}
#         }
 
#     return {"ready": True, "date": date, "time": time}
 
 
# # =========================
# # MAIN API
# # =========================
# @router.post("/chat")
# def chat(req: ChatRequest):
 
#     user_id = req.user_id
#     message = req.message.strip()
#     msg_lower = message.lower()
 
#     chat_collection.update_one(
#         {"user_id": user_id},
#         {"$push": {"messages": {"role": "user", "message": message}}},
#         upsert=True
#     )
 
#     state = get_state(user_id) or {}
#     final_response = None
 
#     NGROK_URL = "https://stimulatingly-glumpier-hannelore.ngrok-free.dev"
 
#     # =====================================================
#     # REPORT FLOW
#     # =====================================================
#     if "report" in msg_lower:
 
#         report = report_collection.find_one(
#             {"user_id": user_id},
#             sort=[("created_at", -1)]
#         )
 
#         if not report or not report.get("pdf_report_path"):
#             final_response = "📭 No report found"
#         else:
#             pdf_path = report.get("pdf_report_path")
#             filename = os.path.basename(pdf_path).replace("\\", "/")
#             pdf_url = f"{NGROK_URL}/reports/{filename}"
 
#             set_state(user_id, {"step": "pdf_confirm", "pdf_path": pdf_path})
 
#             final_response = (
#                 f"📄 Report ready\n👉 {pdf_url}\n\n"
#                 f"❓ Do you want to ask questions from this PDF? (yes/no)"
#             )
 
#     # =====================================================
#     # PDF CONFIRM
#     # =====================================================
#     elif state.get("step") == "pdf_confirm":
 
#         if msg_lower in ("yes", "y"):
#             from services.pdf_qa_service import create_vector_db
#             create_vector_db(user_id, state["pdf_path"])
#             set_state(user_id, {"step": "pdf_qa", "pdf_path": state["pdf_path"]})
#             final_response = "🧠 Ask your question"
#         elif msg_lower in ("no", "n"):
#             clear_state(user_id)
#             final_response = "👍 Okay"
#         else:
#             final_response = "❓ Please answer yes or no"
 
#     # =====================================================
#     # PDF QA
#     # =====================================================
#     elif state.get("step") == "pdf_qa":
 
#         if msg_lower in ("exit", "stop"):
#             clear_state(user_id)
#             final_response = "❌ Exited report mode"
#         else:
#             final_response = ask_pdf(user_id, message)
 
#     # =====================================================
#     # HISTORY
#     # =====================================================
#     elif "history" in msg_lower:
 
#         doc = chat_collection.find_one({"user_id": user_id})
#         if not doc:
#             final_response = "📭 No history"
#         else:
#             msgs = doc.get("messages", [])[-10:]
#             final_response = "\n".join([f"{m['role']}: {m['message']}" for m in msgs])
 
#     # =====================================================
#     # PREVIOUS MEETING
#     # =====================================================
#     elif any(k in msg_lower for k in ("previous meeting", "last meeting", "show my meeting")):
 
#         meeting = meeting_collection.find_one(
#             {"user_id": user_id},
#             sort=[("created_at", -1)]
#         )
 
#         if not meeting:
#             final_response = "📭 No meeting found"
#         else:
#             set_state(user_id, {"step": "ask_update", "meeting_data": meeting})
 
#             final_response = (
#                 f"📅 Last Meeting:\n"
#                 f"📅 Date: {meeting.get('date')}\n"
#                 f"⏰ Time: {meeting.get('time')}\n"
#                 f"👉 {meeting.get('meeting_url')}\n\n"
#                 f"Do you want to update this meeting? (yes/no)"
#             )
 
#     # =====================================================
#     # ASK UPDATE
#     # =====================================================
#     elif state.get("step") == "ask_update":
 
#         if msg_lower in ("yes", "y"):
#             set_state(user_id, {
#                 "step": "update_collect",
#                 "meeting_data": state.get("meeting_data"),
#                 "partial": {},
#                 "awaiting_ampm": False,
#                 "raw_hour": None,
#             })
#             final_response = "🔄 Please provide the new date and time"
 
#         elif msg_lower in ("no", "n"):
#             clear_state(user_id)
#             final_response = "👍 Okay"
#         else:
#             final_response = "❓ Reply yes or no"
 
#     # =====================================================
#     # UPDATE COLLECT
#     # =====================================================
#     elif state.get("step") == "update_collect":
 
#         result = collect_datetime(message, state)
 
#         if not result["ready"]:
#             set_state(user_id, result["new_state"])
#             final_response = result["message"]
 
#         else:
#             date, time = result["date"], result["time"]
#             old = state.get("meeting_data", {})
 
#             set_state(user_id, {
#                 "step": "update_confirm",
#                 "meeting_data": old,
#                 "new_data": {"date": date, "time": time},
#             })
 
#             final_response = (
#                 f"📌 Updated Preview:\n"
#                 f"📅 Date: {date}\n"
#                 f"⏰ Time: {time}\n"
#                 f"👉 {old.get('meeting_url')}\n\n"
#                 f"Confirm update? (yes/no)"
#             )
 
#     # =====================================================
#     # UPDATE CONFIRM
#     # =====================================================
#     elif state.get("step") == "update_confirm":
 
#         if msg_lower in ("yes", "y"):
 
#             new_data = state.get("new_data", {})
#             old = state.get("meeting_data", {})
 
#             set_state(user_id, {
#                 "event_id": old.get("event_id"),
#                 "new_meeting": {
#                     "date": new_data["date"],
#                     "time": new_data["time"],
#                 },
#             })
 
#             res = handle_meeting(user_id, "update_meeting")
 
#             if not res or not res.get("meeting_url"):
#                 return {"message": "❌ Failed to update meeting"}
 
#             meeting_url = old.get("meeting_url") or res.get("meeting_url")
 
#             set_state(user_id, {
#                 "step": "bot_join_confirm",
#                 "meeting_data": {
#                     **res,
#                     "meeting_url": meeting_url,
#                     "date": new_data["date"],
#                     "time": new_data["time"],
#                 }
#             })
 
#             final_response = (
#                 f"✅ Meeting Updated\n"
#                 f"📅 Date: {new_data['date']}\n"
#                 f"⏰ Time: {new_data['time']}\n"
#                 f"👉 {meeting_url}\n\n"
#                 f"🤖 Should the bot join this meeting? (yes/no)"
#             )
 
#         elif msg_lower in ("no", "n"):
#             set_state(user_id, {
#                 "step": "update_collect",
#                 "meeting_data": state.get("meeting_data"),
#                 "partial": {},
#                 "awaiting_ampm": False,
#                 "raw_hour": None,
#             })
#             final_response = "🔄 Please enter the new date and time again"
 
#         else:
#             final_response = "❓ Reply yes or no"
 
#     # =====================================================
#     # NEW MEETING — "schedule" trigger
#     # =====================================================
#     elif msg_lower.startswith("schedule"):
 
#         fresh_state = {
#             "step": "collect",
#             "partial": {},
#             "awaiting_ampm": False,
#             "raw_hour": None,
#         }
 
#         result = collect_datetime(message, fresh_state)
 
#         if not result["ready"]:
#             set_state(user_id, result["new_state"])
#             final_response = result["message"]
 
#         else:
#             # ✅ Date + time ready → show confirmation BEFORE scheduling
#             date, time = result["date"], result["time"]
 
#             set_state(user_id, {
#                 "step": "new_meeting_confirm",
#                 "pending_date": date,
#                 "pending_time": time,
#             })
 
#             final_response = (
#                 f"📋 Meeting Details:\n"
#                 f"📅 Date: {date}\n"
#                 f"⏰ Time: {time}\n\n"
#                 f"Do you want to confirm this meeting? (yes/no)"
#             )
 
#     # =====================================================
#     # COLLECT (follow-up messages for missing date/time)
#     # =====================================================
#     elif state.get("step") == "collect":
 
#         result = collect_datetime(message, state)
 
#         if not result["ready"]:
#             set_state(user_id, result["new_state"])
#             final_response = result["message"]
 
#         else:
#             # ✅ Date + time ready → show confirmation BEFORE scheduling
#             date, time = result["date"], result["time"]
 
#             set_state(user_id, {
#                 "step": "new_meeting_confirm",
#                 "pending_date": date,
#                 "pending_time": time,
#             })
 
#             final_response = (
#                 f"📋 Meeting Details:\n"
#                 f"📅 Date: {date}\n"
#                 f"⏰ Time: {time}\n\n"
#                 f"Do you want to confirm this meeting? (yes/no)"
#             )
 
#     # =====================================================
#     # NEW MEETING CONFIRM  ← new step
#     # =====================================================
#     elif state.get("step") == "new_meeting_confirm":
 
#         date = state.get("pending_date")
#         time = state.get("pending_time")
 
#         if msg_lower in ("yes", "y"):
 
#             # Now actually create the meeting
#             res = do_schedule(user_id, date, time)
 
#             if not res or not res.get("meeting_url"):
#                 return {"message": "❌ Failed to create meeting"}
 
#             set_state(user_id, {
#                 "step": "bot_join_confirm",
#                 "meeting_data": {**res, "date": date, "time": time},
#             })
 
#             final_response = (
#                 f"📅 Meeting Created\n"
#                 f"📅 Date: {date}\n"
#                 f"⏰ Time: {time}\n"
#                 f"👉 {res['meeting_url']}\n\n"
#                 f"🤖 Should the bot join this meeting? (yes/no)"
#             )
 
#         elif msg_lower in ("no", "n"):
#             # Don't schedule — restart date/time collection
#             set_state(user_id, {
#                 "step": "collect",
#                 "partial": {},
#                 "awaiting_ampm": False,
#                 "raw_hour": None,
#             })
 
#             final_response = "🔄 Please provide a new date and time for the meeting"
 
#         else:
#             final_response = "❓ Reply yes or no"
 
#     # =====================================================
#     # BOT JOIN CONFIRM
#     # =====================================================
#     elif state.get("step") == "bot_join_confirm":
 
#         data = state.get("meeting_data") or {}
 
#         if msg_lower in ("yes", "y"):
 
#             raw_time = normalize_time(data.get("time"))
#             if not raw_time:
#                 set_state(user_id, {
#                     "step": "update_collect",
#                     "meeting_data": data,
#                     "partial": {},
#                     "awaiting_ampm": False,
#                     "raw_hour": None,
#                 })
#                 return {"message": "❌ Invalid time. Please re-enter (e.g. 7 pm or 14:00)"}
 
#             try:
#                 start_dt = datetime.datetime.strptime(
#                     f"{data['date']} {raw_time}", "%Y-%m-%d %H:%M"
#                 )
#             except Exception:
#                 set_state(user_id, {
#                     "step": "update_collect",
#                     "meeting_data": data,
#                     "partial": {},
#                     "awaiting_ampm": False,
#                     "raw_hour": None,
#                 })
#                 return {"message": "❌ Invalid date/time. Please re-enter"}
 
#             add_scheduled_meeting(
#                 job_id=data["event_id"],
#                 meeting_url=data["meeting_url"],
#                 scheduled_at_iso=start_dt.isoformat(),
#                 user_id=user_id,
#             )
 
#             clear_state(user_id)
 
#             final_response = (
#                 f"🤖 Bot Scheduled\n"
#                 f"👉 {data.get('meeting_url')}\n"
#                 f"🕒 {data.get('date')} {data.get('time')}"
#             )
 
#         elif msg_lower in ("no", "n"):
#             clear_state(user_id)
 
#             final_response = (
#                 f"📅 Meeting Confirmed\n"
#                 f"👉 {data.get('meeting_url')}\n"
#                 f"🕒 {data.get('date')} {data.get('time')}"
#             )
 
#         else:
#             final_response = "❓ Reply yes or no"
 
#     # =====================================================
#     # FALLBACK — LLM
#     # =====================================================
#     if final_response is None:
#         final_response = ask_llm(message)
 
#     save_bot(user_id, final_response)
#     return {"message": final_response}















































# # from fastapi import APIRouter
# # from pydantic import BaseModel
# # from services.pdf_qa_service import ask_pdf
# # from services.meeting_service import handle_meeting
# # from services.scheduler_service import add_scheduled_meeting
# # from services.parser import parse_meeting

# # from db.mongo import chat_collection, report_collection, meeting_collection
# # from state.chat_state import set_state, get_state, clear_state
# # from services.groq_client import ask_llm

# # import os
# # import re
# # import datetime

# # router = APIRouter()


# # class ChatRequest(BaseModel):
# #     user_id: str
# #     message: str


# # # =========================
# # # SAVE BOT RESPONSE
# # # =========================
# # def save_bot(user_id, msg):
# #     chat_collection.update_one(
# #         {"user_id": user_id},
# #         {"$push": {"messages": {"role": "bot", "message": msg}}},
# #         upsert=True
# #     )


# # # =========================
# # # NORMALIZATION
# # # =========================
# # def normalize_date(date_str):
# #     try:
# #         if re.match(r"\d{2}-\d{2}-\d{4}", date_str):
# #             return datetime.datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
# #         return date_str
# #     except:
# #         return date_str


# # def normalize_time(time_str):
# #     if not time_str:
# #         return None

# #     time_str = time_str.strip().upper()

# #     try:
# #         return datetime.datetime.strptime(time_str, "%I:%M %p").strftime("%H:%M")
# #     except:
# #         pass

# #     try:
# #         return datetime.datetime.strptime(time_str, "%H:%M").strftime("%H:%M")
# #     except:
# #         pass

# #     return time_str


# # # =========================
# # # VALIDATION
# # # =========================
# # def check_missing_parts(msg: str):
# #     msg_lower = msg.lower()

# #     has_date = bool(re.search(r"\d{4}-\d{2}-\d{2}", msg))
# #     has_time = bool(re.search(r"\d{1,2}:\d{2}", msg))

# #     if not has_date and not has_time:
# #         return "❌ Date and time are missing"
# #     if not has_date:
# #         return "❌ Date is missing (Example: 2026-04-28)"
# #     if not has_time:
# #         return "❌ Time is missing (Example: 14:00)"

# #     return None


# # # =========================
# # # MAIN API
# # # =========================
# # @router.post("/chat")
# # def chat(req: ChatRequest):

# #     user_id = req.user_id
# #     message = req.message.strip()
# #     msg_lower = message.lower()

# #     # Save user message
# #     chat_collection.update_one(
# #         {"user_id": user_id},
# #         {"$push": {"messages": {"role": "user", "message": message}}},
# #         upsert=True
# #     )

# #     state = get_state(user_id) or {}
# #     final_response = None

# #     # =========================
# #     # MEETING FLOW (FIXED)
# #     # =========================
# #     if msg_lower.startswith("schedule") or state.get("step") == "collect":

# #         existing = state.get("partial", {})
# #         new = parse_meeting(user_id, message)

# #         merged = {**existing, **(new or {})}

# #         date = normalize_date(merged.get("date", ""))
# #         time = normalize_time(merged.get("time", ""))

# #         combined = f"{date} {time}"

# #         error = check_missing_parts(combined)

# #         if error:
# #             set_state(user_id, {"step": "collect", "partial": merged})
# #             final_response = error
# #         else:
# #             res = handle_meeting(user_id, f"schedule meeting {combined}")

# #             if not res or not res.get("meeting_url"):
# #                 final_response = "❌ Failed to create meeting"
# #             else:
# #                 set_state(user_id, {"step": "confirm", "meeting_data": res})

# #                 final_response = f"""📅 Meeting created
# # 👉 {res.get('meeting_url')}

# # Confirm? (yes/no)"""

# #     # =========================
# #     # CONFIRM
# #     # =========================
# #     elif state.get("step") == "confirm":

# #         data = state.get("meeting_data")

# #         if msg_lower in ["yes", "y"]:
# #             set_state(user_id, {"step": "bot_join_confirm", "meeting_data": data})
# #             final_response = "🤖 Bot ko meeting join karna hai? (yes/no)"

# #         elif msg_lower in ["no", "n"]:
# #             set_state(user_id, {"step": "collect", "partial": {}})
# #             final_response = "🔄 Enter new date & time"

# #         else:
# #             final_response = "❓ Reply yes or no"

# #     # =========================
# #     # BOT JOIN
# #     # =========================
# #     elif state.get("step") == "bot_join_confirm":

# #         data = state.get("meeting_data")

# #         if msg_lower in ["yes", "y"]:

# #             start_dt = datetime.datetime.strptime(
# #                 f"{data['date']} {data['time']}",
# #                 "%Y-%m-%d %H:%M"
# #             )

# #             add_scheduled_meeting(
# #                 job_id=data["event_id"],
# #                 meeting_url=data["meeting_url"],
# #                 scheduled_at_iso=start_dt.isoformat(),
# #                 user_id=user_id
# #             )

# #             clear_state(user_id)

# #             final_response = f"""🤖 Bot Scheduled
# # 👉 {data.get('meeting_url')}
# # 🕒 {data.get('date')} {data.get('time')}"""

# #         elif msg_lower in ["no", "n"]:
# #             clear_state(user_id)

# #             final_response = f"""📅 Meeting Confirmed (No Bot)
# # 👉 {data.get('meeting_url')}
# # 🕒 {data.get('date')} {data.get('time')}"""

# #         else:
# #             final_response = "❓ Reply yes or no"

# #     # =========================
# #     # LLM (CHAT + MEMORY)
# #     # =========================
# #     if final_response is None:

# #         history_doc = chat_collection.find_one({"user_id": user_id})
# #         history_msgs = history_doc.get("messages", []) if history_doc else []

# #         conversation = []

# #         for m in history_msgs[-10:]:
# #             role = "assistant" if m["role"] == "bot" else "user"
# #             conversation.append({
# #                 "role": role,
# #                 "content": m["message"]
# #             })

# #         conversation.append({
# #             "role": "user",
# #             "content": message
# #         })

# #         final_response = ask_llm(conversation)

# #     save_bot(user_id, final_response)

# #     return {"message": final_response}





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
    """
    Accepts YYYY-MM-DD / DD-MM-YYYY / DD/MM/YYYY
    and always returns YYYY-MM-DD.
    """
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


# =========================
# BUILD AMBIGUOUS CONFIRM MESSAGE
# Format-aware: YYYY-MM-DD / YYYY/MM/DD shows different hint than DD-MM-YYYY
# =========================
def _ambiguous_confirm_msg(raw: str, p1: int, p2: int, year: str,
                            year_first: bool) -> str:
    """
    Returns a clear, format-appropriate confirmation question.

    year_first=True  (e.g. 2026-05-06 or 2026/05/06):
      Asks: "In 2026-05-06, is 05 the month or is 06 the month?"
      Hints show YYYY-MM-DD vs YYYY-DD-MM so user understands position.

    year_first=False (e.g. 05-06-2026 or 11/12/2026):
      Asks: "In 11/12/2026, is 11 the day or the month?"
      Hints show DD-MM-YYYY vs MM-DD-YYYY.
    """
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
    """Retry message when user's reply was not understood."""
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
            f'• **"first is day"**   → day={p1:02d}, month={p2:02d}\n'
            f'• **"first is month"** → day={p2:02d}, month={p1:02d}'
        )


# =========================
# SHARED COLLECT LOGIC
# =========================
def collect_datetime(message: str, state: dict) -> dict:
    """
    Merges new message into state's partial date/time.
    """
    partial   = dict(state.get("partial", {}))
    msg_lower = message.strip().lower()

    # ── Handle AM/PM answer ──────────────────────────────────────────
    if state.get("awaiting_ampm") and msg_lower in ("am", "pm"):
        raw_hour = state.get("raw_hour")
        if raw_hour is not None:
            partial["time"] = apply_ampm(int(raw_hour), msg_lower)
            partial["awaiting_ampm"] = False

    else:
        parsed = parse_meeting(None, message)

        # ── Ambiguous numeric date ────────────────────────────────────
        if parsed.get("date_ambiguous"):
            # Capture any time that came alongside the ambiguous date
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
                "ambiguous_year_first":  year_first,   # ← NEW: stored in state
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

        # ── Normal date ──────────────────────────────────────────────
        if parsed.get("date"):
            new_date = normalize_date(parsed["date"])
            if new_date and new_date != partial.get("date"):
                partial["time"] = None
            partial["date"] = new_date

        # ── Time ─────────────────────────────────────────────────────
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
            "message":   "📅 Please provide the date for the meeting along with year and also month",
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
    """
    Resolves an ambiguous date after the user has clarified.

    For year-first formats (year_first=True):
      "yes" → standard order: month=p1, day=p2   → first_is_day=False
      "no"  → swapped order:  month=p2, day=p1   → first_is_day=True

    For day-first formats (year_first=False):
      uses LLM/deterministic as before.
    """
    year_first = state.get("ambiguous_year_first", False)
    p1         = state["ambiguous_p1"]
    p2         = state["ambiguous_p2"]
    year       = state["ambiguous_year"]
    raw        = state["ambiguous_raw"]

    msg_lower  = message.strip().lower()

    # ── Year-first shortcut: yes/no maps directly ────────────────────
    if year_first and msg_lower in ("yes", "y", "no", "n"):
        # "yes" → p1 is month, p2 is day  (standard YYYY-MM-DD order)
        # "no"  → p1 is day,   p2 is month (swapped)
        first_is_day = msg_lower in ("no", "n")
        day, month = (p1, p2) if first_is_day else (p2, p1)
        try:
            resolved = datetime.datetime.strptime(
                f"{year}-{month:02d}-{day:02d}", "%Y-%m-%d"
            ).strftime("%Y-%m-%d")
        except ValueError:
            resolved = None
    else:
        # Day-first format OR year-first with non-yes/no reply → use LLM
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
    """
    Routes to handle_date_confirm if awaiting confirmation,
    otherwise runs collect_datetime.
    Returns (result_dict, used_date_confirm: bool).
    """
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

    state          = get_state(user_id) or {}
    final_response = None

    NGROK_URL = "https://stimulatingly-glumpier-hannelore.ngrok-free.dev"

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
    # =====================================================
    elif state.get("step") == "pdf_confirm":

        if msg_lower in ("yes", "y"):
            from services.pdf_qa_service import create_vector_db
            create_vector_db(user_id, state["pdf_path"])
            set_state(user_id, {"step": "pdf_qa", "pdf_path": state["pdf_path"]})
            final_response = "🧠 Ask your question"
        elif msg_lower in ("no", "n"):
            clear_state(user_id)
            final_response = "👍 Okay"
        else:
            final_response = "❓ Please answer yes or no"

    # =====================================================
    # PDF QA
    # =====================================================
    elif state.get("step") == "pdf_qa":

        if msg_lower in ("exit", "stop"):
            clear_state(user_id)
            final_response = "❌ Exited report mode"
        else:
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
    # =====================================================
    elif state.get("step") == "ask_update":

        if msg_lower in ("yes", "y"):
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

        elif msg_lower in ("no", "n"):
            clear_state(user_id)
            final_response = "👍 Okay"
        else:
            final_response = "❓ Reply yes or no"

    # =====================================================
    # UPDATE COLLECT
    # =====================================================
    elif state.get("step") == "update_collect":

        is_ampm_reply    = state.get("awaiting_ampm") and msg_lower in ("am", "pm")
        is_confirm_reply = state.get("awaiting_date_confirm")

        # year_first "yes/no" answers must pass through even without datetime content
        is_yesno_confirm = (
            is_confirm_reply and
            state.get("ambiguous_year_first") and
            msg_lower in ("yes", "y", "no", "n")
        )

        if (not _has_datetime_content(message)
                and not is_confirm_reply
                and not is_ampm_reply
                and not is_yesno_confirm):
            partial = state.get("partial", {})
            if not partial.get("date"):
                final_response = "📅 Please provide the date (e.g. 2026/06/08, 28-05-2026, or tomorrow)"
            else:
                final_response = "⏰ Please provide the time (e.g. 3 pm, 14:00)"
        else:
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
    # =====================================================
    elif state.get("step") == "update_confirm":

        if msg_lower in ("yes", "y"):

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

            set_state(user_id, {
                "step": "bot_join_confirm",
                "meeting_data": {
                    **res,
                    "meeting_url": meeting_url,
                    "date": new_data["date"],
                    "time": new_data["time"],
                }
            })

            final_response = (
                f"✅ Meeting Updated\n"
                f"📅 Date: {new_data['date']}\n"
                f"⏰ Time: {new_data['time']}\n"
                f"👉 {meeting_url}\n\n"
                f"🤖 Should the bot join this meeting? (yes/no)"
            )

        elif msg_lower in ("no", "n"):
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
            new_data = state.get("new_data", {})
            old_mtg  = state.get("meeting_data", {})
            final_response = (
                f"📌 Please reply yes or no to confirm this update:\n"
                f"📅 Date: {new_data.get('date')}\n"
                f"⏰ Time: {new_data.get('time')}\n"
                f"👉 {old_mtg.get('meeting_url')}"
            )

    # =====================================================
    # NEW MEETING — "schedule" / "create" / "book" trigger
    # =====================================================
    elif any(msg_lower.startswith(kw) for kw in ("schedule", "create meeting", "book meeting")):

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
    # =====================================================
    elif state.get("step") == "collect":

        is_ampm_reply    = state.get("awaiting_ampm") and msg_lower in ("am", "pm")
        is_confirm_reply = state.get("awaiting_date_confirm")

        # year_first "yes/no" answers must pass through even without datetime content
        is_yesno_confirm = (
            is_confirm_reply and
            state.get("ambiguous_year_first") and
            msg_lower in ("yes", "y", "no", "n")
        )

        if (not _has_datetime_content(message)
                and not is_confirm_reply
                and not is_ampm_reply
                and not is_yesno_confirm):
            partial = state.get("partial", {})
            if not partial.get("date"):
                final_response = "📅 Please provide the date for the meeting (e.g. 2026/06/08, 28-05-2026, or tomorrow)"
            else:
                final_response = "⏰ Please provide the time for the meeting (e.g. 3 pm, 14:00)"
        else:
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
    # =====================================================
    elif state.get("step") == "new_meeting_confirm":

        date = state.get("pending_date")
        time = state.get("pending_time")

        if msg_lower in ("yes", "y"):

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

        elif msg_lower in ("no", "n"):
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
            final_response = (
                f"📋 Please reply yes or no to confirm this meeting:\n"
                f"📅 Date: {date}\n"
                f"⏰ Time: {time}"
            )

    # =====================================================
    # BOT JOIN CONFIRM
    # =====================================================
    elif state.get("step") == "bot_join_confirm":

        data = state.get("meeting_data") or {}

        if msg_lower in ("yes", "y"):

            raw_time = normalize_time(data.get("time"))
            if not raw_time:
                set_state(user_id, {
                    "step":                  "update_collect",
                    "meeting_data":          data,
                    "partial":               {},
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

        elif msg_lower in ("no", "n"):
            clear_state(user_id)

            final_response = (
                f"📅 Meeting Confirmed\n"
                f"👉 {data.get('meeting_url')}\n"
                f"🕒 {data.get('date')} {data.get('time')}"
            )

        else:
            final_response = "❓ Reply yes or no"

    # =====================================================
    # FALLBACK — LLM
    # =====================================================
    if final_response is None:
        final_response = ask_llm(message)

    save_bot(user_id, final_response)
    return {"message": final_response}