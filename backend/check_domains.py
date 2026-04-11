import sys, os
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')
domain_dir = r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\domain'
for f in sorted(os.listdir(domain_dir)):
    if f.endswith('_schema.py'):
        mod_name = f[:-3]
        try:
            mod = __import__(f'app.domain.{mod_name}', fromlist=['X'])
            tables = [x for x in dir(mod) if 'TABLE' in x]
            patterns = [x for x in dir(mod) if 'PATTERN' in x]
            t_var = tables[0] if tables else 'MISSING'
            p_var = patterns[0] if patterns else 'MISSING'
            print(f'{mod_name}: TABLES={t_var}, PATTERNS={p_var}')
        except Exception as e:
            print(f'{mod_name}: ERROR {e}')
