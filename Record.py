# import asyncio
# import os
# import time
# import requests
# import datetime
# from dotenv import load_dotenv

# from services.audio_to_json import transcribe_by_bot_id
# from services.json_to_summary import json_to_summary
# from services.report_generator import json_to_pdf
# from db.mongo import report_collection

# load_dotenv()

# RECALL_API_KEY = os.getenv("RECALL_API_KEY")
# BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

# RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")
# os.makedirs(RECORDINGS_DIR, exist_ok=True)


# # =========================
# # CREATE BOT
# # =========================
# def create_bot(meeting_url, google_calendar_event_id=None):
#     payload = {
#         "meeting_url": meeting_url,
#         "bot_name": "Recorder",
#         "recording_config": {
#             "audio_mixed_mp3": {}
#         }
#     }
    
#     if google_calendar_event_id:
#         payload["calendar_event_id"] = google_calendar_event_id

#     r = requests.post(
#         f"{BASE_URL}/bot/",
#         json=payload,
#         headers={"Authorization": RECALL_API_KEY}
#     )

#     r.raise_for_status()
#     return r.json()["id"]


# # =========================
# # GET MP3 URL
# # =========================
# def get_mp3_url(bot_id):
#     r = requests.get(
#         f"{BASE_URL}/bot/{bot_id}/",
#         headers={"Authorization": RECALL_API_KEY}
#     )

#     r.raise_for_status()

#     for rec in r.json().get("recordings", []):
#         audio = rec.get("media_shortcuts", {}).get("audio_mixed")

#         if audio and audio.get("status", {}).get("code") == "done":
#             return audio.get("data", {}).get("download_url")

#     return None


# # =========================
# # PARTICIPANTS (FIXED)
# # =========================

# def extract_participants(bot_id):
#     try:
#         r = requests.get(
#             f"{BASE_URL}/bot/{bot_id}/",
#             headers={"Authorization": RECALL_API_KEY}
#         )

#         data = r.json()

#         participants = []

#         raw = data.get("participants", [])

#         for p in raw:
#             participants.append({
#                 "name": p.get("name") or "Unknown",
#                 "join_time": p.get("join_time"),
#                 "leave_time": p.get("leave_time"),
#                 "duration": p.get("duration") or None
#             })

#         return participants

#     except Exception as e:
#         print("Participant fetch error:", e)
#         return []


# # =========================
# # MAIN RECORD FUNCTION
# # =========================
# def record(meeting_url, meeting_id=None, user_id=None):

#     bot_id = create_bot(meeting_url)

#     # =========================
#     # WAIT FOR AUDIO
#     # =========================
#     while True:
#         mp3 = get_mp3_url(bot_id)
#         if mp3:
#             break
#         time.sleep(10)

#     # =========================
#     # DOWNLOAD AUDIO
#     # =========================
#     path = os.path.join(RECORDINGS_DIR, f"{bot_id}.mp3")

#     with requests.get(mp3, stream=True) as r:
#         r.raise_for_status()
#         with open(path, "wb") as f:
#             for chunk in r.iter_content(1024):
#                 f.write(chunk)

#     # =========================
#     # TRANSCRIPTION
#     # =========================
#     json_path = asyncio.run(transcribe_by_bot_id(bot_id))
#     summary = json_to_summary(json_path)

#     # =========================
#     # PDF GENERATION
#     # =========================
#     pdf_path = json_to_pdf(summary, filename=f"{meeting_id}.pdf")

#     # =========================
#     # PARTICIPANTS (FINAL FIXED)
#     # =========================
#     participants = extract_participants(bot_id)

#     # =========================
#     # SAVE TO DB
#     # =========================
#     report_collection.insert_one({
#         "user_id": user_id,
#         "meeting_id": meeting_id,
#         "meeting_url": meeting_url,
#         "audio": path,
#         "json": json_path,
#         "pdf_report_path": pdf_path,
#         "participants": participants,
#         "created_at": datetime.datetime.utcnow()
#     })

#     return path













import asyncio
import os
import time
import requests
import datetime
from dotenv import load_dotenv

from services.audio_to_json import transcribe_by_bot_id
from services.json_to_summary import json_to_summary
from services.report_generator import json_to_pdf
from services.participants_tracker import build_participants_with_time
from db.mongo import report_collection

load_dotenv()

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)


# =========================
# CREATE BOT
# =========================
def create_bot(meeting_url, google_calendar_event_id=None):
    payload = {
        "meeting_url": meeting_url,
        "bot_name": "Recorder",
        "recording_config": {
            "audio_mixed_mp3": {}
        }
    }

    if google_calendar_event_id:
        payload["calendar_event_id"] = google_calendar_event_id

    r = requests.post(
        f"{BASE_URL}/bot/",
        json=payload,
        headers={"Authorization": RECALL_API_KEY}
    )

    r.raise_for_status()
    return r.json()["id"]


# =========================
# GET MP3 URL
# =========================
def get_mp3_url(bot_id):
    r = requests.get(
        f"{BASE_URL}/bot/{bot_id}/",
        headers={"Authorization": RECALL_API_KEY}
    )

    r.raise_for_status()

    for rec in r.json().get("recordings", []):
        audio = rec.get("media_shortcuts", {}).get("audio_mixed")

        if audio and audio.get("status", {}).get("code") == "done":
            return audio.get("data", {}).get("download_url")

    return None


# =========================
# MAIN RECORD FUNCTION
# =========================
def record(meeting_url, meeting_id=None, user_id=None):

    # 🔹 Step 1: Create bot
    bot_id = create_bot(meeting_url)

    # 🔹 Step 2: Wait for recording
    while True:
        mp3 = get_mp3_url(bot_id)
        if mp3:
            break
        time.sleep(10)

    # 🔹 Step 3: Download audio
    path = os.path.join(RECORDINGS_DIR, f"{bot_id}.mp3")

    with requests.get(mp3, stream=True) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)

    # 🔹 Step 4: Convert audio → transcript
    json_path = asyncio.run(transcribe_by_bot_id(bot_id))

    # 🔹 Step 5: Extract filename (CORRECT)
    audio_filename = os.path.basename(path)

    # 🔹 Step 6: Generate AI report (ONLY ONCE)
    report = json_to_summary(json_path, audio_filename)

    # 🔹 Step 7: Generate PDF
    pdf_path = json_to_pdf(report, filename=f"{meeting_id}.pdf")

    # 🔹 Step 8: Build participants with join/leave time
    participants_with_time = build_participants_with_time(report)

    # 🔹 Step 9: Store in MongoDB
    report_collection.insert_one({
        "user_id": user_id,
        "meeting_id": meeting_id,
        "meeting_url": meeting_url,
        "audio": path,
        "json": json_path,
        "pdf_report_path": pdf_path,
        "participants": participants_with_time,
        "created_at": datetime.datetime.utcnow()
    })

    # 🔹 Step 10: Return audio path
    return path