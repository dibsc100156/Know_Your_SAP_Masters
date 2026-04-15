"""Fix dispatch_parallel: replace broken Celery dispatch with ThreadPoolExecutor"""
path = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\swarm\planner_agent.py'
content = open(path, encoding='utf-8-sig').read()

idx = content.find('# -- Celery dispatch')
if idx < 0:
    print('ERROR: marker not found')
else:
    end_idx = content.find('# -- Collect results', idx)
    if end_idx < 0:
        print('ERROR: end marker not found')
    else:
        end_idx = end_idx  # start of "# -- Collect results"
        old_block = content[idx:end_idx]
        print(f'Found block: {len(old_block)} chars')
        print('---')
        print(repr(old_block[:300]))
        print('---')

        new_block = '''        # -- ThreadPoolExecutor dispatch (reliable, cross-platform) ----------
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
                raw_results.append(future.result())

'''

        content = content[:idx] + new_block + content[end_idx:]
        print('Replaced')

        # Also remove the domain_tasks import from dispatch_parallel
        import_line = '        from app.workers.domain_tasks import dispatch_domain_group, collect_group_results\n\n'
        if import_line in content:
            content = content.replace(import_line, '')
            print('Removed domain_tasks import')
        else:
            import_line2 = '        from app.workers.domain_tasks import dispatch_domain_group, collect_group_results\n'
            if import_line2 in content:
                content = content.replace(import_line2, '')
                print('Removed domain_tasks import (no trailing blank)')

        open(path, 'w', encoding='utf-8').write(content)
        print('Written')

        import py_compile
        try:
            py_compile.compile(path, doraise=True)
            print('Syntax OK')
        except py_compile.PyCompileError as e:
            print(f'Syntax error: {e}')
