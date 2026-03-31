"""TypedDict для ответов API hh.ru"""

from typing import TypedDict


class AccessToken(TypedDict):
    """Токен доступа OAuth."""

    access_token: str | None
    refresh_token: str | None
    access_expires_at: int
