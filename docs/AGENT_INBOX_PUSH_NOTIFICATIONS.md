# Agent Inbox + Push Notifications

## What was added
- User/session-scoped notification store: `backend/app/core/agent_notifications.py`
- Async chat endpoints:
  - `GET /api/v1/chat/notifications`
  - `GET /api/v1/chat/notifications/summary`
  - `POST /api/v1/chat/notifications/{notification_id}/read`
  - `POST /api/v1/chat/notifications/read-all`

## Triggered events
- task queued
- task started
- task completed
- task failed
- task retrying
- task cancelled
- task resumed

## Delivery model
- Notifications are stored per `user_id` and optional `session_id`
- Redis-backed with in-memory fallback
- Lightweight dedup suppresses rapid duplicate events for the same task transition
- Frontends can poll summary endpoints for unread badges and fetch full items on demand

## Noise controls
- dedup keys on task lifecycle transitions
- user/session scoping
- read / read-all acknowledgement endpoints
