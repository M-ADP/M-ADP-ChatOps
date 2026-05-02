"""LangGraph checkpoint retention cron.

sessions 테이블 기준으로 N일이 지난 세션의 checkpoint를 삭제한다.
thread_id = 'sess_{session_id}' 형식으로 매핑한다.

사용법:
    python scripts/cleanup_checkpoints.py --days 30
    python scripts/cleanup_checkpoints.py --days 30 --dry-run

환경 변수:
    DATABASE_URL: PostgreSQL 연결 문자열 (postgresql://... 형식)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30, help="N일 이상 된 세션의 checkpoint 삭제 (기본: 30)")
    parser.add_argument("--dry-run", action="store_true", help="삭제 없이 대상 수만 출력")
    parser.add_argument("--batch-size", type=int, default=500, help="한 번에 처리할 세션 수 (기본: 500)")
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
                "SELECT id FROM sessions WHERE created_at < NOW() - INTERVAL '%s days'",
                (args.days,),
            )
            old_session_ids = [row[0] for row in cur.fetchall()]

        if not old_session_ids:
            logger.info("삭제 대상 세션 없음 (기준: %d일 이전)", args.days)
            return 0

        thread_ids = [f"sess_{sid}" for sid in old_session_ids]
        logger.info("삭제 대상 세션: %d개", len(thread_ids))

        total_deleted = 0
        for i in range(0, len(thread_ids), args.batch_size):
            batch = thread_ids[i : i + args.batch_size]
            with conn.cursor() as cur:
                if args.dry_run:
                    cur.execute(
                        "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ANY(%s)",
                        (batch,),
                    )
                    count = cur.fetchone()[0]
                    logger.info("[dry-run] batch %d: checkpoint %d개 삭제 예정", i // args.batch_size + 1, count)
                    total_deleted += count
                else:
                    cur.execute(
                        "DELETE FROM checkpoint_writes WHERE thread_id = ANY(%s)",
                        (batch,),
                    )
                    cur.execute(
                        "DELETE FROM checkpoints WHERE thread_id = ANY(%s)",
                        (batch,),
                    )
                    conn.commit()
                    logger.info("batch %d: %d개 세션 checkpoint 삭제 완료", i // args.batch_size + 1, len(batch))
                    total_deleted += len(batch)

        if args.dry_run:
            logger.info("[dry-run] 총 %d개 checkpoint 행 삭제 예정", total_deleted)
        else:
            logger.info("총 %d개 세션 checkpoint 삭제 완료", total_deleted)

    return 0


if __name__ == "__main__":
    sys.exit(main())
