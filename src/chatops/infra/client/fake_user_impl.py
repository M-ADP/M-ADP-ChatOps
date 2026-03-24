from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chatops.common.id_generator import IdGenerator


@dataclass
class FakeUserClientImpl:
    users_by_nickname: dict[str, dict[str, Any]] = field(default_factory=dict)

    async def get_profile_by_nickname(self, *, nickname: str) -> dict[str, object]:
        normalized = str(nickname).strip()
        profile = self.users_by_nickname.get(normalized)
        if profile is None:
            profile = {
                "id": IdGenerator.generate_sonyflake_id(),
                "nickname": normalized,
                "github_id": normalized,
                "profile": "",
            }
            self.users_by_nickname[normalized] = profile
        return {
            "success": True,
            "summary": "user.get_profile_by_nickname",
            "data": profile,
            "status_code": 200,
        }
