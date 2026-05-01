from fastapi import APIRouter
from pydantic import BaseModel

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

import json

router = APIRouter()


class ScheduleRequest(BaseModel):
    message: str
    auth_response: str   # 👈 ADD THIS


@router.post("/schedule")
def schedule_meeting(data: ScheduleRequest):

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    flow = Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=SCOPES,
        redirect_uri="NGROK_URL=https://thud-delicate-emptiness.ngrok-free.dev/"
    )

    # 🔥 STEP 1: FETCH TOKEN (THIS WAS MISSING)
    flow.fetch_token(authorization_response=data.auth_response)

    creds = flow.credentials

    service = build("calendar", "v3", credentials=creds)

    return {
        "status": "OAuth success",
        "message": data.message
    }