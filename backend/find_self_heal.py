ORCH_PATH = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\orchestrator.py'

with open(ORCH_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"File size: {len(content)} chars, {content.count(chr(10))} lines")

# PART 2: Add formal_trace to result dict
marker = 'self_heal'
idx = content.find(marker)
print(f"First '{marker}' at: {idx}")
if idx >= 0:
    print(repr(content[idx-5:idx+100]))
print()

# Count occurrences
print(f"Occurrences of self_heal: {content.count('self_heal')}")

# Find all occurrences of self_heal
for i, ch in enumerate(content):
    if content[i:i+len(marker)] == marker:
        context = content[max(0,i-30):i+80].replace('\n', '\\n')
        print(f"  [{i}] {repr(context)}")
        if i > 30000:
            break