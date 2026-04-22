# Long-Running Agent Infrastructure

## What was added
- Durable job state store: `backend/app/core/long_running_jobs.py`
- New Celery queue: `longrun`
- New long-running task: `app.workers.orchestrator_tasks.run_orchestrator_long_task`
- Async control endpoints:
  - `GET /api/v1/chat/jobs`
  - `GET /api/v1/chat/jobs/{task_id}`
  - `POST /api/v1/chat/tasks/{task_id}/resume`
  - existing `DELETE /api/v1/chat/tasks/{task_id}` now also updates durable job state

## Capabilities
- queued / started / retry / success / timeout / cancelled durable status
- persisted submit payload for workflow-level resume
- user/session-scoped job history
- long-running submission path via `long_running=true`
- task lifecycle notifications emitted alongside job state updates

## Current boundary
This is workflow-level resume/retry/cancel infrastructure. It does **not** resume inside a partially executed orchestrator step yet; it resubmits from the stored task payload.
