from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routes.auth_routes import router as auth_router
from routes.chat_routes import router as chat_router
from Record import record
from services.scheduler_service import start_scheduler
from threading import Thread
from pydantic import BaseModel
from db.mongo import chat_collection, report_collection  # ✅ added
from fastapi.responses import Response
import os

app = FastAPI()

# =========================
# PATH SETUP
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# =========================
# START SCHEDULER
# =========================
@app.on_event("startup")
def startup_event():
    print("🚀 App started")
    start_scheduler()

app.include_router(auth_router)
app.include_router(chat_router)

# =========================
# STATIC FILES (PDF)
# =========================
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")

# =========================
# RECORD API
# =========================
class MeetingRequest(BaseModel):
    meeting_url: str
    meeting_id: str | None = None
    user_id: str | None = None


@app.post("/record")
def record_meeting(data: MeetingRequest):

    try:
        # =========================
        # ✅ DUPLICATE CHECK (CRITICAL FIX)
        # =========================
        if data.meeting_id:
            existing = report_collection.find_one({
                "meeting_id": data.meeting_id
            })

            if existing:
                print("⚠️ Duplicate recording prevented")

                return {
                    "message": "⚠️ Recording already exists or in progress",
                    "meeting_url": data.meeting_url
                }

        # =========================
        # 🚀 START RECORDING THREAD
        # =========================
        Thread(
            target=record,
            args=(data.meeting_url, data.meeting_id, data.user_id),
            daemon=True
        ).start()

        return {
            "message": "⏳ Recording started",
            "meeting_url": data.meeting_url
        }

    except Exception as e:
        print("❌ Record error:", e)
        return {"error": "Recording failed"}


# =========================
# FETCH CHAT MESSAGES
# =========================
@app.get("/messages/{user_id}")
def get_messages(user_id: str):

    messages = list(
        chat_collection.find({"user_id": user_id})
        .sort("created_at", 1)
    )

    formatted = []
    for m in messages:
        formatted.append({
            "role": "assistant" if m["role"] == "bot" else "user",
            "content": m["message"]
        })

    return {"messages": formatted}


# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"message": "AI Meeting Bot Running"}




@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)  # "No Content" — tells browser not to bother