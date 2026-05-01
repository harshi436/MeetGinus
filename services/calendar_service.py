from googleapiclient.discovery import build
import uuid
from datetime import datetime, timedelta
import time


def extract_meet_link(event: dict):
    """Safely extract Google Meet link"""
    try:
        # direct link
        if event.get("hangoutLink"):
            return event["hangoutLink"]

        # fallback: conference data
        conf = event.get("conferenceData", {})
        entry_points = conf.get("entryPoints", [])

        for ep in entry_points:
            if ep.get("entryPointType") == "video":
                return ep.get("uri")

    except:
        pass

    return None


def create_meeting(service, title, date, time_str):

    # 🔥 FIX 1: safe parsing
    try:
        start_dt = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
    except:
        start_dt = datetime.utcnow()

    end_dt = start_dt + timedelta(minutes=30)

    event_body = {
        "summary": title or "Meeting",
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Kolkata"
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Kolkata"
        },
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        }
    }

    # =========================
    # CREATE EVENT
    # =========================
    event = service.events().insert(
        calendarId="primary",
        body=event_body,
        conferenceDataVersion=1,
        sendUpdates="all"
    ).execute()

    event_id = event.get("id")

    # =========================
    # FORCE REFRESH (IMPORTANT FIX)
    # =========================
    meeting_url = extract_meet_link(event)

    if not meeting_url:
        for _ in range(5):
            time.sleep(2)

            event = service.events().get(
                calendarId="primary",
                eventId=event_id
            ).execute()

            meeting_url = extract_meet_link(event)

            if meeting_url:
                break

    return {
        "meeting_url": meeting_url,
        "event_id": event_id,
        "title": title,
        "date": date,
        "time": time_str,
        "raw": event
    }