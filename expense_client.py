import requests

# Reuse the backend URL and error parsing from auth_client so there is
# only one place that knows where Spring Boot lives.
from auth_client import JAVA_API_URL, _extract_error_message


def _iso_date(value):
    """Accept a date or an already-formatted YYYY-MM-DD string."""

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def fetch_expenses(
    start_date,
    end_date,
    access_token,
    page=0,
    size=10
):
    """Fetch one page of expenses for the logged-in user.

    start_date and end_date may be datetime.date objects or
    YYYY-MM-DD strings. The backend returns newest-added first
    along with the paging envelope and the whole-period total.
    """

    if not access_token:
        raise RuntimeError("Session expired. Please log in again.")

    try:
        response = requests.get(
            f"{JAVA_API_URL}/expense/period",
            params={
                "startDate": _iso_date(start_date),
                "endDate": _iso_date(end_date),
                "page": page,
                "size": size,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            "Could not connect to the Java backend. "
            "Make sure it is running."
        ) from exc

    if response.status_code == 401:
        raise RuntimeError("Session expired. Please log in again.")

    if not response.ok:
        raise RuntimeError(_extract_error_message(response))

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            "The Java backend returned an invalid response."
        ) from exc
