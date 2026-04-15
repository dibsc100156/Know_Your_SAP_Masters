"""Fix dispatch_single: insert properly-indented guard before assignment line"""
path = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\swarm\planner_agent.py'
content = open(path, encoding='utf-8-sig').read()

# Remove badly-indented guard inserted earlier
bad_frag = (
    '                if not decision.assignments:\n'
    '            return {\n'
    '                "error": "No domain agents assigned for this query.",\n'
    '                "supervisor": "planner_agent",\n'
    '                "decision": decision.routing.value if decision.routing else "unknown",\n'
    '                "reasoning": decision.reasoning,\n'
    '            }\n\n'
    'assignment = decision.assignments[0]'
)
content = content.replace(bad_frag, 'assignment = decision.assignments[0]')

# Now find the assignment line and insert the guard
idx = content.find('assignment = decision.assignments[0]')
if idx < 0:
    print('ERROR: assignment line not found')
else:
    guard = (
        '        if not decision.assignments:\n'
        '            return {\n'
        '                "error": "No domain agents assigned for this query.",\n'
        '                "supervisor": "planner_agent",\n'
        '                "decision": decision.routing.value if decision.routing else "unknown",\n'
        '                "reasoning": decision.reasoning,\n'
        '            }\n\n'
        '        assignment = decision.assignments[0]'
    )
    content = content[:idx] + guard + content[idx + len('assignment = decision.assignments[0]'):]
    open(path, 'w', encoding='utf-8').write(content)
    print('Written')

    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print('Syntax OK')
    except py_compile.PyCompileError as e:
        print(f'Syntax error: {e}')

    lines = content.split('\n')
    print('Verification:')
    for i in range(1262, 1285):
        print(f'{i+1}: {repr(lines[i])}')
