# # from fastapi import APIRouter, Request
# # from fastapi.responses import RedirectResponse
# # from auth.google_auth import get_auth_url, handle_callback

# # router = APIRouter()


# # # 🔹 LOGIN (NO user_id PARAM)
# # @router.get("/auth/login")
# # def login():
# #     auth_url = get_auth_url()
# #     return RedirectResponse(auth_url)


# # # 🔹 CALLBACK
# # @router.get("/auth/callback")
# # def callback(request: Request):

# #     full_url = str(request.url)
# #     state = request.query_params.get("state")

# #     result = handle_callback(full_url, state)

# #     # 👉 OPTIONAL: redirect to frontend with user_id
# #     if "user_id" in result:
# #         return RedirectResponse(
# #             f"http://localhost:8501/?user_id={result['user_id']}&email={result['email']}"
# #         )

# #     return result




# from fastapi import APIRouter, Request
# from fastapi.responses import RedirectResponse
# from auth.google_auth import get_auth_url, handle_callback

# router = APIRouter()


# @router.get("/auth/login")
# def login():
#     auth_url = get_auth_url()
#     return RedirectResponse(auth_url)


# @router.get("/auth/callback")
# def callback(request: Request):
#     full_url = str(request.url)
#     state = request.query_params.get("state")

#     result = handle_callback(full_url, state)

#     if "user_id" in result:
#         return RedirectResponse(
#             f"http://localhost:8501/?user_id={result['user_id']}&email={result['email']}"
#         )

#     return result







from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

from auth.google_auth import get_auth_url, handle_callback

router = APIRouter()


# =========================
# LOGIN
# =========================
@router.get("/auth/login")
def login():
    auth_url = get_auth_url()
    return RedirectResponse(auth_url)


# =========================
# CALLBACK (FIXED)
# =========================
# @router.get("/auth/callback")
# def callback(request: Request):

#     full_url = str(request.url)
#     state = request.query_params.get("state")

#     result = handle_callback(full_url, state)

#     # ❌ NO LOOP REDIRECT
#     if "error" in result:
#         return JSONResponse(result)

#     # ✅ OPTION 1 (RECOMMENDED FOR CLI / TESTING)
#     return JSONResponse(result)




@router.get("/auth/callback")
def callback(request: Request):

    full_url = str(request.url)
    state = request.query_params.get("state")

    result = handle_callback(full_url, state)

    return result   # ❌ NO redirect anymore