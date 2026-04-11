f = open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\validate_memgraph.py', 'rb')
data = f.read()
f.close()

# Fix the doubled backslash issue in the last few lines
# The problematic lines have \\" instead of \"
data = data.replace(b'\\\\"')  # this won't work directly - do line by line

lines = data.split(b'\n')
print(f"Total lines: {len(lines)}")
for i, l in enumerate(lines[-10:], len(lines)-10):
    print(f"L{i}: {l}")

# Find and fix the broken lines
fixed = 0
for i in range(len(lines)):
    # Fix: \\" at end of a print string should be just \"
    # Pattern: print("       python -c \\"....; \\")
    if b'print("       python -c \\\\""' in lines[i] or b'\\"; \\\\")' in lines[i]:
        print(f"Found bad line {i+1}: {lines[i]}")
        # Replace the doubled backslash with single
        lines[i] = lines[i].replace(b'\\\\"; ', b'\\"; ')
        lines[i] = lines[i].replace(b'\\\\")', b'\\")')
        print(f"Fixed to: {lines[i]}")
        fixed += 1

if fixed:
    open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\validate_memgraph.py', 'wb').write(b'\n'.join(lines))
    print(f"Fixed {fixed} lines")
else:
    print("No lines to fix")
