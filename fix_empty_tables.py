"""Fix IndexError on empty tables_involved in orchestrator.py"""
path = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\orchestrator.py'
content = open(path, encoding='utf-8-sig').read()

# Fix line 1449-1453: unguarded tables_involved[0] in else branch
old = '''        else:

            print("    [WARN] No pattern found. Generating SELECT * FROM primary table.")

            base_sql = f"SELECT * FROM {tables_involved[0]} "'''

new = '''        elif tables_involved:
            print("    [WARN] No pattern found. Generating SELECT * FROM primary table.")
            base_sql = f"SELECT * FROM {tables_involved[0]} "
        else:
            print("    [WARN] No tables found. Skipping SQL generation.")
            base_sql = ""'''

count = content.count(old)
print(f'Fix (line 1449-1453): {count} occurrence(s)')
if count:
    content = content.replace(old, new, 1)
    print('Applied')
else:
    # Try without trailing space
    old2 = '''        else:

            print("    [WARN] No pattern found. Generating SELECT * FROM primary table.")

            base_sql = f"SELECT * FROM {tables_involved[0]} "'''
    new2 = '''        elif tables_involved:
            print("    [WARN] No pattern found. Generating SELECT * FROM primary table.")
            base_sql = f"SELECT * FROM {tables_involved[0]} "
        else:
            print("    [WARN] No tables found. Skipping SQL generation.")
            base_sql = ""'''
    count2 = content.count(old2)
    print(f'Fix (old2): {count2} occurrence(s)')
    if count2:
        content = content.replace(old2, new2, 1)
        print('Applied (old2)')

open(path, 'w', encoding='utf-8').write(content)
print('Written')

# Verify
import py_compile
try:
    py_compile.compile(path, doraise=True)
    print('Syntax OK')
except py_compile.PyCompileError as e:
    print(f'Syntax error: {e}')
