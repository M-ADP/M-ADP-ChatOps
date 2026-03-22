from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sonyflake import SonyFlake

from chatops.config import get_sonyflake_settings


class IdGenerator:
    _generator: SonyFlake | None = None

    @classmethod
    def _init_generator(cls) -> None:
        if cls._generator is not None:
            return

        machine_id = get_sonyflake_settings().machine_id
        cls._generator = SonyFlake(
            machine_id=lambda: machine_id,
            start_time=cls._kst_midnight_today(),
        )

    @staticmethod
    def _kst_midnight_today() -> datetime:
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        return datetime(
            year=now_kst.year,
            month=now_kst.month,
            day=now_kst.day,
            tzinfo=kst,
        )

    @classmethod
    def generate_sonyflake_id(cls) -> int:
        cls._init_generator()
        return cls._generator.next_id()
