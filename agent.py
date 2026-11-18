
import json
import os
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent


# Load environment variables from ai_application/.env
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env")

EXPENSE_TOOL_NAME = "get_expenses_by_period"

DELETE_TOOL_NAMES = {
    "find_expenses_for_deletion",
    "delete_expenses",
    "delete_expense",
}


def _parse_tool_payload(content):
    """Turn a ToolMessage content into the dict the MCP tool returned."""

    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return None

    elif isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)

        try:
            content = json.loads("\n".join(parts))
        except ValueError:
            return None

    return content if isinstance(content, dict) else None


def extract_expense_view(messages):
    """Extract the last paged expense result from one agent turn.

    Returns None when the turn did not retrieve expenses, or when the
    tool returned an error. The UI uses this to render the paginated
    table above the assistant's reply without parsing its prose.
    """

    calls = {}

    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") == EXPENSE_TOOL_NAME:
                calls[call.get("id")] = call.get("args") or {}

    for message in reversed(messages):
        call_id = getattr(message, "tool_call_id", None)

        if call_id not in calls:
            continue

        payload = _parse_tool_payload(getattr(message, "content", None))

        if not payload or "items" not in payload:
            return None

        args = calls[call_id]

        return {
            "start_date": args.get("start_date"),
            "end_date": args.get("end_date"),
            "page": payload.get(
                "page",
                args.get("page", 0) or 0
            ),
            "size": payload.get(
                "size",
                args.get("size", 10) or 10
            ),
            "data": payload,
        }

    return None



def is_delete_turn(messages):
    """True when the turn searches for or deletes expenses.

    Delete turns must not hide the assistant's text behind the
    expense table: the user needs to see and answer the question
    about which entries to remove.
    """

    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") in DELETE_TOOL_NAMES:
                return True

    return False


async def create_agent(access_token):

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing from .env"
        )

    if not access_token:
        raise ValueError(
            "JWT access token is missing."
        )

    # MCP server paths
    server_path = (
        PROJECT_ROOT / "mcp_server" / "server.py"
    )

    python_path = (
        PROJECT_ROOT / "mcp_server" / ".venv"
        / "Scripts" / "python.exe"
    )

    if not server_path.exists():
        raise FileNotFoundError(
            f"MCP server not found: {server_path}"
        )

    if not python_path.exists():
        raise FileNotFoundError(
            f"MCP Python interpreter not found: {python_path}"
        )

    # Connect to MCP server.
    # Pass the JWT through the process environment.
    mcp_client = MultiServerMCPClient({
        "expense_manager": {
            "transport": "stdio",
            "command": str(python_path),
            "args": [str(server_path)],
            "env": {
                **os.environ,
                "EXPENSE_ACCESS_TOKEN": access_token
            }
        }
    })

    # Discover MCP tools.
    tools = await mcp_client.get_tools()

    # Initialize Gemini.
    llm = ChatGoogleGenerativeAI(
        model=os.getenv(
            "GEMINI_MODEL",
            "gemini-3.5-flash-lite"
        ),
        google_api_key=api_key,
    )

    system_prompt = f"""
    You are an AI assistant for an expense management application.

    Today's date is {date.today().isoformat()}.

    Help users add expenses and retrieve their expenses
    using the available MCP tools.

    Rules:
    - Use MCP tools to perform expense operations.
    - Never claim an operation succeeded unless the tool confirms it.
    - Use today's date when the user explicitly says today.
    - Interpret relative dates using today's date.
    - Do not invent expense records or dates.
    - If the user does not specify an expense date, do not
      invent one. Let the backend apply its default date.
    - Report tool errors honestly.

    Retrieved expenses are ordered newest-added first, by the
    time each record was added (created_at, descending), not by
    the expense date.

    Retrieval is paginated:
    - The retrieval tool returns one page with items, page, size,
      totalItems, totalPages, hasNext and totalAmount (the amount
      sum for the whole period).
    - items is the only source of truth. Never invent rows.
    - The app renders the paged table and the whole-period total
      beside your reply, so keep your own answer to one short
      sentence and do not repeat the rows or totals in prose.
    - The table's Previous/Next buttons work on their own. Do not
      tell the user to ask you for the next page inside the table.
    - If the user asks you for the next page (for example
      "next"), call the tool again with the same dates and
      page + 1.
    - If hasNext is false, say there are no more records
      instead of paging further.
    - If the user asks for all expenses, page through until
      hasNext is false. Do not claim items is everything.

    Deleting expenses:
    - Before deleting, call find_expenses_for_deletion with the
      category and/or dates the user mentioned. Never delete an id
      that you have not just seen in a tool result.
    - If no expenses match, say so and delete nothing.
    - If the user mentioned a category, or more than one expense
      matches the request (requires_confirmation is true), do not
      delete anything yet. List the matching entries with their
      id, date, amount and category, then ask the user whether to
      delete all of them or only specific ids.
    - Delete only after the user's explicit confirmation, using
      delete_expenses with the exact ids from the search result.
      If they chose specific entries, delete only those ids.
    - If exactly one expense matches and the user did not mention
      a category, delete that id with delete_expenses.
    - Report the deleted ids and any failures from the tool.
    """

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
    )


async def run_agent(messages, access_token):
    """Execute the agent using the logged-in user's JWT."""

    agent = await create_agent(access_token)

    result = await agent.ainvoke({
        "messages": messages
    })

    # Only inspect messages produced by this turn. The agent receives
    # the whole conversation, so scanning all of it would re-attach an
    # earlier turn's expense table to every later reply.
    new_messages = result["messages"][len(messages):]

    expense_view = (
        None
        if is_delete_turn(new_messages)
        else extract_expense_view(new_messages)
    )

    return {
        "messages": result["messages"],
        "expense_view": expense_view,
    }
