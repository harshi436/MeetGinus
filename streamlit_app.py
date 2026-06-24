import streamlit as st
import requests
import os
from dotenv import load_dotenv
import webbrowser
import speech_recognition as sr
 
# =========================
# LOAD ENV
# =========================
load_dotenv()
 
BASE_URL = os.getenv("NGROK_URL")
API_URL = f"{BASE_URL}/chat"
LOGIN_URL = f"{BASE_URL}/auth/login"
 
# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="Meeting Bot", layout="wide")
 
# =========================
# SESSION STATE
# =========================
if "user_id" not in st.session_state:
    st.session_state.user_id = None
 
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
 
if "mode" not in st.session_state:
    st.session_state.mode = "text"
 
recognizer = sr.Recognizer()
 
# =========================
# SIDEBAR
# =========================
st.sidebar.title("⚙️ Settings")
 
if st.sidebar.button("🔐 Login"):
    webbrowser.open(LOGIN_URL)
    st.sidebar.success("Login page opened!")
 
user_id_input = st.sidebar.text_input("Enter User ID")
 
if st.sidebar.button("✅ Confirm User"):
    if user_id_input:
        st.session_state.user_id = user_id_input
        st.sidebar.success("Logged in!")
    else:
        st.sidebar.error("Enter valid user ID")
 
# Mode selection
mode = st.sidebar.radio("Input Mode", ["Text", "Voice"])
st.session_state.mode = mode.lower()
 
# =========================
# MAIN UI
# =========================
st.title("🤖 MeetGenius")
 
# =========================
# VOICE FUNCTION
# =========================
def get_voice_input():
    try:
        with sr.Microphone() as source:
            st.info("🎤 Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
 
        text = recognizer.recognize_google(audio)
        return text
 
    except Exception:
        st.error("Voice input failed")
        return None
 
# =========================
# CHAT DISPLAY
# =========================
for chat in st.session_state.chat_history:
    with st.chat_message(chat["role"]):
        st.markdown(chat["content"])
 
# =========================
# INPUT SECTION
# =========================
if st.session_state.user_id:
 
    if st.session_state.mode == "text":
        user_input = st.chat_input("Type your message...")
    else:
        if st.button("🎤 Speak"):
            user_input = get_voice_input()
            if user_input:
                st.success(f"You: {user_input}")
        else:
            user_input = None
 
    if user_input:
 
        # Add user message
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input
        })
 
        with st.chat_message("user"):
            st.markdown(user_input)
 
        # =========================
        # API CALL
        # =========================
        try:
            res = requests.post(
                API_URL,
                json={
                    "user_id": st.session_state.user_id,
                    "message": user_input
                },
                timeout=60
            )
 
            response = res.json()
            bot_msg = response.get("message", "No response")
 
        except Exception as e:
            bot_msg = f"❌ API Error: {e}"
 
        # Add bot response
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": bot_msg
        })
 
        with st.chat_message("assistant"):
            st.markdown(bot_msg)
 
else:
    st.warning("⚠️ Please login and enter user ID from sidebar")
 
# =========================
# CLEAR CHAT
# =========================
if st.sidebar.button("🗑 Clear Chat"):
    st.session_state.chat_history = []
