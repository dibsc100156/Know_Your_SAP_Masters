data = open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\validate_memgraph.py', 'rb').read()
lines = data.split(b'\n')
for i, line in enumerate(lines):
    if b'\\"; \\' in line:
        lines[i] = line.replace(b'\\"; \\', b'\\"; ')
        print(f'Fixed line {i+1}: {line}')
        break
open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\validate_memgraph.py', 'wb').write(b'\n'.join(lines))
print('Done')
