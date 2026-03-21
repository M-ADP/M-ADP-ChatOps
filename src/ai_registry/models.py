from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenAPIOperation:
    id: str
    source_file: Path
    operation_id: str
    path: str
    method: str
    summary: str
    required_headers: list[str]
    required_inputs: dict[str, Any]
