# # chat_state = {}

# # def set_state(user_id, data):
# #     chat_state[user_id] = data

# # def get_state(user_id):
# #     return chat_state.get(user_id)

# # def clear_state(user_id):
# #     chat_state.pop(user_id, None)

# chat_state = {}

# def set_state(user_id, data):
#     chat_state[user_id] = data

# def get_state(user_id):
#     return chat_state.get(user_id)

# def clear_state(user_id):
#     chat_state.pop(user_id, None)









import time

chat_state = {}
STATE_TTL = 600  # 10 minutes of inactivity → auto-reset

def set_state(user_id, data):
    data = dict(data)
    data["_ts"] = time.time()
    chat_state[user_id] = data

def get_state(user_id):
    entry = chat_state.get(user_id)
    if not entry:
        return None
    if time.time() - entry.get("_ts", 0) > STATE_TTL:
        chat_state.pop(user_id, None)
        return None
    return entry

def clear_state(user_id):
    chat_state.pop(user_id, None)