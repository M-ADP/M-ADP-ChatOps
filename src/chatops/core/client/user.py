from __future__ import annotations

from typing import Protocol


class UserClient(Protocol):
    async def get_profile_by_nickname(self, *, nickname: str) -> dict[str, object]: ...
