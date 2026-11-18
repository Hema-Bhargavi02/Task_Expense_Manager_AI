
import streamlit as st

from auth_client import login
from auth_session import save_session


def render_login():

    st.title("Welcome back")
    st.caption("Log in to your Expense AI Assistant")

    with st.form("login_form"):

        user_id = st.text_input(
            "Username or email"
        ).strip()

        password = st.text_input(
            "Password",
            type="password"
        )

        submitted = st.form_submit_button(
            "Login",
            use_container_width=True
        )

    if submitted:

        if not user_id or not password:
            st.error(
                "Enter your username/email and password."
            )

        else:
            try:
                result = login(user_id, password)

                save_session(result["token"], result["userId"])

                st.session_state.auth_page = "login"

                st.rerun()

            except RuntimeError as exc:
                st.error(str(exc))
