import re, sys

vtt_path = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\s3.en.vtt'
with open(vtt_path, encoding='utf-8') as f:
    content = f.read()

# Remove VTT header and timestamps, extract text
lines = content.split('\n')
clean_lines = []
for line in lines:
    line = line.strip()
    # Skip WEBVTT header, blank lines, timestamp lines, cue identifiers
    if not line:
        continue
    if line.startswith('WEBVTT') or line.startswith('NOTE') or line.startswith('-->') or line.isdigit():
        continue
    # Remove HTML tags
    line = re.sub(r'<[^>]+>', '', line)
    line = re.sub(r'&amp;', '&', line)
    line = re.sub(r'&lt;', '<', line)
    line = re.sub(r'&gt;', '>', line)
    line = re.sub(r'&nbsp;', ' ', line)
    if line and line not in ('♪♪♪',):
        clean_lines.append(line)

# Dedupe consecutive identical lines
deduped = []
prev = None
for line in clean_lines:
    if line != prev:
        deduped.append(line)
        prev = line

full_text = ' '.join(deduped)
print(f"Total chars: {len(full_text)}")
print(f"Total words: {len(full_text.split())}")

# Save clean text
clean_path = vtt_path.replace('.vtt', '_clean.txt')
with open(clean_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(deduped))
print(f"Clean text saved to: {clean_path}")

# Print first 1000 chars for inspection
print("\n--- PREVIEW ---")
print(' '.join(deduped[:200]))
