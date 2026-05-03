from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram


sse_connections_active = Gauge(
    "sse_connections_active",
    "현재 활성 SSE 연결 수",
)

sse_connections_total = Counter(
    "sse_connections_total",
    "전체 SSE 연결 누적 수",
    labelnames=("outcome",),
)

sse_events_sent_total = Counter(
    "sse_events_sent_total",
    "SSE로 전송된 이벤트 누적 수",
)

sse_db_polls_total = Counter(
    "sse_db_polls_total",
    "SSE follow 모드의 DB 폴링 누적 횟수",
)

sse_connection_duration_seconds = Histogram(
    "sse_connection_duration_seconds",
    "SSE follow 연결 유지 시간 (초)",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)
