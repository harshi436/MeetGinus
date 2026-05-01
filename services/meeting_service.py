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
    except:
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
    # 🔥 UPDATE FLOW (STRICT)
    # ======================================================
    if message == "update_meeting":
 
        event_id = state.get("event_id")
        parsed = state.get("new_meeting")
 
        if not event_id or not parsed:
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
 
        # UPDATE EVENT
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
 
        # UPDATE DB
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
 
    # ======================================================
    # 🚀 CREATE FLOW (STRICT)
    # ======================================================
    elif "schedule" in msg:
 
        from services.parser import parse_meeting
 
        parsed = parse_meeting(user_id, message)
 
        if parsed.get("status") == "missing":
            # fallback basic parsing
            match = re.search(r"(\d{1,2}:\d{2})", message)
            if not match:
                return {
                    "message": "❌ Could not understand time",
                    "meeting_url": None,
                    "event_id": None
                }
 
            parsed = {
                "title": "Meeting",
                "date": get_today(),
                "time": match.group(1)
            }
 
        start = parse_datetime(parsed["date"], parsed["time"])
        if not start:
            return {
                "message": "❌ Invalid time format",
                "meeting_url": None,
                "event_id": None
            }
 
        end = start + datetime.timedelta(minutes=30)
 
        # CREATE EVENT
        event = service.events().insert(
            calendarId="primary",
            body={
                "summary": parsed.get("title", "Meeting"),
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
 
        event_id = event.get("id")
 
        meeting_url = extract_meet_link(event)
 
        # retry for meet link
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
 
        # SAVE DB
        meeting_collection.insert_one({
            "user_id": user_id,
            "event_id": event_id,
            "meeting_url": meeting_url,
            "date": parsed["date"],
            "time": parsed["time"],
            "created_at": datetime.datetime.utcnow()
        })
 
        return {
            "message": "📅 Meeting created",
            "meeting_url": meeting_url,
            "event_id": event_id,
            "date": parsed["date"],
            "time": parsed["time"]
        }
 
    # ======================================================
    # DEFAULT
    # ======================================================
    return {
        "message": "❌ No meeting action detected",
        "meeting_url": None,
        "event_id": None
    }

























































































# import re
# import uuid
# import datetime

# from state.chat_state import get_state
# from db.mongo import meeting_collection
# from auth.token_service import get_token
# from googleapiclient.discovery import build
# from google.oauth2.credentials import Credentials


# # =========================
# # SAFE DATETIME PARSER
# # =========================
# def parse_datetime(date, time):
#     try:
#         time = re.sub(r"\s+", " ", time).strip()

#         # remove seconds if present
#         if len(time) == 8:
#             time = time[:5]

#         if "AM" in time or "PM" in time:
#             return datetime.datetime.strptime(
#                 f"{date} {time}",
#                 "%Y-%m-%d %I:%M %p"
#             )

#         return datetime.datetime.strptime(
#             f"{date} {time}",
#             "%Y-%m-%d %H:%M"
#         )
#     except:
#         return None


# # =========================
# # GET TODAY DATE
# # =========================
# def get_today():
#     return datetime.datetime.now().strftime("%Y-%m-%d")


# # =========================
# # EXTRACT MEET LINK
# # =========================
# def extract_meet_link(event):
#     if event.get("hangoutLink"):
#         return event["hangoutLink"]

#     conf = event.get("conferenceData", {})
#     for ep in conf.get("entryPoints", []):
#         if ep.get("entryPointType") == "video":
#             return ep.get("uri")

#     return None


# # =========================
# # BUILD GOOGLE SERVICE
# # =========================
# def get_calendar_service(user_id):
#     token = get_token(user_id)
#     if not token:
#         return None

#     creds = Credentials(
#         token=token["access_token"],
#         refresh_token=token["refresh_token"],
#         token_uri="https://oauth2.googleapis.com/token",
#         client_id=token["client_id"],
#         client_secret=token["client_secret"]
#     )

#     return build("calendar", "v3", credentials=creds)


# # =========================
# # MAIN HANDLER
# # =========================
# def handle_meeting(user_id, message):

#     msg = message.lower().strip()
#     state = get_state(user_id) or {}

#     service = get_calendar_service(user_id)
#     if not service:
#         return {
#             "message": "❌ Google not connected",
#             "meeting_url": None,
#             "event_id": None
#         }

#     # ======================================================
#     # 🔥 UPDATE FLOW (STRICT)
#     # ======================================================
#     if message == "update_meeting":

#         event_id = state.get("event_id")
#         parsed = state.get("new_meeting")

#         if not event_id or not parsed:
#             return {
#                 "message": "❌ Missing meeting data",
#                 "meeting_url": None,
#                 "event_id": None
#             }

#         start = parse_datetime(parsed["date"], parsed["time"])
#         if not start:
#             return {
#                 "message": "❌ Invalid datetime",
#                 "meeting_url": None,
#                 "event_id": None
#             }

#         end = start + datetime.timedelta(minutes=30)

#         # UPDATE EVENT
#         service.events().patch(
#             calendarId="primary",
#             eventId=event_id,
#             body={
#                 "start": {
#                     "dateTime": start.isoformat(),
#                     "timeZone": "Asia/Kolkata"
#                 },
#                 "end": {
#                     "dateTime": end.isoformat(),
#                     "timeZone": "Asia/Kolkata"
#                 }
#             }
#         ).execute()

#         updated_event = service.events().get(
#             calendarId="primary",
#             eventId=event_id
#         ).execute()

#         meeting_url = extract_meet_link(updated_event)

#         # fallback DB
#         if not meeting_url:
#             db_meeting = meeting_collection.find_one({"event_id": event_id})
#             if db_meeting:
#                 meeting_url = db_meeting.get("meeting_url")

#         if not meeting_url:
#             meeting_url = "https://meet.google.com (generating...)"

#         # UPDATE DB
#         meeting_collection.update_one(
#             {"event_id": event_id},
#             {
#                 "$set": {
#                     "date": parsed["date"],
#                     "time": parsed["time"],
#                     "meeting_url": meeting_url
#                 }
#             }
#         )

#         return {
#             "message": "🔄 Meeting updated successfully",
#             "meeting_url": meeting_url,
#             "event_id": event_id,
#             "date": parsed["date"],
#             "time": parsed["time"]
#         }

#     # ======================================================
#     # 🚀 CREATE FLOW (STRICT)
#     # ======================================================
#     elif "schedule" in msg:

#         from services.parser import parse_meeting

#         parsed = parse_meeting(user_id, message)

#         if not parsed:
#             # fallback basic parsing
#             match = re.search(r"(\d{1,2}:\d{2})", message)
#             if not match:
#                 return {
#                     "message": "❌ Could not understand time",
#                     "meeting_url": None,
#                     "event_id": None
#                 }

#             parsed = {
#                 "title": "Meeting",
#                 "date": get_today(),
#                 "time": match.group(1)
#             }

#         start = parse_datetime(parsed["date"], parsed["time"])
#         if not start:
#             return {
#                 "message": "❌ Invalid time format",
#                 "meeting_url": None,
#                 "event_id": None
#             }

#         end = start + datetime.timedelta(minutes=30)

#         # CREATE EVENT
#         event = service.events().insert(
#             calendarId="primary",
#             body={
#                 "summary": parsed.get("title", "Meeting"),
#                 "start": {
#                     "dateTime": start.isoformat(),
#                     "timeZone": "Asia/Kolkata"
#                 },
#                 "end": {
#                     "dateTime": end.isoformat(),
#                     "timeZone": "Asia/Kolkata"
#                 },
#                 "conferenceData": {
#                     "createRequest": {
#                         "requestId": str(uuid.uuid4()),
#                         "conferenceSolutionKey": {
#                             "type": "hangoutsMeet"
#                         }
#                     }
#                 }
#             },
#             conferenceDataVersion=1,
#             sendUpdates="all"
#         ).execute()

#         event_id = event.get("id")

#         meeting_url = extract_meet_link(event)

#         # retry for meet link
#         for _ in range(5):
#             if meeting_url:
#                 break
#             event = service.events().get(
#                 calendarId="primary",
#                 eventId=event_id
#             ).execute()
#             meeting_url = extract_meet_link(event)

#         if not meeting_url:
#             meeting_url = "https://meet.google.com (generating...)"

#         # SAVE DB
#         meeting_collection.insert_one({
#             "user_id": user_id,
#             "event_id": event_id,
#             "meeting_url": meeting_url,
#             "date": parsed["date"],
#             "time": parsed["time"],
#             "created_at": datetime.datetime.utcnow()
#         })

#         return {
#             "message": "📅 Meeting created",
#             "meeting_url": meeting_url,
#             "event_id": event_id,
#             "date": parsed["date"],
#             "time": parsed["time"]
#         }

#     # ======================================================
#     # DEFAULT
#     # ======================================================
#     return {
#         "message": "❌ No meeting action detected",
#         "meeting_url": None,
#         "event_id": None
#     }