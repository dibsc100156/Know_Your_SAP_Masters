import re
from collections import OrderedDict

path = "C:/Users/vishnu/.openclaw/workspace/SAP_HANA_LLM_VendorChatbot/s3.en.vtt"
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    raw = f.read()

lines = raw.split('\n')
seen = OrderedDict()
for line in lines:
    if line.startswith('WEBVTT') or not line.strip():
        continue
    if '-->' in line:
        continue
    cleaned = re.sub(r'<[^>]+>', '', line)
    cleaned = ' '.join(cleaned.split()).strip()
    if cleaned and len(cleaned) > 2:
        if cleaned not in seen:
            seen[cleaned] = True

deduped = ' '.join(seen.keys())
print(f"Deduplicated: {len(deduped)} chars")
with open("C:/Users/vishnu/.openclaw/workspace/SAP_HANA_LLM_VendorChatbot/s3_clean.txt", 'w', encoding='utf-8') as f:
    f.write(deduped)
print(f"\n{deduped}")
