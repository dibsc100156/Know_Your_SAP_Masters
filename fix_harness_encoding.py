import codecs

path = 'C:/Users/vishnu/.openclaw/workspace/SAP_HANA_LLM_VendorChatbot/docs/HARNESS_DESIGN_PRINCIPLES.md'

with open(path, 'rb') as f:
    raw = f.read()

# Fix common Unicode issues
clean = raw.replace(b'\xe2\x80\x94', b' -- ')   # em-dash
clean = clean.replace(b'\xe2\x80\x9c', b'"')      # left double quote
clean = clean.replace(b'\xe2\x80\x9d', b'"')      # right double quote
clean = clean.replace(b'\xe2\x80\x99', b"'")      # right single quote / apostrophe
clean = clean.replace(b'\xe2\x80\x93', b'-')      # en-dash

with open(path, 'wb') as f:
    f.write(clean)

# Verify
with codecs.open(path, 'r', encoding='utf-8-sig') as f:
    content = f.read()
print(f'OK: {len(content)} chars')
print(content[:300])
