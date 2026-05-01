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
# LOGIN FLOW
# =========================
print("🔐 Opening login...")
webbrowser.open(LOGIN_URL)
 
print("\n👉 After login, copy user_id from browser response")
user_id = input("Enter user_id: ").strip()
 
print(f"✅ Logged in! User ID: {user_id}")
 
recognizer = sr.Recognizer()
 
 
# =========================
# VOICE INPUT
# =========================
def get_voice_input():
    try:
        with sr.Microphone() as source:
            print("🎤 Speak now...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(source, timeout=20, phrase_time_limit=20)
 
        text = recognizer.recognize_google(audio)
        print("🗣 You (voice):", text)
        return text
 
    except Exception:
        print("⚠️ Voice input failed")
        return None
 
 
# =========================
# MODE SELECT (ONE TIME)
# =========================
print("\nChoose input mode:")
print("1. Type message")
print("2. Speak (voice)")
 
while True:
    mode = input("Enter choice (1/2): ").strip()
    if mode in ["1", "2"]:
        break
    print("❌ Invalid choice")
 
print(f"✅ Mode locked: {'TEXT' if mode == '1' else 'VOICE'}")
print("Type 'quit_app' anytime to exit\n")
 
 
# =========================
# MAIN LOOP
# =========================
while True:
 
    # =========================
    # INPUT
    # =========================
    if mode == "1":
        msg = input("You (text): ").strip()
    else:
        msg = get_voice_input()
        if not msg:
            continue
 
    # =========================
    # EXIT
    # =========================
    if msg.lower() == "quit_app":
        print("👋 Exiting...")
        break
 
    if not msg:
        print("⚠️ Empty input")
        continue
 
 
    # =========================
    # API CALL
    # =========================
    try:
        res = requests.post(
            API_URL,
            json={
                "user_id": user_id,
                "message": msg
            },
            timeout=30
        )
 
        response = res.json()
        bot_msg = response.get("message", "")
 
        print("\nBot:")
        print(bot_msg)
 
    except Exception as e:
        print("❌ API Error:", e)