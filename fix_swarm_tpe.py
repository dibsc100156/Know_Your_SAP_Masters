"""Fix dispatch_parallel: replace broken Celery dispatch with ThreadPoolExecutor"""
path = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\swarm\planner_agent.py'
content = open(path, encoding='utf-8-sig').read()

# The old Celery dispatch block (from "-- Celery dispatch" to "raw_results = ...")
old = '''        # -- Celery dispatch: each domain agent goes to its own queue ----------
        # Replaces ThreadPoolExecutor. Each task lands in a dedicated queue;
        # workers on that queue pick it up. No in-process threading.
        async_results = dispatch_domain_group(
            assignments=decision.assignments,
            query=decision.query,
            user_role=auth_context.role_id,
            run_id=run_id,
            plan_path=plan_path,
        )

        # -- Collect results (wait for all agents) ----------------------------
        # Per-domain task has 240s hard limit. Overall group timeout = 300s.
        raw_results = collect_group_results(async_results, decision.assignments, run_id=run_id, timeout=300.0)'''

new = '''        # -- ThreadPoolExecutor dispatch (reliable, cross-platform) ----------
        # On Windows + Celery solo pool, async result communication is broken.
        # Fall back to ThreadPoolExecutor for in-process parallel execution.
        # Swarm autoscaling via Celery workers remains available for Linux/production.
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_agent_task(assignment):
            """Run one domain agent in a thread."""
            agent = self._domain_agents.get(assignment.agent_name)
            if not agent:
                return {
                    "error": f"Unknown agent: {assignment.agent_name}",
                    "status": "agent_not_found",
                    "agent_name": assignment.agent_name,
                }
            try:
                result = agent.run(
                    query=decision.query,
                    auth_context=auth_context,
                    tables_hint=assignment.tables_hint,
                    run_id=run_id,
                    plan_path=plan_path,
                    verbose=False,
                )
                result["status"] = result.get("status", "success")
                result["agent_name"] = assignment.agent_name
                return result
            except Exception as e:
                logger.exception(f"[_run_agent_task] {assignment.agent_name} error: {e}")
                return {
                    "error": str(e),
                    "status": "error",
                    "agent_name": assignment.agent_name,
                }

        start = time.time()
        raw_results = []
        with ThreadPoolExecutor(max_workers=min(len(decision.assignments), max_workers)) as pool:
            futures = {
                pool.submit(_run_agent_task, assignment): assignment
                for assignment in decision.assignments
            }
            for future in as_completed(futures):
                raw_results.append(future.result())'''

count = content.count(old)
print(f'Fix: {count} occurrence(s)')
if count:
    content = content.replace(old, new, 1)
    print('Applied')
else:
    print('Pattern not found - checking with find...')
    idx = content.find('# -- Celery dispatch')
    if idx >= 0:
        print(f'Found at index {idx}')
    else:
        print('Not found at all')

# Also remove the domain_tasks import from dispatch_parallel if present
old_import = '        from app.workers.domain_tasks import dispatch_domain_group, collect_group_results\n\n'
if old_import in content:
    content = content.replace(old_import, '')
    print('Removed domain_tasks import from dispatch_parallel')
else:
    # Try without trailing newline
    old_import2 = '        from app.workers.domain_tasks import dispatch_domain_group, collect_group_results\n'
    if old_import2 in content:
        content = content.replace(old_import2, '')
        print('Removed domain_tasks import (no trailing newline)')
    else:
        print('domain_tasks import already removed or not found')

open(path, 'w', encoding='utf-8').write(content)
print('Written')

import py_compile
try:
    py_compile.compile(path, doraise=True)
    print('Syntax OK')
except py_compile.PyCompileError as e:
    print(f'Syntax error: {e}')
