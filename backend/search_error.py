import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

# Search all Python files in app/
root = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app'
found = []
for dirpath, dirnames, filenames in os.walk(root):
    for fname in filenames:
        if fname.endswith('.py'):
            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, encoding='utf-8-sig') as f:
                    text = f.read()
                for m in re.finditer(r'no such group', text, re.IGNORECASE):
                    rel = os.path.relpath(fpath, root)
                    start = max(0, m.start()-120)
                    end = min(len(text), m.end()+120)
                    snippet = text[start:end]
                    print(f'FILE: {rel}')
                    print(f'  MATCH: ...{snippet}...')
                    print()
            except Exception as e:
                print(f'Error reading {fpath}: {e}')

print('Search complete.')