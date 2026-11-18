import time
from datetime import datetime

import extra_streamlit_components as stx
import jwt
import streamlit as st

COOKIE_NAME = "expense_jwt"


@st.cache_resource
def cookie_manager():
    return stx.CookieManager(key="auth_cookie_manager")


def _decode(token):
    # UX-only decode. The backend still verifies the signature and expiry.
    return jwt.decode(token, options={"verify_signature": False})


def token_expires_at(token):
    return int(_decode(token)["exp"])


def is_expired():
    expires_at = st.session_state.get("expires_at")
    return not expires_at or expires_at <= time.time()


def flush_pending_cookies():
    """Render the cookie component to apply a queued write/delete.

    The CookieManager writes cookies from the browser after a component
    render, so the change is applied on the run after save/clear.
    """

    token = st.session_state.pop("pending_cookie", None)

    if token:
        try:
            exp = token_expires_at(token)
            cookie_manager().set(
                COOKIE_NAME,
                token,
                expires_at=datetime.fromtimestamp(exp),
                path="/",
                same_site="lax",
                # secure=True once the app is served over HTTPS.
            )
        except Exception:
            pass

    if st.session_state.pop("pending_delete", False):
        try:
            cookie_manager().delete(COOKIE_NAME)
        except Exception:
            pass


def save_session(token, user_id):
    """Persist the JWT in session state and queue it for the cookie."""

    exp = token_expires_at(token)

    st.session_state.access_token = token
    st.session_state.user_id = user_id
    st.session_state.expires_at = exp
    st.session_state.authenticated = True
    st.session_state.force_logged_out = False
    st.session_state.chat_history = []
    st.session_state.agent_messages = []

    st.session_state.pending_cookie = token


def restore_session():
    """Restore the login from the cookie after a refresh/new tab."""

    if st.session_state.get("force_logged_out"):
        return

    if st.session_state.get("access_token"):
        return

    token = (st.context.cookies or {}).get(COOKIE_NAME)
    if not token:
        return

    try:
        claims = _decode(token)
    except jwt.PyJWTError:
        clear_session()
        return

    if int(claims["exp"]) <= time.time():
        clear_session()
        return

    st.session_state.access_token = token
    st.session_state.expires_at = int(claims["exp"])
    st.session_state.user_id = claims.get("sub")
    st.session_state.authenticated = True


def clear_session():
    """Clear session state and queue the auth cookie for deletion."""

    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.access_token = None
    st.session_state.expires_at = None
    st.session_state.chat_history = []
    st.session_state.agent_messages = []

    # Do not let restore_session() revive the just-cleared cookie.
    st.session_state.force_logged_out = True
    st.session_state.pending_delete = True
