# services/webhook_handler.py
import threading
import time
from config.config import NGROK_URL, RECORDINGS_DIR
from services.downloader import download_mp3
from services.Recall_client import get_mixed_audio_url
from utils import store
from dotenv import load_dotenv

load_dotenv(override=True)

def handle_webhook_event(data: dict):
    event = data.get("event")
    print(f"📌 Event: {event}")
    print("📦 FULL WEBHOOK PAYLOAD:", data)

    if event not in ("bot.status_change", "bot.recording_ready"):
        print("   (ignored event)")
        return

    bot_id      = data.get("data", {}).get("bot_id")
    status_code = data.get("data", {}).get("status", {}).get("code")
    sub_code    = data.get("data", {}).get("status", {}).get("sub_code")

    print(f"   bot_id   = {bot_id}")
    print(f"   status   = {status_code}")
    print(f"   sub_code = {sub_code}")

    if not bot_id:
        print("   ⚠️  No bot_id in payload — ignoring")
        return

    if status_code in ("call_ended", "recording_processing", "recording_done"):
        store.upsert(bot_id, status="processing")

        def safe_process(bot_id):
            try:
                _process_recording(bot_id)
            except Exception as e:
                print(f"❌ THREAD ERROR for bot {bot_id}: {e}")
                store.upsert(bot_id, status="error")

        thread = threading.Thread(target=safe_process, args=(bot_id,), daemon=True)
        thread.start()

    elif status_code in ("error", "fatal"):
        store.upsert(bot_id, status="error")
        print(f"   ❌ Bot ended with error: {status_code} / {sub_code}")

    else:
        print(f"   ℹ️  Intermediate status '{status_code}' — waiting")


def _process_recording(bot_id: str):
    """
    Background thread:
      1. Poll Recall API until MP3 CDN URL is available
      2. Download MP3 to recordings/{bot_id}.mp3
      3. Update store with local_file + public_url
    """
    print(f"\n🔄 Processing recording for bot {bot_id} ...")

    MAX_RETRIES  = 30
    WAIT_SECONDS = 20

    # ── Poll until MP3 URL is available ──────────────────────────────────────
    mp3_url = None
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"   Attempt {attempt}/{MAX_RETRIES} — checking for MP3 URL...")
        mp3_url = get_mixed_audio_url(bot_id)
        if mp3_url:
            break
        print(f"   ⏳ Not ready yet — waiting {WAIT_SECONDS}s...")
        time.sleep(WAIT_SECONDS)

    if not mp3_url:
        print(f"   ❌ MP3 URL never became available for bot {bot_id}")
        store.upsert(bot_id, status="error", report_status="error")
        return

    print(f"   ✅ mp3_url = {mp3_url}")
    store.upsert(bot_id, mp3_download_url=mp3_url)

    # ── Download MP3 to disk into recordings/ folder ──────────────────────────
    local_file = download_mp3(mp3_url, bot_id, RECORDINGS_DIR)
    print(f"   ✅ local_file = {local_file}")

    if not NGROK_URL:
        raise ValueError("❌ NGROK_URL is empty — cannot build public download URL")

    filename   = f"{bot_id}.mp3"
    public_url = f"{NGROK_URL}/download/{filename}"

    # ── Mark as fully done ────────────────────────────────────────────────────
    store.upsert(
        bot_id,
        status="done",
        report_status="done",
        local_file=local_file,
        public_url=public_url,
    )

    print(f"\n🎉 Audio ready!")
    print(f"   Local  : {local_file}")
    print(f"   Public : {public_url}\n")