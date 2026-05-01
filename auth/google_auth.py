import os
import uuid
from datetime import datetime

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from config.config import SCOPES, GOOGLE_REDIRECT_URI
from auth.token_service import save_token
from db.mongo import user_collection

# os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

flow_store = {}


def create_flow():
    return Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )


# =========================
# LOGIN
# =========================
def get_auth_url():
    flow = create_flow()

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )

    flow_store[state] = flow

    print("🔥 LOGIN STATE:", state)

    return auth_url


# =========================
# CALLBACK (FIXED - NO LOOP)
# =========================
def handle_callback(full_url: str, state: str):

    if state not in flow_store:
        return {"error": "Session expired. Please login again"}

    flow = flow_store[state]

    # exchange code
    flow.fetch_token(authorization_response=full_url)
    creds = flow.credentials

    # get user info
    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()

    email = user_info.get("email")

    # check user
    user = user_collection.find_one({"email": email})

    if user:
        user_id = user["user_id"]
    else:
        user_id = str(uuid.uuid4())
        user_collection.insert_one({
            "user_id": user_id,
            "email": email,
            "created_at": datetime.utcnow()
        })

    # save token
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "email": email
    }

    save_token(user_id, token_data)

    # cleanup
    del flow_store[state]

    print("✅ LOGIN SUCCESS:", email)

    # 🚨 IMPORTANT: RETURN ONLY DATA (NO REDIRECT LOOP)
    return {
        "message": "Login successful",
        "user_id": user_id,
        "email": email
    }