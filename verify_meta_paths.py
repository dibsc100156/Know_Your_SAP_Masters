from app.core.meta_path_library import meta_path_library

stats = meta_path_library.stats()
print(f"Total meta-paths: {stats['total_meta_paths']}")
print(f"Total variants: {stats['total_variants']}")
print(f"Tables indexed: {stats['tables_indexed']}")

# Show some sample auto paths
library = meta_path_library
all_paths = library._paths_by_tag  # dict of tag -> [meta_path_ids]
print(f"\nSample auto-generated paths:")

# Find some auto paths
auto_paths = [p for p in library._paths if p.id.startswith('auto_') or p.id.startswith('base_')]
print(f"Auto paths found: {len(auto_paths)}")

# Show first 10
for p in auto_paths[:10]:
    tables_str = ' -> '.join(p.tables)
    print(f"  [{p.id}] {p.name}")
    print(f"    Tables: {tables_str}")
