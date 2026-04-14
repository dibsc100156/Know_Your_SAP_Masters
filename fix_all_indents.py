path = "C:/Users/vishnu/.openclaw/workspace/SAP_HANA_LLM_VendorChatbot/backend/app/agents/orchestrator.py"
with open(path, "r", encoding="utf-8-sig") as f:
    lines = f.readlines()

# All phase prints that have wrong indentation (4 spaces when should be 8)
wrong_indent_lines = [637, 674, 1007, 1117, 1195, 1242, 1283]

fixed = []
for i, line in enumerate(lines):
    if (i + 1) in wrong_indent_lines and line.startswith('    print'):
        # Fix: add 4 more spaces
        fixed_line = '        ' + line.lstrip()
        print(f"Fixed line {i+1}: {fixed_line.rstrip()[:80]}")
        fixed.append(fixed_line)
    else:
        fixed.append(line)

with open(path, "w", encoding="utf-8-sig") as f:
    f.writelines(fixed)

print(f"Fixed {len([l for l in fixed if l.startswith('        print') and '[1' in l or l.startswith('        print') and '[2' in l])} lines")
print("Done")
