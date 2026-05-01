import requests
from config.config import RECALL_API_KEY, BASE_URL
from dotenv import load_dotenv

load_dotenv(override=True)

def _headers() -> dict:
    return {
        "Authorization": RECALL_API_KEY,
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def create_bot(meeting_url: str, webhook_url: str) -> dict:
    """
    Create a Recall.ai bot and send it to the meeting.
    Records mixed audio as MP3.
    """
    payload = {
        "meeting_url": meeting_url,
        "bot_name": "Meeting Recorder",
        "recording_config": {
            "audio_mixed_mp3": {},
        },
        "webhook_url": webhook_url,
    }

    response = requests.post(
        f"{BASE_URL}/bot/",
        json=payload,
        headers=_headers(),
        timeout=30,
    )

    print(f"[create_bot] status={response.status_code}  body={response.text}")
    response.raise_for_status()
    return response.json()


def get_bot(bot_id: str) -> dict:
    """
    Fetch the full bot object from Recall API.
    Includes the recordings list with media_shortcuts.
    """
    response = requests.get(
        f"{BASE_URL}/bot/{bot_id}/",
        headers=_headers(),
        timeout=30,
    )
    print(f"[get_bot] status={response.status_code}")
    response.raise_for_status()
    return response.json()


def get_mixed_audio_url(bot_id: str) -> str | None:
    """
    Poll Recall API and return the MP3 CDN download URL once ready.

    Path inside Recall response:
      recordings[0].media_shortcuts.audio_mixed.status.code == "done"
      recordings[0].media_shortcuts.audio_mixed.data.download_url

    Returns:
        CDN download URL string if ready, None if still processing.
    """
    bot        = get_bot(bot_id)
    recordings = bot.get("recordings", [])

    print(f"[get_mixed_audio_url] recordings count = {len(recordings)}")

    if not recordings:
        print("   ⚠️  No recordings yet")
        return None

    for recording in recordings:
        print(f"   recording id = {recording.get('id')}")
        print(f"   recording    = {recording}")

        media_shortcuts = recording.get("media_shortcuts", {})
        audio           = media_shortcuts.get("audio_mixed")

        if not audio:
            print("   ⚠️  audio_mixed not in media_shortcuts yet")
            continue

        status_code = audio.get("status", {}).get("code")
        print(f"   audio_mixed status = {status_code}")

        if status_code == "done":
            download_url = audio.get("data", {}).get("download_url")
            print(f"   ✅ download_url = {download_url}")
            return download_url
        else:
            print(f"   ⏳ audio_mixed not ready yet (status={status_code})")

    return None