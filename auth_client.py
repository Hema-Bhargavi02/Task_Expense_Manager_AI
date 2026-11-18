
import os

import requests
from dotenv import load_dotenv

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

JAVA_API_URL = os.getenv(
    "JAVA_API_URL",
    "http://localhost:8080"
).rstrip("/")


def _post(endpoint, data):
    try:
        response = requests.post(
            f"{JAVA_API_URL}{endpoint}",
            json=data,
            timeout=10
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            "Could not connect to the Java backend."
        ) from exc

    if not response.ok:
        try:
            body = response.json()
            message = (
                body.get("message")
                or body.get("error")
                or "Request failed."
            )
        except ValueError:
            message = "Request failed."

        raise RuntimeError(message)

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            "The Java backend returned an invalid response."
        ) from exc


def signup(user_id, password):
    return _post(
        "/auth/register",
        {
            "userId": user_id,
            "password": password
        }
    )


def login(user_id, password):
    result = _post(
        "/auth/login",
        {
            "userId": user_id,
            "password": password
        }
    )

    token = result.get("token") or result.get("accessToken")

    if not token:
        raise RuntimeError(
            "Login succeeded without a JWT token. "
            "Check the Java login response."
        )

    return {
        "userId": result.get("userId", user_id),
        "token": token
    }
