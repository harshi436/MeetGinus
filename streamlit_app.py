# import streamlit as st
# import requests


# query_params = st.query_params

# if "user_id" in query_params:
#     st.session_state.user_id = query_params["user_id"]

# if "email" in query_params:
#     st.session_state.email = query_params["email"]

# API_URL = "https://thud-delicate-emptiness.ngrok-free.dev/chat"
# # LOGIN_URL = "https://thud-delicate-emptiness.ngrok-free.dev/auth/login?user_id=123"
# LOGIN_URL = "https://thud-delicate-emptiness.ngrok-free.dev/auth/login"

# st.set_page_config(page_title="AI Meeting Bot", layout="centered")

# # =========================
# # HEADER
# # =========================

# if "email" in st.session_state:
#     st.success(f"✅ Logged in as: {st.session_state.email}")
    
# st.title("🤖 AI Meeting Scheduler Bot")

# st.markdown("### Step 1: Login with Google")
# st.markdown(f"[🔐 Click to Login]({LOGIN_URL})")

# st.divider()

# # =========================
# # SESSION STATE
# # =========================
# if "chat" not in st.session_state:
#     st.session_state.chat = []

# # =========================
# # SHOW CHAT
# # =========================
# for msg in st.session_state.chat:
#     with st.chat_message(msg["role"]):
#         st.write(msg["content"])

# # =========================
# # INPUT
# # =========================
# user_input = st.chat_input("Type your message")

# if user_input:

#     # Show user message instantly
#     st.session_state.chat.append({"role": "user", "content": user_input})

#     with st.chat_message("user"):
#         st.write(user_input)

#     try:
#         res = requests.post(
#             API_URL,
#             json={
#                 "user_id": st.session_state.get("user_id"),
#                 "message": user_input
#             }
#         )

#         data = res.json()

#         bot_message = ""

#         # ✅ Meeting link
#         if "meeting_url" in data:
#             bot_message += f"📅 Meeting Created!\n\n🔗 {data['meeting_url']}\n\n"

#         # ✅ Main message
#         if "message" in data:
#             bot_message += data["message"]

#         if "reply" in data:
#             bot_message += data["reply"]

#         # ✅ PDF link
#         if "pdf_url" in data:
#             bot_message += f"\n\n📄 [View Report]({data['pdf_url']})"

#         # ✅ Error
#         if "error" in data:
#             bot_message = data["error"]

#         if not bot_message:
#             bot_message = "⚠️ No response from server"

#     except Exception as e:
#         bot_message = f"❌ Error: {str(e)}"

#     # Save bot response
#     st.session_state.chat.append({"role": "assistant", "content": bot_message})

#     with st.chat_message("assistant"):
#         st.write(bot_message)


import streamlit as st
import requests
import uuid

# =========================
# CONFIG
# =========================
API_URL = "https://thud-delicate-emptiness.ngrok-free.dev/chat"
BASE_URL = "https://thud-delicate-emptiness.ngrok-free.dev"

st.set_page_config(page_title="AI Meeting Bot", layout="centered")

# =========================
# SESSION INIT
# =========================
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "chat" not in st.session_state:
    st.session_state.chat = []

# =========================
# HANDLE REDIRECT PARAMS
# =========================
query_params = st.query_params

if "user_id" in query_params:
    st.session_state.user_id = query_params["user_id"]

if "email" in query_params:
    st.session_state.email = query_params["email"]

# =========================
# LOGIN URL (FIXED)
# =========================
LOGIN_URL = f"{BASE_URL}/auth/login?user_id={st.session_state.user_id}"

# =========================
# UI HEADER
# =========================
st.title("🤖 AI Meeting Scheduler Bot")

if "email" in st.session_state:
    st.success(f"✅ Logged in as: {st.session_state.email}")
else:
    st.markdown("### Step 1: Login with Google")
    st.markdown(f"[🔐 Click to Login]({LOGIN_URL})")

st.divider()

# =========================
# SHOW CHAT
# =========================
for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# =========================
# INPUT (BLOCK IF NOT LOGGED IN)
# =========================
if "email" not in st.session_state:
    st.warning("⚠️ Please login first to use chat")
    st.stop()

user_input = st.chat_input("Type your message")

if user_input:

    # Save user message
    st.session_state.chat.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.write(user_input)

    try:
        res = requests.post(
            API_URL,
            json={
                "user_id": st.session_state.user_id,
                "message": user_input
            }
        )

        data = res.json()
        bot_message = ""

        # ✅ Meeting link
        if "meeting_url" in data:
            bot_message += f"📅 Meeting Created!\n\n🔗 {data['meeting_url']}\n\n"

        # ✅ Main message
        if "message" in data:
            bot_message += data["message"]

        if "reply" in data:
            bot_message += data["reply"]

        # ✅ PDF link
        if "pdf_url" in data and data["pdf_url"]:
            bot_message += f"\n\n📄 [View Report]({data['pdf_url']})"

        # ✅ Error
        if "error" in data:
            bot_message = data["error"]

        if not bot_message:
            bot_message = "⚠️ No response from server"

    except Exception as e:
        bot_message = f"❌ Error: {str(e)}"

    # Save bot response
    st.session_state.chat.append({"role": "assistant", "content": bot_message})

    with st.chat_message("assistant"):
        st.write(bot_message)

