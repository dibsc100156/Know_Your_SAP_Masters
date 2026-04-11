#!/usr/bin/env python3
"""
Seed SQL Patterns into ChromaDB
==============================
Loads all 18-domain SQL pattern library into the ChromaDB vector store
for semantic retrieval by the SQL RAG system.

Usage:
    python -m app.core.sql_patterns.seed_patterns
    python -m app.core.sql_patterns.seed_patterns --domain material_master
    python -m app.core.sql_patterns.seed_patterns --stats
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sentence_transformers import SentenceTransformer
import chromadb

from app.core.sql_patterns.library import (
    PATTERNS_BY_DOMAIN,
    get_all_patterns,
    get_pattern_count,
)


def get_embedding_model():
    """Load the embedding model used by the SQL RAG system."""
    print("[INIT] Loading embedding model: all-MiniLM-L6-v2")
    return SentenceTransformer("all-MiniLM-L6-v2")


def get_chroma_client(db_path: str = "./chroma_db"):
    """Initialize ChromaDB persistent client."""
    print(f"[INIT] Connecting to ChromaDB at: {db_path}")
    client = chromadb.PersistentClient(path=db_path)
    return client


def seed_domain(domain: str, encoder, client, collection_name: str = "sap_sql_patterns"):
    """Seed patterns for a single domain into ChromaDB."""
    patterns = PATTERNS_BY_DOMAIN.get(domain, [])
    if not patterns:
        print(f"[WARN] No patterns found for domain: {domain}")
        return 0

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

    ids = []
    embeddings = []
    metadatas = []
    documents = []

    for pattern in patterns:
        query_id = f"{domain}_{pattern['intent'].lower().replace(' ', '_')[:40]}"

        # Embed the business intent + use case for semantic matching
        text_to_embed = f"Business Question: {pattern['intent']} | Use Case: {pattern['business_use_case']} | Tables: {', '.join(pattern['tables'])}"

        ids.append(query_id)
        embeddings.append(encoder.encode(text_to_embed).tolist())
        documents.append(pattern["sql"].strip())
        metadatas.append({
            "domain": domain,
            "intent": pattern["intent"],
            "business_use_case": pattern["business_use_case"],
            "tables_used": ",".join(pattern["tables"]),
        })

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents,
    )

    print(f"[OK] Seeded {len(patterns)} patterns for domain: {domain}")
    return len(patterns)


def seed_all_domains(collection_name: str = "sap_sql_patterns", db_path: str = "./chroma_db"):
    """Seed all domains into ChromaDB."""
    encoder = get_embedding_model()
    client = get_chroma_client(db_path)

    # Clear existing collection for clean slate
    try:
        client.delete_collection(name=collection_name)
        print(f"[RESET] Cleared existing collection: {collection_name}")
    except Exception:
        pass

    total = 0
    domains = sorted(PATTERNS_BY_DOMAIN.keys())

    print(f"\n[SEED] Starting pattern seeding across {len(domains)} domains...")

    for domain in domains:
        count = seed_domain(domain, encoder, client, collection_name)
        total += count

    print(f"\n[OK] Total patterns seeded: {total}")
    return total


def print_stats():
    """Print statistics about the pattern library."""
    domains = sorted(PATTERNS_BY_DOMAIN.keys())
    total = get_pattern_count()

    print(f"\n{'=' * 60}")
    print(f"  SQL Pattern Library Statistics")
    print(f"{'=' * 60}")
    print(f"  Total Domains: {len(domains)}")
    print(f"  Total Patterns: {total}")
    print(f"{'=' * 60}\n")

    for domain in domains:
        count = len(PATTERNS_BY_DOMAIN[domain])
        tables = set()
        for p in PATTERNS_BY_DOMAIN[domain]:
            tables.update(p["tables"])

        print(f"  {domain:<30} {count:>3} patterns | {len(tables)} tables")

    print(f"\n{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Seed SQL patterns into ChromaDB")
    parser.add_argument("--domain", type=str, default=None,
                        help="Seed only a specific domain (e.g., material_master)")
    parser.add_argument("--stats", action="store_true",
                        help="Show pattern library statistics")
    parser.add_argument("--db-path", type=str, default="./chroma_db",
                        help="Path to ChromaDB storage")
    parser.add_argument("--collection", type=str, default="sap_sql_patterns",
                        help="ChromaDB collection name")

    args = parser.parse_args()

    if args.stats:
        print_stats()
        return 0

    if args.domain:
        encoder = get_embedding_model()
        client = get_chroma_client(args.db_path)
        count = seed_domain(args.domain, encoder, client, args.collection)
        print(f"\n[OK] Seeded {count} patterns for: {args.domain}")
    else:
        seed_all_domains(collection_name=args.collection, db_path=args.db_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
