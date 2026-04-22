# Phase 19 Operator Guide — Agent-as-Tool Dynamic Override

## Purpose
Phase 19 clamps agent autonomy when Sentinel or CIBA determine the request should not be allowed to fan out autonomously.

## What operators should expect
- **Normal path:** swarm / synthesis autonomy is allowed.
- **Tool mode:** sub-agents are treated like deterministic tools; autonomous synthesis is suppressed.
- **CIBA pending / denied:** request is blocked from autonomous progress until approval state changes.

## Trigger sources
1. **Safety Sentinel** returns `tighten` or `block`
2. **CIBA** has a pending request for the same session/query
3. Existing tool-mode session state is still active

## Runtime behavior
### `tighten`
- query may continue
- agent autonomy is clamped
- `tool_mode=true`
- synthesis falls back to `dedup_only`

### `block`
- if query already approved in CIBA: proceed in tool mode
- if denied in CIBA: hard reject
- if not yet reviewed: create CIBA request and return pending state

## Operator-facing API/debug fields
Sync chat responses surface:
- `tool_mode`
- `tool_mode_reason`
- `guardrails`
- `sentinel`

## Safe operating procedure
1. Check `tool_mode` and `tool_mode_reason`
2. If blocked, inspect the CIBA request
3. Approve only when the business need is valid and scope is acceptable
4. Re-run the query after approval; it should proceed in tool mode if still safety-constrained
5. If the same session repeatedly tightens/blocks, inspect `guardrails.profile`

## Failure modes to watch
- Repeated pending CIBA requests for the same workflow
- Tool mode staying active longer than expected for a session
- Dedup-only synthesis returning incomplete merged results for highly cross-domain asks

## Current implementation status
- Pre-swarm Sentinel/CIBA override: live
- Parallel dispatch tool-mode wrapper: live
- Dedup-only synthesis fallback: live
- API/debug surfacing: live
- Targeted tests: `backend/tests/test_phase19_agent_tool_mode.py`
