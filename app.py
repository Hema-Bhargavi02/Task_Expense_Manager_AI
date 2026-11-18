
import asyncio
from datetime import datetime

import streamlit as st

from agent import run_agent
from auth_session import (
    clear_session,
    flush_pending_cookies,
    is_expired,
    restore_session,
)
from expense_client import fetch_expenses
from login import render_login
from signup import render_signup


st.set_page_config(
    page_title="Expense AI Assistant",
    page_icon="💬",
    layout="centered",
)


def initialize_state():
    defaults = {
        "authenticated": False,
        "user_id": None,
        "access_token": None,
        "expires_at": None,
        "force_logged_out": False,
        "auth_page": "login",
        "chat_history": [],
        "agent_messages": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Apply any queued cookie write/delete from the previous run.
    flush_pending_cookies()

    # Restore the login from the cookie after a refresh or new tab.
    restore_session()


def get_text(content):
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
            else:
                parts.append(str(item))

        return "\n".join(parts)

    return str(content)


def logout():
    clear_session()
    st.session_state.auth_page = "login"

    st.rerun()


def format_added(value):
    """Render the backend's created_at timestamp in local time."""

    if not value:
        return ""

    try:
        return datetime.fromisoformat(value).astimezone().strftime(
            "%Y-%m-%d %H:%M"
        )
    except (TypeError, ValueError):
        return value


def format_amount(value):
    """Format an amount total with thousands separators."""

    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def change_expense_page(index, delta):
    """Button callback: move the page before the script reruns."""

    view = st.session_state.chat_history[index]["expense_view"]
    view["page"] = max(0, view["page"] + delta)


def render_expense_view(index, view):
    """Render the paged table and its Previous/Next buttons.

    The table is ordered by the backend: newest-added first.
    """

    access_token = st.session_state.access_token

    if not access_token:
        st.warning("Session expired. Please log in again.")
        return

    data = view.get("data") or {}

    # The callback bumps `page`, so exactly one fetch happens per click.
    if data.get("page") != view["page"]:

        try:
            data = fetch_expenses(
                view["start_date"],
                view["end_date"],
                access_token,
                page=view["page"],
                size=view["size"],
            )

            view["data"] = data

        except Exception as exc:
            message = str(exc)

            if "401" in message or "session" in message.lower():
                clear_session()
                st.warning("Session expired. Please log in again.")
                st.rerun()

            st.error(message)
            return

    items = data.get("items") or []
    page_number = data.get("page", view["page"])
    page_size = data.get("size", view["size"])
    total_items = data.get("totalItems", len(items))
    total_pages = data.get("totalPages", 0)

    st.caption(
        f"Expenses {view.get('start_date', '')} to "
        f"{view.get('end_date', '')}"
    )

    if items:

        first_row = page_number * page_size + 1
        last_row = first_row + len(items) - 1

        st.caption(
            f"Showing {first_row}\u2013{last_row} of {total_items} · "
            f"Page {page_number + 1} of {max(total_pages, 1)}"
        )

        st.dataframe(
            [
                {
                    "Added": format_added(item.get("createdAt")),
                    "Date": item.get("expenseDate", ""),
                    "Amount": item.get("amount"),
                    "Category": item.get("category", ""),
                    "Description": item.get("description") or "",
                    "ID": item.get("id"),
                }
                for item in items
            ],
            width="stretch",
            hide_index=True,
        )

    else:
        st.caption("No expenses in this period.")

    # The backend returns the whole-period total, so it stays the
    # same while the table pages through its rows.
    total_amount = data.get("totalAmount")

    if total_amount is None:
        total_amount = sum(
            float(item.get("amount") or 0)
            for item in items
        )
        total_label = "Total (this page)"
    else:
        total_label = "Total"

    st.caption(f"{total_label}: {format_amount(total_amount)}")

    previous_column, next_column = st.columns(2)

    previous_column.button(
        "Previous",
        key=f"expense_previous_{index}",
        disabled=not items or page_number <= 0,
        on_click=change_expense_page,
        args=(index, -1),
        width="stretch",
    )

    next_column.button(
        "Next",
        key=f"expense_next_{index}",
        disabled=not data.get("hasNext", False),
        on_click=change_expense_page,
        args=(index, 1),
        width="stretch",
    )


def render_message(index, message):

    with st.chat_message(message["role"]):

        # The paginated table sits above the assistant's text.
        if message.get("expense_view"):
            render_expense_view(index, message["expense_view"])

        if message.get("content"):
            st.markdown(message["content"])


def render_chat():

    st.title("💬 Expense AI Assistant")

    st.caption(
        f"Logged in as {st.session_state.user_id}"
    )

    if st.button("Logout"):
        logout()

    for index, message in enumerate(
            st.session_state.chat_history):
        render_message(index, message)

    user_input = st.chat_input(
        "Ask about your expenses..."
    )

    if user_input:

        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
        })

        render_message(
            len(st.session_state.chat_history) - 1,
            st.session_state.chat_history[-1],
        )

        with st.spinner("Thinking..."):

            try:
                if is_expired():
                    clear_session()
                    st.warning(
                        "Session expired. Please log in again."
                    )
                    st.rerun()

                access_token = (
                    st.session_state.access_token
                )

                if not access_token:
                    raise ValueError(
                        "Session expired. Please log in again."
                    )

                messages = [
                    *st.session_state.agent_messages,
                    {
                        "role": "user",
                        "content": user_input,
                    },
                ]

                # Pass the logged-in user's JWT.
                result = asyncio.run(
                    run_agent(
                        messages,
                        access_token
                    )
                )

                st.session_state.agent_messages = (
                    result["messages"]
                )

                expense_view = result.get("expense_view")

                # Retrieval turns display the backend table and total
                # only, so the model's prose is not shown.
                response = (
                    ""
                    if expense_view
                    else get_text(
                        result["messages"][-1].content
                    )
                )

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response,
                    "expense_view": expense_view,
                })

                render_message(
                    len(st.session_state.chat_history) - 1,
                    st.session_state.chat_history[-1],
                )

            except Exception as exc:
                message = str(exc)

                if "401" in message or "session" in message.lower():
                    clear_session()
                    st.warning(
                        "Session expired. Please log in again."
                    )
                    st.rerun()

                st.error(message)


initialize_state()

if st.session_state.authenticated:
    render_chat()

else:

    login_tab, signup_tab = st.tabs([
        "Login",
        "Sign Up",
    ])

    with login_tab:
        render_login()

    with signup_tab:
        render_signup()
