from googleapiclient.discovery import build
import uuid
from datetime import datetime, timedelta


def extract_meet_link(event):
    """SAFE extract Meet link"""
    if event.get("hangoutLink"):
        return event["hangoutLink"]

    conf = event.get("conferenceData", {})
    for ep in conf.get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            return ep.get("uri")

    return None


def create_meeting(creds, title, date, time):

    service = build("calendar", "v3", credentials=creds)

    start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
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
                "conferenceSolutionKey": {
                    "type": "hangoutsMeet"
                }
            }
        }
    }

    event = service.events().insert(
        calendarId="primary",
        body=event_body,
        conferenceDataVersion=1,
        sendUpdates="all"
    ).execute()

    event_id = event.get("id")

    # FORCE REFRESH (Google delay fix)
    meeting_url = extract_meet_link(event)

    for _ in range(5):
        if meeting_url:
            break

        event = service.events().get(
            calendarId="primary",
            eventId=event_id
        ).execute()

        meeting_url = extract_meet_link(event)

    return {
        "meeting_url": meeting_url,
        "event_id": event_id,
        "raw": event
    }