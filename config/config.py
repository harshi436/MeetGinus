# import os

# # 🔥 ADD THIS LINE HERE (TOP)
# os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
# from dotenv import load_dotenv

# load_dotenv(override=True)
# # ==============================
# # 🔹 RECALL.AI CONFIG
# # ==============================

# MONGO_URI = os.getenv("MONGO_URI")
# DB_NAME = os.getenv("DB_NAME")

# RECALL_API_KEY = os.getenv("RECALL_API_KEY")
# BASE_URL       = os.getenv("BASE_URL", "https://us-west-2.recall.ai/api/v1")

# # Ngrok public URL (no trailing slash)
# NGROK_URL   = os.getenv("NGROK_URL", "").rstrip("/")
# WEBHOOK_URL = f"{NGROK_URL}/webhook" if NGROK_URL else ""
# RECORD_API = f"{NGROK_URL}/record"
# # ==============================
# # 🔹 ASSEMBLYAI CONFIG
# # ==============================
# ASSEMBLY_API_KEY       = os.getenv("ASSEMBLY_API_KEY")
# ASSEMBLY_UPLOAD_URL    = os.getenv("ASSEMBLY_UPLOAD_URL")
# ASSEMBLY_TRANSCRIPT_URL = os.getenv("ASSEMBLY_TRANSCRIPT_URL")

# # ==============================
# # 🔹 GROQ CONFIG
# # ==============================
# GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# # SCOPES = ["https://www.googleapis.com/auth/calendar"]
# SCOPES = [
#     "https://www.googleapis.com/auth/calendar",
#     "https://www.googleapis.com/auth/userinfo.email",
#     "https://www.googleapis.com/auth/userinfo.profile",
#     "openid"
# ]
# GOOGLE_REDIRECT_URI = "https://thud-delicate-emptiness.ngrok-free.dev/auth/callback"


# # ==============================
# # 🔹 HEADER HELPERS
# # ==============================
# def get_assembly_headers():
#     if not ASSEMBLY_API_KEY:
#         raise RuntimeError("❌ ASSEMBLY_API_KEY is missing")
#     return {"authorization": ASSEMBLY_API_KEY}

# # ==============================
# # 🔹 STORAGE PATHS
# # ==============================
# # recordings/ lives at project root: <project_root>/recordings/
# RECORDINGS_DIR = os.path.join(
#     os.path.dirname(os.path.dirname(__file__)),
#     "recordings"
# )

# os.makedirs(RECORDINGS_DIR, exist_ok=True)

# # ==============================
# # 🔹 VALIDATION
# # ==============================
# if not RECALL_API_KEY:
#     raise RuntimeError("❌ RECALL_API_KEY is missing from .env")

# if not NGROK_URL:
#     print("⚠️  NGROK_URL is not set — webhook and public download URLs will not work!")

# # ==============================
# # 🔹 STARTUP DEBUG PRINTS
# # ==============================
# print("🌐 NGROK_URL      :", NGROK_URL)
# print("🔗 WEBHOOK_URL    :", WEBHOOK_URL)
# print("📁 RECORDINGS_DIR :", RECORDINGS_DIR)
# print("Recall ai :",RECALL_API_KEY)


import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# ==============================
# 🔹 RECALL.AI CONFIG
# ==============================
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
BASE_URL = os.getenv("BASE_URL", "https://us-west-2.recall.ai/api/v1")

# Ngrok public URL (no trailing slash)
NGROK_URL = os.getenv("NGROK_URL", "").rstrip("/")
WEBHOOK_URL = f"{NGROK_URL}/webhook" if NGROK_URL else ""
RECORD_API = f"{NGROK_URL}/record"

# ==============================
# 🔹 ASSEMBLYAI CONFIG
# ==============================
ASSEMBLY_API_KEY = os.getenv("ASSEMBLY_API_KEY")
ASSEMBLY_UPLOAD_URL = os.getenv("ASSEMBLY_UPLOAD_URL")
ASSEMBLY_TRANSCRIPT_URL = os.getenv("ASSEMBLY_TRANSCRIPT_URL")

# ==============================
# 🔹 GROQ CONFIG
# ==============================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ==============================
# 🔹 GOOGLE OAUTH CONFIG (FIXED)
# ==============================

# ✅ Keep scopes minimal (avoid consent errors)
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]

# ✅ EXACT redirect URI (must match Google Console)
GOOGLE_REDIRECT_URI = "https://thud-delicate-emptiness.ngrok-free.dev/auth/callback"

# ==============================
# 🔹 HEADER HELPERS
# ==============================
def get_assembly_headers():
    if not ASSEMBLY_API_KEY:
        raise RuntimeError("❌ ASSEMBLY_API_KEY is missing")
    return {"authorization": ASSEMBLY_API_KEY}

# ==============================
# 🔹 STORAGE PATHS
# ==============================
RECORDINGS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "recordings"
)

os.makedirs(RECORDINGS_DIR, exist_ok=True)

# ==============================
# 🔹 VALIDATION
# ==============================
if not RECALL_API_KEY:
    raise RuntimeError("❌ RECALL_API_KEY is missing from .env")

if not NGROK_URL:
    print("⚠️ NGROK_URL is not set — public URLs may not work!")

# ==============================
# 🔹 DEBUG PRINTS
# ==============================
print("🌐 NGROK_URL      :", NGROK_URL)
print("🔗 WEBHOOK_URL    :", WEBHOOK_URL)
print("📁 RECORDINGS_DIR :", RECORDINGS_DIR)
print("🔁 REDIRECT URI   :", GOOGLE_REDIRECT_URI)