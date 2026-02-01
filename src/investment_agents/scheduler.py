"""Scheduler for daily updates and recurring tasks."""

import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class DailyUpdateScheduler:
    def __init__(self, timezone: str = "America/New_York") -> None:
        self.scheduler = AsyncIOScheduler(timezone=timezone)
        self.timezone = timezone

    def add_daily_update(
        self,
        callback: Callable[[], Coroutine[Any, Any, None]],
        hour: int = 9,
        minute: int = 0,
        job_id: str | None = None,
    ) -> str:
        trigger = CronTrigger(hour=hour, minute=minute, timezone=self.timezone)
        job = self.scheduler.add_job(
            self._run_async_callback,
            trigger=trigger,
            args=[callback],
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled daily update at {hour:02d}:{minute:02d} {self.timezone}")
        return job.id

    def add_interval_update(
        self,
        callback: Callable[[], Coroutine[Any, Any, None]],
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        job_id: str | None = None,
    ) -> str:
        job = self.scheduler.add_job(
            self._run_async_callback,
            trigger="interval",
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            args=[callback],
            id=job_id,
            replace_existing=True,
        )
        return job.id

    async def _run_async_callback(
        self,
        callback: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        try:
            await callback()
        except Exception as e:
            logger.error(f"Error in scheduled callback: {e}", exc_info=True)

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time,
                "trigger": str(job.trigger),
            })
        return jobs
