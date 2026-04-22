from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = os.environ.get("CELERY_RESULT_BACKEND") or f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:6379/0"
NOTIFICATION_TTL_SECONDS = 7 * 24 * 60 * 60
DEDUP_TTL_SECONDS = 5 * 60
MAX_NOTIFICATIONS_PER_INDEX = 200


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_key(kind: str, value: str) -> str:
    return f"agent_notify:index:{kind}:{value}"


@dataclass
class AgentNotification:
    notification_id: str
    title: str
    message: str
    category: str = "task"
    severity: str = "info"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    created_at: str = field(default_factory=_utc_now)
    status: str = "unread"
    read_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "title": self.title,
            "message": self.message,
            "category": self.category,
            "severity": self.severity,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "created_at": self.created_at,
            "status": self.status,
            "read_at": self.read_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentNotification":
        return cls(
            notification_id=data.get("notification_id", ""),
            title=data.get("title", ""),
            message=data.get("message", ""),
            category=data.get("category", "task"),
            severity=data.get("severity", "info"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            task_id=data.get("task_id"),
            created_at=data.get("created_at", _utc_now()),
            status=data.get("status", "unread"),
            read_at=data.get("read_at"),
            metadata=data.get("metadata", {}) or {},
        )


class AgentNotificationStore:
    def __init__(self, redis_url: str = DEFAULT_REDIS_URL):
        self.redis_url = redis_url
        self._client = None
        self._lock = Lock()
        self._memory: Dict[str, AgentNotification] = {}
        self._user_index: Dict[str, List[str]] = {}
        self._session_index: Dict[str, List[str]] = {}
        self._dedup: Dict[str, float] = {}
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
            logger.warning("[AgentNotifications] Redis unavailable — in-memory fallback: %s", e)
            self._client = None

    def _cleanup_memory_dedup(self):
        now = time.time()
        for key, expiry in list(self._dedup.items()):
            if expiry < now:
                del self._dedup[key]

    def _notification_key(self, notification_id: str) -> str:
        return f"agent_notify:item:{notification_id}"

    def create_notification(
        self,
        *,
        title: str,
        message: str,
        category: str = "task",
        severity: str = "info",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        dedup_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        metadata = metadata or {}
        notif_id = uuid.uuid4().hex
        dedup_scope = user_id or session_id or "global"
        dedup_token = f"{dedup_scope}:{dedup_key}" if dedup_key else None

        if self._client and dedup_token:
            try:
                dedup_cache_key = f"agent_notify:dedup:{dedup_token}"
                existing_id = self._client.get(dedup_cache_key)
                if existing_id:
                    existing = self.get_notification(existing_id)
                    if existing:
                        return existing
            except Exception as e:
                logger.debug("[AgentNotifications] Redis dedup read failed: %s", e)
        elif dedup_token:
            with self._lock:
                self._cleanup_memory_dedup()
                if dedup_token in self._dedup:
                    for existing in self.list_notifications(user_id=user_id, session_id=session_id, limit=50):
                        if existing.get("metadata", {}).get("dedup_key") == dedup_key:
                            return existing

        notification = AgentNotification(
            notification_id=notif_id,
            title=title,
            message=message,
            category=category,
            severity=severity,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            metadata={**metadata, **({"dedup_key": dedup_key} if dedup_key else {})},
        )
        data = notification.to_dict()
        score = time.time()

        if self._client:
            try:
                pipe = self._client.pipeline()
                pipe.setex(self._notification_key(notif_id), NOTIFICATION_TTL_SECONDS, json.dumps(data))
                if user_id:
                    user_key = _index_key("user", user_id)
                    pipe.zadd(user_key, {notif_id: score})
                    pipe.zremrangebyrank(user_key, 0, -(MAX_NOTIFICATIONS_PER_INDEX + 1))
                    pipe.expire(user_key, NOTIFICATION_TTL_SECONDS)
                if session_id:
                    session_key = _index_key("session", session_id)
                    pipe.zadd(session_key, {notif_id: score})
                    pipe.zremrangebyrank(session_key, 0, -(MAX_NOTIFICATIONS_PER_INDEX + 1))
                    pipe.expire(session_key, NOTIFICATION_TTL_SECONDS)
                if dedup_token:
                    pipe.setex(f"agent_notify:dedup:{dedup_token}", DEDUP_TTL_SECONDS, notif_id)
                pipe.execute()
                return data
            except Exception as e:
                logger.warning("[AgentNotifications] Redis write failed, using memory: %s", e)

        with self._lock:
            self._memory[notif_id] = notification
            if user_id:
                self._user_index.setdefault(user_id, []).insert(0, notif_id)
                self._user_index[user_id] = self._user_index[user_id][:MAX_NOTIFICATIONS_PER_INDEX]
            if session_id:
                self._session_index.setdefault(session_id, []).insert(0, notif_id)
                self._session_index[session_id] = self._session_index[session_id][:MAX_NOTIFICATIONS_PER_INDEX]
            if dedup_token:
                self._dedup[dedup_token] = time.time() + DEDUP_TTL_SECONDS
        return data

    def get_notification(self, notification_id: str) -> Optional[Dict[str, Any]]:
        if self._client:
            try:
                raw = self._client.get(self._notification_key(notification_id))
                return json.loads(raw) if raw else None
            except Exception as e:
                logger.debug("[AgentNotifications] Redis get failed: %s", e)
        with self._lock:
            notif = self._memory.get(notification_id)
            return notif.to_dict() if notif else None

    def list_notifications(
        self,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if self._client:
            try:
                if user_id:
                    ids = self._client.zrevrange(_index_key("user", user_id), 0, max(limit - 1, 0))
                elif session_id:
                    ids = self._client.zrevrange(_index_key("session", session_id), 0, max(limit - 1, 0))
                else:
                    ids = []
                notifications = []
                for notif_id in ids:
                    notif = self.get_notification(notif_id)
                    if notif and (not unread_only or notif.get("status") != "read"):
                        notifications.append(notif)
                return notifications
            except Exception as e:
                logger.warning("[AgentNotifications] Redis list failed, using memory: %s", e)

        with self._lock:
            if user_id:
                ids = list(self._user_index.get(user_id, []))
            elif session_id:
                ids = list(self._session_index.get(session_id, []))
            else:
                ids = list(self._memory.keys())
            notifications = []
            for notif_id in ids[:limit]:
                notif = self._memory.get(notif_id)
                if notif and (not unread_only or notif.status != "read"):
                    notifications.append(notif.to_dict())
            notifications.sort(key=lambda n: n.get("created_at", ""), reverse=True)
            return notifications[:limit]

    def get_summary(self, *, user_id: Optional[str] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
        notifications = self.list_notifications(user_id=user_id, session_id=session_id, limit=100)
        unread = [n for n in notifications if n.get("status") != "read"]
        return {
            "total": len(notifications),
            "unread": len(unread),
            "info": sum(1 for n in unread if n.get("severity") == "info"),
            "warning": sum(1 for n in unread if n.get("severity") == "warning"),
            "error": sum(1 for n in unread if n.get("severity") == "error"),
            "success": sum(1 for n in unread if n.get("severity") == "success"),
            "newest_at": notifications[0].get("created_at") if notifications else None,
        }

    def mark_read(self, notification_id: str) -> bool:
        notif = self.get_notification(notification_id)
        if not notif:
            return False
        notif["status"] = "read"
        notif["read_at"] = _utc_now()
        if self._client:
            try:
                self._client.setex(self._notification_key(notification_id), NOTIFICATION_TTL_SECONDS, json.dumps(notif))
                return True
            except Exception as e:
                logger.warning("[AgentNotifications] Redis mark_read failed: %s", e)
        with self._lock:
            self._memory[notification_id] = AgentNotification.from_dict(notif)
        return True

    def mark_all_read(self, *, user_id: Optional[str] = None, session_id: Optional[str] = None) -> int:
        notifications = self.list_notifications(user_id=user_id, session_id=session_id, unread_only=True, limit=200)
        count = 0
        for notif in notifications:
            if self.mark_read(notif["notification_id"]):
                count += 1
        return count


_store: Optional[AgentNotificationStore] = None


def get_notification_store() -> AgentNotificationStore:
    global _store
    if _store is None:
        _store = AgentNotificationStore()
    return _store
