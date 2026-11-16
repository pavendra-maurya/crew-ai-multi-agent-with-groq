import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional
from .schemas import JobDetailResponse, JobStatus


class JobStateManager:
    """Thread-safe store tracking job lifecycle and broadcasting live SSE events from sync CrewAI threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[str, JobDetailResponse] = {}
        self._events: Dict[str, List[str]] = {}

    def create_job(self, job_id: str) -> JobDetailResponse:
        with self._lock:
            job = JobDetailResponse(
                job_id=job_id,
                status=JobStatus.QUEUED,
                created_at=datetime.now(timezone.utc),
            )
            self._jobs[job_id] = job
            self._events[job_id] = []
            return job

    def publish_event(self, job_id: str, event_type: str, agent: str, message: str) -> None:
        payload = json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": event_type,
                "agent": agent,
                "message": message,
            }
        )
        with self._lock:
            if job_id in self._events:
                self._events[job_id].append(payload)

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        report=None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = status
            if report is not None:
                job.report = report
            if error is not None:
                job.error = error
            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                job.completed_at = datetime.now(timezone.utc)

    def get_job(self, job_id: str) -> Optional[JobDetailResponse]:
        with self._lock:
            return self._jobs.get(job_id)

    async def stream_events(self, job_id: str):
        cursor = 0
        while True:
            with self._lock:
                events = self._events.get(job_id, [])
                new_events = events[cursor:]
                cursor = len(events)
                job = self._jobs.get(job_id)

            for ev in new_events:
                yield f"data: {ev}\n\n"

            if job and job.status in (JobStatus.COMPLETED, JobStatus.FAILED) and not new_events:
                yield f"event: done\ndata: {json.dumps({'status': job.status})}\n\n"
                break

            await asyncio.sleep(0.4)


job_manager = JobStateManager()
