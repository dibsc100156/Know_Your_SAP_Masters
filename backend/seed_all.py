#!/usr/bin/env python3
"""
Seed all vector stores for SAP Masters 5-Pillar RAG.
=====================================================
Seeds ChromaDB with:
  - DDIC schema metadata (Table RAG)
  - SQL patterns (SQL Pattern RAG)

Usage:
    python seed_all.py              # Seed both stores
    python seed_all.py --stats      # Show store counts
    python seed_all.py --force       # Force re-seed (delete existing data)
"""

import sys
import os
import argparse

# Ensure app imports work
sys.path.insert(0, os.path.dirname(__file__))

DOMAINS = {
    "business_partner":    __import__("app.domain.business_partner_schema",    fromlist=["BUSINESS_PARTNER_TABLES"]).BUSINESS_PARTNER_TABLES,
    "material_master":     __import__("app.domain.material_master_schema",     fromlist=["MATERIAL_MASTER_TABLES"]).MATERIAL_MASTER_TABLES,
    "purchasing":          __import__("app.domain.purchasing_schema",          fromlist=["PURCHASING_TABLES"]).PURCHASING_TABLES,
    "sales_distribution": __import__("app.domain.sales_distribution_schema",fromlist=["SALES_DISTRIBUTION_TABLES"]).SALES_DISTRIBUTION_TABLES,
    "warehouse_management":__import__("app.domain.warehouse_management_schema",fromlist=["WAREHOUSE_MANAGEMENT_TABLES"]).WAREHOUSE_MANAGEMENT_TABLES,
    "quality_management":  __import__("app.domain.quality_management_schema", fromlist=["QUALITY_MANAGEMENT_TABLES"]).QUALITY_MANAGEMENT_TABLES,
    "project_system":      __import__("app.domain.project_system_schema",     fromlist=["PROJECT_SYSTEM_TABLES"]).PROJECT_SYSTEM_TABLES,
    "transportation":      __import__("app.domain.transportation_schema",     fromlist=["TRANSPORTATION_TABLES"]).TRANSPORTATION_TABLES,
    "customer_service":    __import__("app.domain.customer_service_schema",   fromlist=["CUSTOMER_SERVICE_TABLES"]).CUSTOMER_SERVICE_TABLES,
    "ehs":                 __import__("app.domain.ehs_schema",                fromlist=["EHS_TABLES"]).EHS_TABLES,
    "variant_configuration":__import__("app.domain.variant_configuration_schema",fromlist=["VARIANT_CONFIGURATION_TABLES"]).VARIANT_CONFIGURATION_TABLES,
    "real_estate":         __import__("app.domain.real_estate_schema",       fromlist=["REAL_ESTATE_TABLES"]).REAL_ESTATE_TABLES,
    "gts":                 __import__("app.domain.gts_schema",               fromlist=["GTS_TABLES"]).GTS_TABLES,
    "is_oil":              __import__("app.domain.is_oil_schema",             fromlist=["IS_OIL_TABLES"]).IS_OIL_TABLES,
    "is_retail":           __import__("app.domain.is_retail_schema",          fromlist=["IS_RETAIL_TABLES"]).IS_RETAIL_TABLES,
    "is_utilities":        __import__("app.domain.is_utilities_schema",       fromlist=["IS_UTILITIES_TABLES"]).IS_UTILITIES_TABLES,
    "is_health":           __import__("app.domain.is_health_schema",          fromlist=["IS_HEALTH_TABLES"]).IS_HEALTH_TABLES,
    "taxation_india":      __import__("app.domain.taxation_india_schema",     fromlist=["TAXATION_INDIA_TABLES"]).TAXATION_INDIA_TABLES,
}

STUB_TABLES = {"LAGP", "MAPL", "KONP", "VTTK", "PRPS", "QALS_BASE"}


def seed_chroma_schemas(db_path: str = "./chroma_db", force: bool = False):
    """Seed ChromaDB with DDIC schema metadata."""
    from sentence_transformers import SentenceTransformer
    import chromadb

    print("[CHROMA] Loading embedding model: all-MiniLM-L6-v2")
    encoder = SentenceTransformer("all-MiniLM-L6-v2")

    print(f"[CHROMA] Connecting to ChromaDB at: {db_path}")
    client = chromadb.PersistentClient(path=db_path)

    collection_name = "sap_master_schemas"
    try:
        if force:
            try:
                client.delete_collection(collection_name)
                print(f"[CHROMA] Reset existing collection: {collection_name}")
            except Exception:
                print(f"[CHROMA] Collection {collection_name} not found — creating fresh")
        collection = client.create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})
    except Exception:
        collection = client.get_collection(collection_name)
        if force:
            collection.delete(delete_all=True)
        collection = client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    total_tables = 0
    total_domains_loaded = 0

    for domain_name, tables in sorted(DOMAINS.items()):
        real_tables = {t: v for t, v in tables.items() if t not in STUB_TABLES and len(v.get("columns", [])) > 1}
        if not real_tables:
            print(f"[CHROMA]   {domain_name}: SKIPPED (stub domain)")
            continue

        ids, embeddings, documents, metadatas = [], [], [], []
        for table_name, table_def in real_tables.items():
            col_desc = ", ".join(
                f"{c['name']} ({c.get('type','?')}): {c.get('desc','')}"
                for c in table_def.get("columns", [])
            )
            doc = f"Table {table_name} — {table_def.get('description','')}. Columns: {col_desc}"
            ids.append(f"schema_{domain_name}_{table_name}")
            embeddings.append(encoder.encode(doc).tolist())
            documents.append(doc)
            metadatas.append({
                "table": table_name,
                "module": table_def.get("module", ""),
                "domain": domain_name,
            })

        if ids:
            collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
            total_tables += len(ids)
            total_domains_loaded += 1
            print(f"[CHROMA]   {domain_name}: {len(ids)} tables loaded ✓")

    count = collection.count()
    print(f"\n[CHROMA] ✓ Done. {total_tables} schemas seeded across {total_domains_loaded} domains.")
    print(f"[CHROMA]   Total vectors in sap_master_schemas: {count}")
    return total_tables


def seed_chroma_sql(db_path: str = "./chroma_db", force: bool = False):
    """Seed ChromaDB with SQL patterns from the library."""
    from sentence_transformers import SentenceTransformer
    import chromadb
    from app.core.sql_patterns.library import PATTERNS_BY_DOMAIN

    # Merge mega-generated patterns
    MODULE_TO_DOMAIN = {
        'MM':'material_master','MM-PUR':'purchasing','BP':'business_partner',
        'SD':'sales_distribution','FI':'business_partner','CO':'project_system',
        'QM':'quality_management','WM':'warehouse_management','PM':'customer_service',
        'PS':'project_system','TM':'transportation','CS':'customer_service',
        'HR':'business_partner','RE':'real_estate','GTS':'gts',
        'IS-OIL':'is_oil','IS-UTILITY':'is_utilities','IS-RETAIL':'is_retail',
        'IS-HEALTH':'is_health','TAX':'taxation_india','LO-VC':'variant_configuration',
        'AUTO':'business_partner',
    }
    try:
        from app.core.sql_patterns.mega_generated_patterns import MEGA_PATTERNS
        added = 0
        for p in MEGA_PATTERNS:
            domain = MODULE_TO_DOMAIN.get(p.get('module','AUTO'), 'business_partner')
            if domain in PATTERNS_BY_DOMAIN:
                PATTERNS_BY_DOMAIN[domain].append(p); added += 1
            else:
                for d in PATTERNS_BY_DOMAIN:
                    PATTERNS_BY_DOMAIN[d].append(p); added += 1; break
        print(f"[CHROMA] Merged {added} mega patterns. Total: {sum(len(v) for v in PATTERNS_BY_DOMAIN.values())}")
    except Exception as e:
        print(f"[CHROMA] Mega patterns not loaded: {e}")

    print("[CHROMA] Loading embedding model: all-MiniLM-L6-v2")
    encoder = SentenceTransformer("all-MiniLM-L6-v2")

    print(f"[CHROMA] Connecting to ChromaDB at: {db_path}")
    client = chromadb.PersistentClient(path=db_path)

    collection_name = "sap_sql_patterns"
    try:
        if force:
            try:
                client.delete_collection(collection_name)
                print(f"[CHROMA] Reset existing collection: {collection_name}")
            except Exception:
                print(f"[CHROMA] Collection {collection_name} not found — creating fresh")
        collection = client.create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})
    except Exception:
        collection = client.get_collection(collection_name)
        if force:
            collection.delete(delete_all=True)
        collection = client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    total_patterns = 0
    domains_loaded = 0

    for domain in sorted(PATTERNS_BY_DOMAIN.keys()):
        patterns = PATTERNS_BY_DOMAIN[domain]
        if not patterns:
            continue

        ids, embeddings, documents, metadatas = [], [], [], []
        for i, pattern in enumerate(patterns):
            query_id = f"{domain}_{pattern['intent'].lower().replace(' ', '_')[:40]}_{i}"
            text_to_embed = (
                f"Business Question: {pattern['intent']} | "
                f"Use Case: {pattern['business_use_case']} | "
                f"Tables: {', '.join(pattern['tables'])}"
            )
            ids.append(query_id)
            embeddings.append(encoder.encode(text_to_embed).tolist())
            documents.append(pattern["sql"].strip())
            metadatas.append({
                "domain": domain,
                "intent": pattern["intent"],
                "business_use_case": pattern["business_use_case"],
                "tables_used": ",".join(pattern["tables"]),
            })

        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
        total_patterns += len(patterns)
        domains_loaded += 1
        print(f"[CHROMA]   {domain}: {len(patterns)} patterns loaded ✓")

    print(f"\n[CHROMA] ✓ Done. {total_patterns} SQL patterns seeded across {domains_loaded} domains.")
    return total_patterns


def show_stats(chroma_path: str = "./chroma_db"):
    """Show current store statistics."""
    print(f"\n{'=' * 60}")
    print("  Vector Store Statistics")
    print(f"{'=' * 60}")

    try:
        import chromadb
        client = chromadb.PersistentClient(path=chroma_path)

        try:
            sc = client.get_collection("sap_master_schemas")
            print(f"  ChromaDB sap_master_schemas: {sc.count()} vectors")
        except Exception:
            print("  ChromaDB sap_master_schemas: NOT INITIALIZED")

        try:
            sp = client.get_collection("sap_sql_patterns")
            print(f"  ChromaDB sap_sql_patterns: {sp.count()} vectors")
        except Exception:
            print("  ChromaDB sap_sql_patterns: NOT INITIALIZED")

    except Exception as e:
        print(f"  ChromaDB: ERROR — {e}")

    try:
        from app.core.sql_patterns.library import PATTERNS_BY_DOMAIN
        total = sum(len(p) for p in PATTERNS_BY_DOMAIN.values())
        domains = len(PATTERNS_BY_DOMAIN)
        print(f"  SQL Pattern Library: {total} patterns across {domains} domains")
    except Exception as e:
        print(f"  SQL Pattern Library: ERROR — {e}")

    print(f"{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(description="Seed all vector stores for SAP Masters RAG")
    parser.add_argument("--force", action="store_true", help="Force re-seed (delete existing data)")
    parser.add_argument("--stats", action="store_true", help="Show store statistics")
    parser.add_argument("--chroma-path", default="./chroma_db", help="ChromaDB path")

    args = parser.parse_args()

    if args.stats:
        show_stats(args.chroma_path)
        return 0

    print(f"\n{'=' * 60}")
    print("  SEEDING ALL VECTOR STORES (ChromaDB)")
    print(f"{'=' * 60}\n")

    seed_chroma_schemas(args.chroma_path, args.force)
    print()
    seed_chroma_sql(args.chroma_path, args.force)

    print("\n[DONE] Run `python -m uvicorn app.main:app --reload --port 8000` to start the API.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
