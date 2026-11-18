
import streamlit as st

from auth_client import signup


def render_signup():

    st.title("Create an account")
    st.caption("AI Task & Money Tracker")

    with st.form("signup_form"):

        user_id = st.text_input(
            "Username or email"
        ).strip()

        password = st.text_input(
            "Password",
            type="password"
        )

        confirm_password = st.text_input(
            "Confirm password",
            type="password"
        )

        submitted = st.form_submit_button(
            "Sign Up",
            use_container_width=True
        )

    if submitted:

        if not user_id or not password:
            st.error(
                "Please fill in all required fields."
            )

        elif password != confirm_password:
            st.error("Passwords do not match.")

        elif len(password) < 8:
            st.error(
                "Password must contain at least 8 characters."
            )

        else:
            try:
                signup(user_id, password)

                st.success(
                    "Account created successfully. Please log in."
                )

                st.session_state.auth_page = "login"

                st.rerun()

            except RuntimeError as exc:
                st.error(str(exc))
