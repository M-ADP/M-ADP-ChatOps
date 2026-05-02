"""Bedrock Titan 임베딩 기반 operation 시맨틱 라우터.

Bedrock 미설정 시 from_registry()가 None을 반환하며, 호출자는 keyword fallback으로 전환한다.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chatops.services.registry import RegistryEntry

logger = logging.getLogger(__name__)

_MODEL_ID = "amazon.titan-embed-text-v2:0"
_EMBED_DIMENSIONS = 512
_MAX_INPUT_CHARS = 8000


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _similarity_to_bonus(sim: float) -> int:
    if sim >= 0.90:
        return 20
    if sim >= 0.80:
        return 15
    if sim >= 0.70:
        return 10
    if sim >= 0.60:
        return 5
    return 0


def _anchor_text(entry: Any) -> str:
    """capability × 3 + when_to_use + examples → 임베딩용 앵커 텍스트."""
    capability_x3 = " ".join([entry.capability] * 3)
    when_to_use = " ".join(entry.when_to_use)
    examples = " ".join(entry.examples)
    return f"{capability_x3} {when_to_use} {examples}"


class SemanticRouter:
    """Operation 앵커 임베딩을 보유하고, 쿼리 벡터와의 코사인 유사도를 점수로 변환한다."""

    def __init__(self, client: Any, anchors: dict[str, list[float]]) -> None:
        self._client = client
        self._anchors = anchors

    def embed_text(self, text: str) -> list[float] | None:
        try:
            response = self._client.invoke_model(
                modelId=_MODEL_ID,
                body=json.dumps({
                    "inputText": text[:_MAX_INPUT_CHARS],
                    "dimensions": _EMBED_DIMENSIONS,
                    "normalize": True,
                }),
                contentType="application/json",
                accept="application/json",
            )
            return json.loads(response["body"].read())["embedding"]
        except Exception as exc:
            logger.warning("SemanticRouter embed_text failed: %s", exc)
            return None

    def score_bonus(self, user_vec: list[float], operation_id: str) -> int:
        """user_vec와 operation 앵커의 코사인 유사도를 0–20 정수 점수로 반환한다.

        normalize=True로 임베딩했으므로 dot product = cosine similarity.
        """
        anchor = self._anchors.get(operation_id)
        if anchor is None:
            return 0
        return _similarity_to_bonus(_dot(user_vec, anchor))

    @classmethod
    def from_registry(
        cls,
        entries: list[Any],
        region: str | None = None,
    ) -> "SemanticRouter | None":
        """Registry 엔트리 앵커를 임베딩해 SemanticRouter를 생성한다.

        Bedrock 접근 불가 시 None을 반환하며 호출자가 keyword fallback을 사용한다.
        """
        if not entries:
            return None

        try:
            import boto3  # type: ignore[import]
            client = boto3.client("bedrock-runtime", region_name=region or "us-east-1")
        except Exception as exc:
            logger.info("SemanticRouter unavailable (boto3 import/client): %s", exc)
            return None

        # 연결 가능 여부를 첫 번째 엔트리로 probe (최대 3회 재시도)
        probe = cls(client=client, anchors={})
        _MAX_PROBE_RETRIES = 3
        probe_vec: list[float] | None = None
        for attempt in range(_MAX_PROBE_RETRIES):
            probe_vec = probe.embed_text(_anchor_text(entries[0]))
            if probe_vec is not None:
                break
            if attempt < _MAX_PROBE_RETRIES - 1:
                logger.warning(
                    "SemanticRouter probe attempt %d/%d failed, retrying...",
                    attempt + 1, _MAX_PROBE_RETRIES,
                )
        if probe_vec is None:
            logger.warning(
                "SemanticRouter: %d probe 시도 모두 실패, keyword fallback 사용",
                _MAX_PROBE_RETRIES,
            )
            return None

        anchors: dict[str, list[float]] = {entries[0].id: probe_vec}
        failed_ids: list[str] = []
        for entry in entries[1:]:
            vec = probe.embed_text(_anchor_text(entry))
            if vec is not None:
                anchors[entry.id] = vec
            else:
                failed_ids.append(entry.id)

        if failed_ids:
            logger.warning(
                "SemanticRouter: %d개 entry 임베딩 실패 (무시하고 계속): %s",
                len(failed_ids), failed_ids,
            )
        logger.info(
            "SemanticRouter: %d/%d operation 앵커 임베딩 완료",
            len(anchors),
            len(entries),
        )
        return cls(client=client, anchors=anchors)
