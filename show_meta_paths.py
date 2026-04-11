from app.core.sql_patterns.auto_meta_paths_v2 import AUTO_META_PATHS_V2

print("=== SAMPLE AUTO-GENERATED META-PATHS ===\n")
for p in AUTO_META_PATHS_V2[:20]:
    mp = p['module_pair']
    arrow = '>>>'
    tables_str = ' -> '.join(p['tables'])
    sql_preview = p['sql_template'][:100].replace('\n', ' ')
    print(f"  [{p['id']}] {mp} | Tables: {tables_str}")
    print(f"    SQL: {sql_preview}...")
    print()
print(f"  ... and {len(AUTO_META_PATHS_V2)-20} more paths.")

# Show cross-module highlights
print("\n=== KEY CROSS-MODULE PATHS ===")
cross = [p for p in AUTO_META_PATHS_V2 if p['module_pair'].split('-')[0] != p['module_pair'].split('-')[1]]
key_pairs = [
    ('MM-PUR', 'FI', 'P2P Full Cycle'),
    ('SD', 'FI', 'O2C Full Cycle'),
    ('MM', 'BP', 'Material-Vendor'),
    ('FI', 'CO', 'Cost Center'),
    ('QM', 'SD', 'Quality-Delivery'),
    ('HR', 'CO', 'Employee-Cost Center'),
]
for ma, mb, label in key_pairs:
    key = f"{ma}-{mb}"
    found = [p for p in cross if p['module_pair'] == key]
    if found:
        print(f"\n  [{label}] ({key})")
        print(f"    Path: {' -> '.join(found[0]['tables'])}")
