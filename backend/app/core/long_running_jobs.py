from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = os.environ.get("CELERY_RESULT_BACKEND") or f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:6379/0"
JOB_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_JOBS_PER_INDEX = 200


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_key(kind: str, value: str) -> str:
    return f"longrun:index:{kind}:{value}"


@dataclass
class LongRunningJob:
    task_id: str
    query: str
    user_role: str
    domain: str = "auto"
    urgency: str = "normal"
    status: str = "queued"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    queue_target: Optional[str] = None
    routing_tier: Optional[str] = None
    long_running: bool = False
    submitted_at: str = field(default_factory=_utc_now)
    started_at: Optional[str] = None
    heartbeat_at: Optional[str] = None
    completed_at: Optional[str] = None
    retries: int = 0
    cancel_requested: bool = False
    last_error: Optional[str] = None
    worker: Optional[str] = None
    answer_preview: Optional[str] = None
    result_summary: Dict[str, Any] = field(default_factory=dict)
    resume_count: int = 0
    resubmitted_from: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "query": self.query,
            "user_role": self.user_role,
            "domain": self.domain,
            "urgency": self.urgency,
            "status": self.status,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "queue_target": self.queue_target,
            "routing_tier": self.routing_tier,
            "long_running": self.long_running,
            "submitted_at": self.submitted_at,
            "started_at": self.started_at,
            "heartbeat_at": self.heartbeat_at,
            "completed_at": self.completed_at,
            "retries": self.retries,
            "cancel_requested": self.cancel_requested,
            "last_error": self.last_error,
            "worker": self.worker,
            "answer_preview": self.answer_preview,
            "result_summary": self.result_summary,
            "resume_count": self.resume_count,
            "resubmitted_from": self.resubmitted_from,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LongRunningJob":
        return cls(
            task_id=data.get("task_id", ""),
            query=data.get("query", ""),
            user_role=data.get("user_role", "AP_CLERK"),
            domain=data.get("domain", "auto"),
            urgency=data.get("urgency", "normal"),
            status=data.get("status", "queued"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            queue_target=data.get("queue_target"),
            routing_tier=data.get("routing_tier"),
            long_running=bool(data.get("long_running", False)),
            submitted_at=data.get("submitted_at", _utc_now()),
            started_at=data.get("started_at"),
            heartbeat_at=data.get("heartbeat_at"),
            completed_at=data.get("completed_at"),
            retries=int(data.get("retries", 0)),
            cancel_requested=bool(data.get("cancel_requested", False)),
            last_error=data.get("last_error"),
            worker=data.get("worker"),
            answer_preview=data.get("answer_preview"),
            result_summary=data.get("result_summary", {}) or {},
            resume_count=int(data.get("resume_count", 0)),
            resubmitted_from=data.get("resubmitted_from"),
            payload=data.get("payload", {}) or {},
        )


class LongRunningJobStore:
    def __init__(self, redis_url: str = DEFAULT_REDIS_URL):
        self.redis_url = redis_url
        self._client = None
        self._lock = Lock()
        self._memory: Dict[str, LongRunningJob] = {}
        self._user_index: Dict[str, List[str]] = {}
        self._session_index: Dict[str, List[str]] = {}
        self._connect()

    def _connect(self):
        try:
            import redis as redis_lib
            self._client = redis_lib.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._client.ping()
        except Exception as e:
            logger.warning("[LongRunningJobs] Redis unavailable — in-memory fallback: %s", e)
            self._client = None

    def _job_key(self, task_id: str) -> str:
        return f"longrun:job:{task_id}"

    def create_job(self, *, task_id: str, query: str, user_role: str, domain: str = "auto", urgency: str = "normal", user_id: Optional[str] = None, session_id: Optional[str] = None, queue_target: Optional[str] = None, routing_tier: Optional[str] = None, long_running: bool = False, payload: Optional[Dict[str, Any]] = None, resubmitted_from: Optional[str] = None) -> Dict[str, Any]:
        job = LongRunningJob(
            task_id=task_id,
            query=query,
            user_role=user_role,
            domain=domain,
            urgency=urgency,
            user_id=user_id,
            session_id=session_id,
            queue_target=queue_target,
            routing_tier=routing_tier,
            long_running=long_running,
            status="queued",
            payload=payload or {},
            resubmitted_from=resubmitted_from,
        )
        if resubmitted_from:
            prior = self.get_job(resubmitted_from)
            job.resume_count = int(prior.get("resume_count", 0)) + 1 if prior else 1
        return self._save(job)

    def _save(self, job: LongRunningJob) -> Dict[str, Any]:
        data = job.to_dict()
        score = time.time()
        if self._client:
            try:
                pipe = self._client.pipeline()
                pipe.setex(self._job_key(job.task_id), JOB_TTL_SECONDS, json.dumps(data))
                if job.user_id:
                    user_key = _index_key("user", job.user_id)
                    pipe.zadd(user_key, {job.task_id: score})
                    pipe.zremrangebyrank(user_key, 0, -(MAX_JOBS_PER_INDEX + 1))
                    pipe.expire(user_key, JOB_TTL_SECONDS)
                if job.session_id:
                    session_key = _index_key("session", job.session_id)
                    pipe.zadd(session_key, {job.task_id: score})
                    pipe.zremrangebyrank(session_key, 0, -(MAX_JOBS_PER_INDEX + 1))
                    pipe.expire(session_key, JOB_TTL_SECONDS)
                pipe.execute()
                return data
            except Exception as e:
                logger.warning("[LongRunningJobs] Redis write failed, using memory: %s", e)

        with self._lock:
            self._memory[job.task_id] = job
            if job.user_id:
                self._user_index.setdefault(job.user_id, []).insert(0, job.task_id)
                self._user_index[job.user_id] = self._user_index[job.user_id][:MAX_JOBS_PER_INDEX]
            if job.session_id:
                self._session_index.setdefault(job.session_id, []).insert(0, job.task_id)
                self._session_index[job.session_id] = self._session_index[job.session_id][:MAX_JOBS_PER_INDEX]
        return data

    def get_job(self, task_id: str) -> Optional[Dict[str, Any]]:
        if self._client:
            try:
                raw = self._client.get(self._job_key(task_id))
                return json.loads(raw) if raw else None
            except Exception as e:
                logger.debug("[LongRunningJobs] Redis get failed: %s", e)
        with self._lock:
            job = self._memory.get(task_id)
            return job.to_dict() if job else None

    def update_job(self, task_id: str, **updates) -> Optional[Dict[str, Any]]:
        current = self.get_job(task_id)
        if not current:
            return None
        merged = LongRunningJob.from_dict({**current, **updates})
        return self._save(merged)

    def mark_started(self, task_id: str, worker: Optional[str] = None) -> Optional[Dict[str, Any]]:
        now = _utc_now()
        return self.update_job(task_id, status="started", started_at=current_or_default(self.get_job(task_id), "started_at", now), heartbeat_at=now, worker=worker)

    def heartbeat(self, task_id: str, **updates) -> Optional[Dict[str, Any]]:
        return self.update_job(task_id, heartbeat_at=_utc_now(), **updates)

    def mark_retry(self, task_id: str, retries: int, error: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.update_job(task_id, status="retry", retries=retries, heartbeat_at=_utc_now(), last_error=error)

    def mark_completed(self, task_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.update_job(
            task_id,
            status=result.get("status", "success"),
            heartbeat_at=_utc_now(),
            completed_at=_utc_now(),
            answer_preview=(result.get("answer") or "")[:200],
            result_summary={
                "tables_used": result.get("tables_used", [])[:10],
                "routing_tier": result.get("routing_tier"),
                "confidence": result.get("confidence_score"),
                "execution_time_ms": result.get("execution_time_ms"),
            },
        )

    def mark_failed(self, task_id: str, error: str, status: str = "error") -> Optional[Dict[str, Any]]:
        return self.update_job(task_id, status=status, heartbeat_at=_utc_now(), completed_at=_utc_now(), last_error=error)

    def request_cancel(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.update_job(task_id, cancel_requested=True, status="cancel_requested", heartbeat_at=_utc_now())

    def mark_cancelled(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.update_job(task_id, cancel_requested=True, status="cancelled", completed_at=_utc_now(), heartbeat_at=_utc_now())

    def list_jobs(self, *, user_id: Optional[str] = None, session_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if self._client:
            try:
                if user_id:
                    ids = self._client.zrevrange(_index_key("user", user_id), 0, max(limit - 1, 0))
                elif session_id:
                    ids = self._client.zrevrange(_index_key("session", session_id), 0, max(limit - 1, 0))
                else:
                    ids = []
                jobs = [self.get_job(task_id) for task_id in ids]
                return [j for j in jobs if j]
            except Exception as e:
                logger.warning("[LongRunningJobs] Redis list failed, using memory: %s", e)

        with self._lock:
            if user_id:
                ids = self._user_index.get(user_id, [])
            elif session_id:
                ids = self._session_index.get(session_id, [])
            else:
                ids = list(self._memory.keys())
            jobs = [self._memory[task_id].to_dict() for task_id in ids[:limit] if task_id in self._memory]
            jobs.sort(key=lambda j: j.get("submitted_at", ""), reverse=True)
            return jobs[:limit]


def current_or_default(data: Optional[Dict[str, Any]], key: str, default: Any) -> Any:
    if not data:
        return default
    return data.get(key) or default


_store: Optional[LongRunningJobStore] = None


def get_long_running_job_store() -> LongRunningJobStore:
    global _store
    if _store is None:
        _store = LongRunningJobStore()
    return _store
