from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RequestEventResponse(BaseModel):
    sequence: int
    type: str
    data: dict[str, Any]
    timestamp: datetime
