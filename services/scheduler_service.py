import json
import os
from datetime import datetime
import requests
from config.config import NGROK_URL

RECORD_API = f"{NGROK_URL}/record"
JOBS_FILE = "scheduled_jobs.json"


def load_jobs():
    if not os.path.exists(JOBS_FILE):
        return {}
    try:
        with open(JOBS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_jobs(jobs):
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

def add_scheduled_meeting(job_id, meeting_url, scheduled_at_iso, user_id):

    if not job_id or not meeting_url or meeting_url == "None":
        print("❌ Invalid job data — skipped")
        return

    jobs = load_jobs()

    jobs[job_id] = {
        "meeting_url": meeting_url,
        "scheduled_at": scheduled_at_iso,
        "user_id": user_id,
        "status": "pending"
    }

    save_jobs(jobs)

    print(f"✅ Job Scheduled: {job_id}")

def check_jobs():

    jobs = load_jobs()
    now = datetime.now()

    for job_id, job in jobs.items():

        if job.get("status") != "pending":
            continue

        meeting_url = job.get("meeting_url")

        if not meeting_url:
            job["status"] = "failed"
            continue

        scheduled = datetime.fromisoformat(job["scheduled_at"])

        if now >= scheduled:

            print(f"🚀 Running Job: {job_id}")

            res = requests.post(RECORD_API, json={
                "meeting_url": meeting_url,
                "meeting_id": job_id,
                "user_id": job["user_id"]
            })

            if res.status_code == 200:
                job["status"] = "done"
            else:
                job["status"] = "failed"

    save_jobs(jobs)


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(check_jobs, "interval", seconds=30)
    scheduler.start()

    print("⏰ Scheduler running")