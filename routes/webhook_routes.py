# routes/webhook.py
from fastapi import APIRouter, Request
from services.webhook_handler import handle_webhook_event
from dotenv import load_dotenv

load_dotenv(override=True)
router = APIRouter()


@router.get("/webhook", operation_id="webhook_probe")
async def webhook_probe():
    """Health check — confirms the webhook URL is reachable by Recall.ai."""
    print("✅ Webhook GET probe — reachable")
    return {"status": "webhook reachable"}


@router.post("/webhook", operation_id="webhook_receiver")
async def webhook_receiver(request: Request):
    """
    Recall.ai calls this when the bot status changes.
    When status.code == 'call_ended' or 'recording_done',
    the MP3 is automatically downloaded to recordings/ folder.
    """
    try:
        data = await request.json()
    except Exception as e:
        print(f"❌ Failed to parse webhook JSON: {e}")
        return {"status": "invalid json"}

    if not data:
        print("⚠️  Empty webhook body received")
        return {"status": "ignored"}

    print("\n📥 ================= WEBHOOK RECEIVED =================")
    print("FULL DATA:", data)
    print("=====================================================\n")
    print(f"   event  : {data.get('event')}")
    print(f"   bot_id : {data.get('data', {}).get('bot_id')}")
    print(f"   status : {data.get('data', {}).get('status', {}).get('code')}")

    handle_webhook_event(data)
    return {"status": "ok"}


@router.get("/test-webhook", summary="Test Webhook Locally")
async def test_webhook():
    """
    Manually triggers a fake 'call_ended' webhook event for testing.
    Use this to simulate a meeting ending without a real meeting.
    """
    fake_data = {
        "event": "bot.status_change",
        "data": {
            "bot_id": "test123",
            "status": {"code": "call_ended"}
        }
    }

    handle_webhook_event(fake_data)
    return {"status": "test triggered", "fake_bot_id": "test123"}