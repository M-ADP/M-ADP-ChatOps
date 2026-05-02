"""만료된 interrupted/pending_approval 요청을 approval_expired로 일괄 업데이트.

DB에 영구 잔존하는 만료 요청을 정리한다.
TTL은 chatops 앱 설정(approval_ttl_seconds)과 동일한 값을 사용한다.

사용법:
    python scripts/sweep_expired_requests.py
    python scripts/sweep_expired_requests.py --ttl-seconds 900 --dry-run

cron 예시 (5분마다):
    */5 * * * * cd /app && python scripts/sweep_expired_requests.py >> /var/log/sweep.log 2>&1

환경 변수:
    DATABASE_URL: PostgreSQL 연결 문자열
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 900
_STALE_STATUSES = ("pending_approval", "interrupted")
_TARGET_STATUS = "approval_expired"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=int(os.environ.get("APPROVAL_TTL_SECONDS", _DEFAULT_TTL_SECONDS)),
        help=f"승인 TTL(초). 이 시간이 지난 요청을 만료 처리 (기본: {_DEFAULT_TTL_SECONDS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="업데이트 없이 대상 수만 출력")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        logger.error("DATABASE_URL이 PostgreSQL이 아닙니다: %s", db_url[:30] or "(미설정)")
        return 1

    try:
        import psycopg  # type: ignore[import]
    except ImportError:
        logger.error("psycopg 패키지가 필요합니다: pip install psycopg")
        return 1

    conn_str = db_url.replace("+psycopg", "").replace("+asyncpg", "")

    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, created_at
                FROM requests
                WHERE status = ANY(%s)
                  AND created_at < NOW() - INTERVAL '%s seconds'
                """,
                (list(_STALE_STATUSES), args.ttl_seconds),
            )
            rows = cur.fetchall()

        if not rows:
            logger.info("만료된 요청 없음 (TTL: %d초)", args.ttl_seconds)
            return 0

        expired_ids = [row[0] for row in rows]
        logger.info("만료 대상: %d개 요청 (TTL: %d초)", len(expired_ids), args.ttl_seconds)

        if args.dry_run:
            for rid, st, created in rows[:10]:
                logger.info("[dry-run] request_id=%s status=%s created_at=%s", rid, st, created)
            if len(rows) > 10:
                logger.info("[dry-run] ... 외 %d개", len(rows) - 10)
            return 0

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE requests SET status = %s, updated_at = NOW() WHERE id = ANY(%s)",
                (_TARGET_STATUS, expired_ids),
            )
            conn.commit()

        logger.info("%d개 요청을 %s로 업데이트 완료", len(expired_ids), _TARGET_STATUS)

    return 0


if __name__ == "__main__":
    sys.exit(main())
