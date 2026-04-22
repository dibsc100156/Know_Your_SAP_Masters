# Doc-Gardening Agent

## What was added
- `backend/app/core/doc_gardening_agent.py`
- `GET /api/v1/automation/doc-gardening`

## Current checks
- broken markdown/code file references
- TODO/TBD placeholders in docs
- lightly-scored orphan doc detection

## Output
- `status`
- `doc_count`
- `issue_count`
- `issues[]` with `severity`, `issue_type`, `confidence`, and `risk`

## Current boundary
This is a scanner/proposal surface. It does not auto-edit docs or open PRs yet.
