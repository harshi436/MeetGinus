import re
import uuid
import datetime
 
from state.chat_state import get_state
from db.mongo import meeting_collection
from auth.token_service import get_token
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
 
 
# =========================
# SAFE DATETIME PARSER
# =========================
def parse_datetime(date, time):
    try:
        time = re.sub(r"\s+", " ", time).strip()
 
        # remove seconds if present
        if len(time) == 8:
            time = time[:5]
 
        if "AM" in time or "PM" in time:
            return datetime.datetime.strptime(
                f"{date} {time}",
                "%Y-%m-%d %I:%M %p"
            )
 
        return datetime.datetime.strptime(
            f"{date} {time}",
            "%Y-%m-%d %H:%M"
        )
    except Exception as e:
        print(f"[meeting_service] parse_datetime error: {e} | date={date} time={time}")
        return None
 
 
# =========================
# GET TODAY DATE
# =========================
def get_today():
    return datetime.datetime.now().strftime("%Y-%m-%d")
 
 
# =========================
# EXTRACT MEET LINK
# =========================
def extract_meet_link(event):
    if event.get("hangoutLink"):
        return event["hangoutLink"]
 
    conf = event.get("conferenceData", {})
    for ep in conf.get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            return ep.get("uri")
 
    return None
 
 
# =========================
# BUILD GOOGLE SERVICE
# =========================
def get_calendar_service(user_id):
    token = get_token(user_id)
    if not token:
        print(f"[meeting_service] No token found for user_id={user_id}")
        return None
 
    creds = Credentials(
        token=token["access_token"],
        refresh_token=token["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token["client_id"],
        client_secret=token["client_secret"]
    )
 
    return build("calendar", "v3", credentials=creds)
 
 
# =========================
# PARSE DATE+TIME FROM MESSAGE STRING
# Format: "schedule meeting YYYY-MM-DD HH:MM"
# chat.py always sends it in this exact format
# =========================
def _extract_date_time_from_msg(message: str):
    """
    Extracts date and time directly from the message string.
    chat.py sends: "schedule meeting 2026-12-06 15:00"
    Returns (date_str, time_str) or (None, None)
    """
    # Match YYYY-MM-DD HH:MM
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})', message)
    if m:
        return m.group(1), m.group(2)
    return None, None
 
 
# =========================
# MAIN HANDLER
# =========================
def handle_meeting(user_id, message):
 
    msg = message.lower().strip()
    state = get_state(user_id) or {}
 
    service = get_calendar_service(user_id)
    if not service:
        return {
            "message": "❌ Google not connected",
            "meeting_url": None,
            "event_id": None
        }
 
    # ======================================================
    # 🔄 UPDATE FLOW
    # ======================================================
    if message == "update_meeting":
 
        event_id = state.get("event_id")
        parsed   = state.get("new_meeting")
 
        if not event_id or not parsed:
            print(f"[meeting_service] update_meeting: missing event_id or new_meeting in state")
            return {
                "message": "❌ Missing meeting data",
                "meeting_url": None,
                "event_id": None
            }
 
        start = parse_datetime(parsed["date"], parsed["time"])
        if not start:
            return {
                "message": "❌ Invalid datetime",
                "meeting_url": None,
                "event_id": None
            }
 
        end = start + datetime.timedelta(minutes=30)
 
        try:
            service.events().patch(
                calendarId="primary",
                eventId=event_id,
                body={
                    "start": {
                        "dateTime": start.isoformat(),
                        "timeZone": "Asia/Kolkata"
                    },
                    "end": {
                        "dateTime": end.isoformat(),
                        "timeZone": "Asia/Kolkata"
                    }
                }
            ).execute()
 
            updated_event = service.events().get(
                calendarId="primary",
                eventId=event_id
            ).execute()
 
            meeting_url = extract_meet_link(updated_event)
 
            # fallback DB
            if not meeting_url:
                db_meeting = meeting_collection.find_one({"event_id": event_id})
                if db_meeting:
                    meeting_url = db_meeting.get("meeting_url")
 
            if not meeting_url:
                meeting_url = "https://meet.google.com (generating...)"
 
            meeting_collection.update_one(
                {"event_id": event_id},
                {
                    "$set": {
                        "date": parsed["date"],
                        "time": parsed["time"],
                        "meeting_url": meeting_url
                    }
                }
            )
 
            return {
                "message": "🔄 Meeting updated successfully",
                "meeting_url": meeting_url,
                "event_id": event_id,
                "date": parsed["date"],
                "time": parsed["time"]
            }
 
        except Exception as e:
            print(f"[meeting_service] update_meeting Google API error: {e}")
            return {
                "message": "❌ Failed to update meeting",
                "meeting_url": None,
                "event_id": None
            }
 
    # ======================================================
    # 🚀 CREATE FLOW
    # chat.py sends: "schedule meeting 2026-12-06 15:00"
    # We extract date+time directly — no re-parsing with parse_meeting()
    # ======================================================
    elif "schedule" in msg:
 
        # ✅ Extract date and time directly from the message string
        date, time = _extract_date_time_from_msg(message)
 
        if not date or not time:
            print(f"[meeting_service] CREATE: could not extract date/time from: '{message}'")
            return {
                "message": "❌ Could not understand date or time",
                "meeting_url": None,
                "event_id": None
            }
 
        start = parse_datetime(date, time)
        if not start:
            print(f"[meeting_service] CREATE: parse_datetime failed | date={date} time={time}")
            return {
                "message": "❌ Invalid time format",
                "meeting_url": None,
                "event_id": None
            }
 
        end = start + datetime.timedelta(minutes=30)
 
        try:
            event = service.events().insert(
                calendarId="primary",
                body={
                    "summary": "Meeting",
                    "start": {
                        "dateTime": start.isoformat(),
                        "timeZone": "Asia/Kolkata"
                    },
                    "end": {
                        "dateTime": end.isoformat(),
                        "timeZone": "Asia/Kolkata"
                    },
                    "conferenceData": {
                        "createRequest": {
                            "requestId": str(uuid.uuid4()),
                            "conferenceSolutionKey": {
                                "type": "hangoutsMeet"
                            }
                        }
                    }
                },
                conferenceDataVersion=1,
                sendUpdates="all"
            ).execute()
 
            event_id    = event.get("id")
            meeting_url = extract_meet_link(event)
 
            # Retry up to 5 times if meet link not yet generated
            for _ in range(5):
                if meeting_url:
                    break
                event = service.events().get(
                    calendarId="primary",
                    eventId=event_id
                ).execute()
                meeting_url = extract_meet_link(event)
 
            if not meeting_url:
                meeting_url = "https://meet.google.com (generating...)"
 
            # Save to DB
            meeting_collection.insert_one({
                "user_id":     user_id,
                "event_id":    event_id,
                "meeting_url": meeting_url,
                "date":        date,
                "time":        time,
                "created_at":  datetime.datetime.utcnow()
            })
 
            print(f"[meeting_service] ✅ Meeting created | event_id={event_id} url={meeting_url}")
 
            return {
                "message":     "📅 Meeting created",
                "meeting_url": meeting_url,
                "event_id":    event_id,
                "date":        date,
                "time":        time
            }
 
        except Exception as e:
            print(f"[meeting_service] CREATE Google API error: {e}")
            return {
                "message":     "❌ Google Calendar API error",
                "meeting_url": None,
                "event_id":    None
            }
 
    # ======================================================
    # DEFAULT — no action matched
    # ======================================================
    print(f"[meeting_service] No action matched for message: '{message}'")
    return {
        "message":     "❌ No meeting action detected",
        "meeting_url": None,
        "event_id":    None
    }