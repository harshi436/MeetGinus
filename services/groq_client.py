# from groq import Groq
# from config.config import GROQ_API_KEY
# from db.mongo import chat_collection
 
# client = Groq(api_key=GROQ_API_KEY)
 
 
# # ✅ Get last messages from DB
# def get_last_messages(user_id, limit=10):
#     chats = chat_collection.find(
#         {"user_id": user_id}
#     ).sort("_id", -1).limit(limit)
 
#     return list(chats)
 
 
# # ✅ Convert DB chats → LLM format
# def build_chat_context(user_id):
 
#     messages = []
 
#     chats = get_last_messages(user_id)
 
#     for chat in reversed(chats):
 
#         role = chat.get("role", "user")
 
#         # 🔥 FIX ROLE
#         if role not in ["system", "user", "assistant"]:
#             if role == "bot":
#                 role = "assistant"
#             else:
#                 role = "user"
 
#         messages.append({
#             "role": role,
#             "content": chat.get("message", "")
#         })
 
#     return messages
 
 
# # ✅ MAIN CHAT FUNCTION
# def chat_with_groq(user_id: str, message: str):
 
#     # 🔹 Step 1: Load previous conversation
#     history = build_chat_context(user_id)
 
#     # 🔹 Step 2: Build messages
#     messages = [
#         {"role": "system", "content": "You are a helpful assistant."}
#     ]
 
#     # add previous chats
#     messages.extend(history)
 
#     # ✅ add current user message (FIXED)
#     messages.append({
#         "role": "user",
#         "content": message
#     })
 
#     # 🔹 Step 3: Call Groq
#     response = client.chat.completions.create(
#         model="llama-3.1-8b-instant",
#         messages=messages,
#         temperature=0.5,
#         max_tokens=300
#     )
 
#     reply = response.choices[0].message.content
 
#     # 🔹 Step 4: Save conversation in DB
#     chat_collection.insert_one({
#         "user_id": user_id,
#         "role": "user",
#         "message": message
#     })
 
#     chat_collection.insert_one({
#         "user_id": user_id,
#         "role": "assistant",   # ✅ ALWAYS assistant
#         "message": reply
#     })
 
#     return reply
 
# def ask_llm(message):
#     chat_completion = client.chat.completions.create(
#         model="llama-3.1-8b-instant",
#         messages=[
#             {
#                 "role": "system",
#                 "content": (
#                     "You are a STRICT Meeting Scheduling Assistant.\n\n"
 
#                     "====================\n"
#                     "ROLE LIMITATION\n"
#                     "====================\n"
#                     "You ONLY handle:\n"
#                     "- scheduling meetings\n"
#                     "- updating meetings\n"
#                     "- confirming meetings\n"
#                     "- meeting history\n\n"
 
#                     "You MUST refuse all other topics.\n\n"
 
#                     "====================\n"
#                     "GREETING RULE\n"
#                     "====================\n"
#                     "- Reply naturally and short\n"
#                     "- Do NOT repeat same greeting\n"
#                     "- Do NOT explain capabilities unless asked\n\n"
 
#                     "====================\n"
#                     "CRITICAL OUTPUT RULE (VERY IMPORTANT)\n"
#                     "====================\n"
#                     "If you return meeting data, ALWAYS follow JSON format:\n\n"
#                     "{\n"
#                     "  \"title\": \"\",\n"
#                     "  \"date\": \"YYYY-MM-DD\",\n"
#                     "  \"time\": \"HH:MM (24-hour format)\",\n"
#                     "  \"relative\": \"\",\n"
#                     "  \"duration\": 30\n"
#                     "}\n\n"
 
#                     "====================\n"
#                     "TIME VALIDATION RULE (STRICT)\n"
#                     "====================\n"
#                     "- time MUST be valid 24-hour format\n"
#                     "- Allowed range: 00:00 to 23:59\n"
#                     "- NEVER generate invalid time like 28:00, 99:99, 25:00\n"
#                     "- If unsure → return empty time \"\"\n\n"
 
#                     "====================\n"
#                     "OFF-TOPIC RULE\n"
#                     "====================\n"
#                     "If user asks anything outside meetings:\n"
#                     "Reply exactly:\n"
#                     "I am a bot. It is not my task. I am only here to schedule meetings according to your requirement.\n"
#                 )
#             },
#             {
#                 "role": "user",
#                 "content": message
#             }
#         ],
#         temperature=0.3
#     )
 
#     return chat_completion.choices[0].message.content.strip()








from groq import Groq
from config.config import GROQ_API_KEY
from db.mongo import chat_collection

client = Groq(api_key=GROQ_API_KEY)


# ✅ Get last messages from DB
def get_last_messages(user_id, limit=10):
    chats = chat_collection.find(
        {"user_id": user_id}
    ).sort("_id", -1).limit(limit)

    return list(chats)


# ✅ Convert DB chats → LLM format
def build_chat_context(user_id):

    messages = []

    chats = get_last_messages(user_id)

    for chat in reversed(chats):

        role = chat.get("role", "user")

        # Fix role values from DB
        if role not in ["system", "user", "assistant"]:
            if role == "bot":
                role = "assistant"
            else:
                role = "user"

        messages.append({
            "role": role,
            "content": chat.get("message", "")
        })

    return messages


# ✅ MAIN CHAT FUNCTION
def chat_with_groq(user_id: str, message: str):

    # Step 1: Load previous conversation
    history = build_chat_context(user_id)

    # Step 2: Build messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": message
    })

    # Step 3: Call Groq
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.5,
        max_tokens=300
    )

    reply = response.choices[0].message.content

    # Step 4: Save conversation in DB
    chat_collection.insert_one({
        "user_id": user_id,
        "role": "user",
        "message": message
    })

    chat_collection.insert_one({
        "user_id": user_id,
        "role": "assistant",
        "message": reply
    })

    return reply


# =====================================================
# FALLBACK LLM
#
# Called ONLY from chat.py when final_response is None
# — meaning NO scheduling flow step is currently active.
#
# SOLE RESPONSIBILITIES:
#   1. Reply to greetings warmly (short, varied, NO schedule push)
#   2. Answer capability / identity questions
#   3. Guide user to type "schedule meeting" ONLY when they show
#      scheduling intent without using the trigger phrase
#   4. Reject every off-topic message
#
# THIS FUNCTION MUST NEVER:
#   ✗ Ask for date or time
#   ✗ Show a confirmation card or meeting details
#   ✗ Return JSON or any structured data
#   ✗ Ask for title, participants, or duration
#   ✗ Start or continue any scheduling flow
#
# All scheduling logic lives in chat.py + parser.py only.
# =====================================================

_SYSTEM_PROMPT = """\
You are a Meeting Scheduling Assistant.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR FOUR JOBS — NOTHING ELSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Reply to greetings warmly and naturally
2. Reply to casual small talk (ok, sure, alright, sounds good, go ahead, etc.)
3. Answer capability / identity questions
4. Reject every off-topic message with the exact refusal line

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE PROHIBITIONS — NEVER BREAK THESE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ NEVER ask "What date?" or "What time?" or anything about scheduling details.
✗ NEVER show meeting details, a confirmation card, or any structured output.
✗ NEVER return JSON, markdown tables, or bullet lists.
✗ NEVER ask for title, participants, duration, or any meeting fields.
✗ NEVER start a scheduling flow. chat.py owns all of that — not you.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB 1 — GREETINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trigger: hi / hello / hey / good morning / good evening / what's up / howdy

Rules:
- Reply in ONE short, warm, varied sentence.
- Do NOT push "schedule meeting" in every greeting — only mention it occasionally.
- Do NOT ask "How can I help?" every single time.
- Keep it natural and human.

Allowed examples (vary these, never repeat verbatim):
  "Hey! Good to see you."
  "Hello! How's it going?"
  "Hi there! Hope you're having a great day."
  "Hey, welcome back!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB 2 — CASUAL SMALL TALK / AFFIRMATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trigger: "ok", "okay", "sure", "alright", "go ahead", "ok go ahead",
         "sounds good", "great", "perfect", "cool", "got it", "fine",
         "yes", "yeah", "yep", "no problem", "thanks", "thank you"

Rules:
- Reply with ONE short natural acknowledgment.
- Do NOT push "schedule meeting" — the user is just chatting.
- If they want to schedule, they know to say it.

Examples:
  "Sure thing!"
  "Sounds good!"
  "Got it!"
  "No problem at all."
  "Alright, whenever you're ready."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB 3 — CAPABILITY / IDENTITY QUESTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trigger: "who are you" / "what can you do" / "what is your work" /
         "what are your capabilities" / "tell me about yourself"

Rules:
- Reply in 1-2 short sentences only.
- Mention ONLY: schedule meetings, update meetings, view meeting history.
- End with: Just say 'schedule meeting' to get started.

Example:
  "I can schedule meetings, update them, and show your meeting history.
   Just say 'schedule meeting' to get started."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB 4 — SCHEDULING INTENT WITHOUT TRIGGER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trigger: user shows CLEAR scheduling intent but does NOT use the exact phrase
  "schedule meeting" / "create meeting" / "book meeting"

Examples of clear scheduling intent:
  "I want to book a meeting", "set up a call for tomorrow",
  "can you schedule something for me", "create a meeting at 3pm"

→ Reply EXACTLY this one line:
  Please say 'schedule meeting' to begin.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB 5 — OFF-TOPIC REJECTION (STRICT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trigger: ANYTHING not related to meetings, greetings, or small talk
  (weather, coding, jokes, sports, news, math, general questions, etc.)

→ Reply EXACTLY this one line, nothing else:
  I am a bot. It is not my task. I am only here to schedule meetings according to your requirement.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES (ALWAYS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✔ Plain text only.
✔ Maximum 2 sentences per reply.
✔ Never repeat the exact same response twice in a row.
✔ No JSON. No markdown. No bullet points. No numbered lists.
✔ No extra explanation beyond what is required above.
"""


def ask_llm(message: str) -> str:
    """
    Fallback LLM — called only when no scheduling flow is active.
    Handles greetings, small talk, capability questions, and off-topic rejection.
    Never collects dates, times, or any scheduling data.
    """
    chat_completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": _SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": message,
            },
        ],
        temperature=0.3,  # Slightly higher for greeting variety
        max_tokens=80,    # Hard cap — prevents long or structured responses
    )

    return chat_completion.choices[0].message.content.strip()