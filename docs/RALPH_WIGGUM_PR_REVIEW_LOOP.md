# Ralph Wiggum PR Review Loop

## What was added
- `backend/app/core/pr_review_loop.py`
- `POST /api/v1/automation/pr-review-loop`

## Flow
1. self-review
2. specialist reviews (`quality`, `security`, `docs`)
3. iterate until stable or max rounds reached
4. return merge recommendation and auto-merge eligibility

## Output shape
- `status`: `approved` | `changes_requested`
- `blocking_count`
- `warning_count`
- `auto_merge_eligible`
- `history[]` with per-round review artifacts

## Current boundary
This is a deterministic local review harness. It does not create or merge live GitHub PRs yet.
