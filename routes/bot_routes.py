import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config.config import WEBHOOK_URL
from config.config import RECALL_API_KEY, BASE_URL, NGROK_URL
from services.Recall_client import create_bot
from services.Recall_client import get_mixed_audio_url
from utils import store
from utils.store import upsert, get
from dotenv import load_dotenv
load_dotenv(override=True)
router = APIRouter()


# ── Request Model ─────────────────────────────────────────────────────────────

class JoinMeetingRequest(BaseModel):
    meeting_url: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"meeting_url": "https://meet.google.com/xxx-yyyy-zzz"}
            ]
        }
    }


# ── Endpoints — NO response_model to avoid Pydantic 422 on nested data ────────

@router.post("/join-meeting", summary="Join Meeting")
async def join_meeting(data: JoinMeetingRequest):
    """
    Send a bot to a Zoom / Google Meet / Teams meeting.
    webhook_url is auto-set from .env NGROK_URL.
    """
    print(f"🚀 Joining meeting : {data.meeting_url}")
    # print(f"   Webhook URL     : {WEBHOOK_URL}")

    if not WEBHOOK_URL.startswith("https://"):
        raise HTTPException(
        status_code=500,
        detail="❌ WEBHOOK_URL must be public HTTPS (ngrok required)"
    )

    print(f"   Webhook URL     : {WEBHOOK_URL}")

    result = create_bot(
        meeting_url=data.meeting_url,
        webhook_url=WEBHOOK_URL,
    )

    bot_id = result.get("id")
    if not bot_id:
        raise HTTPException(
            status_code=500,
            detail="Recall API did not return a bot ID. Check your API key and meeting URL.",
        )

    store.upsert(bot_id, status="recording")

    return {
        "message": "✅ Bot is joining the meeting",
        "bot_id": bot_id,
        "status_url": f"/status/{bot_id}",
        "recording_url": f"/recording/{bot_id}",
        "data": result,
    }

@router.get("/status/{bot_id}")
async def get_status(bot_id: str):
    info = get(bot_id)
    if not info:
        raise HTTPException(status_code=404, detail="Bot not found")

    try:
        mp3_url = get_mixed_audio_url(bot_id)
        if mp3_url:
            filename = f"{bot_id}.mp3"
            public_url = f"{NGROK_URL}/download/{filename}" if NGROK_URL else None
            upsert(bot_id, status="done", mp3_download_url=mp3_url, public_url=public_url)  # ← add public_url
        else:
            upsert(bot_id, status="recording")
    except Exception as e:
        print("ERROR:", e)
        upsert(bot_id, status="error")

    return {"bot_id": bot_id, **get(bot_id)}



@router.get("/recording/{bot_id}", summary="Get Recording Download Link")
async def get_recording(bot_id: str):
    info = store.get(bot_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Bot ID '{bot_id}' not found.")

    if info["status"] == "error":
        return {"bot_id": bot_id, "status": "error", "message": "❌ Recording failed.", "download_url": None}

    # Accept either public_url (set by webhook handler) or mp3_download_url (set by /status poll)
    download_url = info.get("public_url") or info.get("mp3_download_url")

    if info["status"] != "done" or not download_url:
        return {
            "bot_id": bot_id,
            "status": info["status"],
            "message": "⏳ Recording not ready yet. Keep polling GET /status/{bot_id}",
            "download_url": None,
        }

    return {
        "bot_id": bot_id,
        "status": "done",
        "message": "✅ Recording ready!",
        "download_url": download_url,
        "recall_cdn_url": info.get("mp3_download_url"),
    }
