"""
orchestrator_tools.py — Pillar 2 Tool Registry
===============================================
Unified tool registry for the Agentic RAG Orchestrator.
Every tool wraps a CLI function or library call and exposes:
  - name, description
  - input_schema
  - execute(params, auth_context) -> result

Tools map to the 5 Pillars:
  Pillar 3: schema_lookup()
  Pillar 4: sql_pattern_lookup()
  Pillar 5: graph_traverse()
  Security: sql_validate()
  Execution: sql_execute()
  Masking: result_mask()
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import json




def meta_harness_propose(params: Dict[str, Any], auth_context: Any) -> Dict[str, Any]:
    """
    [Meta-Harness] Automated Meta-Harness Loop.
    Reads recent HarnessRun failures from Redis, groups by pattern,
    diagnoses root causes via LLM, and outputs YAML recommendations
    for human review before applying patches.

    IMPORTANT: Runs in ADVISORY MODE — patches are saved to YAML, not auto-applied.
    """
    from app.core.meta_harness_loop import MetaHarnessLoop, RECOMMENDATIONS_DIR
    import logging
    logger = logging.getLogger("meta-harness")

    days = params.get("days", 7)
    limit = params.get("limit", 200)

    try:
        mh = MetaHarnessLoop()
        recommendations = mh.analyze_recent_failures(days=days, limit=limit)

        if not recommendations:
            return {
                "status": "healthy",
                "message": "No recent HarnessRun failures found — harness is healthy.",
                "days_analyzed": days,
                "recommendations": [],
            }

        # Format recommendations for the orchestrator
        rec_summaries = []
        for rec in sorted(recommendations, key=lambda r: ["P0","P1","P2"].index(r.priority)):
            rec_summaries.append({
                "id": rec.id,
                "priority": rec.priority,
                "title": rec.title,
                "category": rec.category,
                "target_file": rec.target_file,
                "effort": rec.effort,
                "risk": rec.risk,
                "status": rec.status,
                "evidence": rec.evidence[:200],
                "patch_lines": rec.patch_lines[:5] if rec.patch_lines else [],
            })

        latest_file = sorted(RECOMMENDATIONS_DIR.glob("analysis_*.yaml"))[-1] if list(RECOMMENDATIONS_DIR.glob("analysis_*.yaml")) else None

        return {
            "status": "recommendations_ready",
            "days_analyzed": days,
            "failures_collected": limit,
            "recommendation_count": len(recommendations),
            "recommendations": rec_summaries,
            "yaml_file": str(latest_file) if latest_file else None,
            "advisory_note": "Review YAML before applying. Use approve_and_apply(rec_ids=[...]) to patch.",
        }
    except Exception as e:
        logger.exception("meta_harness_propose failed")
        return {"status": "error", "message": str(e)}

# =============================================================================
# Tool Result / Error Types
# =============================================================================

class ToolStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    PARTIAL = "partial"  # Some results but not all


@dataclass
class ToolResult:
    status: ToolStatus
    data: Any = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "data": self.data,
            "message": self.message,
            "metadata": self.metadata,
        }


# =============================================================================
# Pillar 3: Schema RAG — Schema Lookup Tool
# =============================================================================

def schema_lookup(
    query: str,
    auth_context=None,
    domain: str = "auto",
    n_results: int = 4,
) -> ToolResult:
    """
    [Pillar 3] Schema RAG — Find SAP tables matching a natural language query.

    Uses the VectorStoreManager (ChromaDB by default, Qdrant when
    VECTOR_STORE_BACKEND=qdrant is set) to perform semantic search against
    the sap_schema collection (384d, cosine). Results are filtered by
    auth_context (role-based table/column masking) before returning.

    Args:
        query: Natural language query (e.g., "find vendor tables")
        auth_context: Optional SAPAuthContext for role-based filtering
        domain: Domain filter (auto, business_partner, material_master, etc.)
        n_results: Max number of results to return

    Returns:
        ToolResult with list of matching schemas
    """
    from app.core.vector_store import store_manager

    try:
        # Step 1: Vector search (Schema RAG — Pillar 3)
        raw_results = store_manager.search_schema(query, n_results=n_results, domain=domain)

        if not raw_results:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f"No schemas found matching: '{query}'",
                metadata={"query": query}
            )

        # Step 2: Role-based filtering + column masking
        tables_used = []
        filtered_schemas = []

        for r in raw_results[:n_results]:
            meta = r.get("metadata", {})
            table_name = meta.get("table", "")

            if auth_context and not auth_context.is_table_allowed(table_name):
                continue

            # Parse key_columns from the document text for auth_object matching
            doc = r.get("document", "")
            description = meta.get("module", "")  # fallback

            filtered_schemas.append({
                "table": table_name,
                "description": description,
                "module": meta.get("module", ""),
                "key_columns": [],
                "auth_object": "",
            })
            tables_used.append(table_name)

        if not filtered_schemas:
            return ToolResult(
                status=ToolStatus.ERROR,
                message="No authorized tables found for your query in this domain.",
                metadata={"query": query, "domain": domain}
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "schemas": filtered_schemas,
                "tables_used": tables_used,
                "query": query,
                "domain": domain,
                "backend": store_manager.backend_name,
            },
            message=f"Found {len(filtered_schemas)} authorized table(s) [backend={store_manager.backend_name}]",
            metadata={"query": query, "domain": domain, "backend": store_manager.backend_name}
        )

    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Schema lookup failed: {str(e)}",
            metadata={"query": query}
        )


# =============================================================================
# Pillar 5½: Graph-Enhanced Schema Discovery
# =============================================================================

def graph_enhanced_schema_discovery(
    query: str,
    auth_context=None,
    domain: str = "auto",
    top_k: int = 5,
    expand_neighbors: int = 2,
) -> ToolResult:
    """
    [Pillar 5½] Graph Embedding Search — Semantic + Structural Table Discovery.

    Uses two embedding layers over the SAP NetworkX FK graph:
      Layer 1 — Node2Vec structural: captures hub/authority/bridge roles via
                random walks on the FK relationship graph.
      Layer 2 — Context-rich text: table description + module + domain +
                structural_role + top-6 neighbors encoded via all-MiniLM-L6-v2.

    Fusion: 0.6 * structural_centrality_percentile + 0.4 * text_similarity.

    This is the Graph Embedding Store (Phase 2) discovering tables that are
    both semantically relevant AND structurally important — even if they don't
    appear in the top text matches. Key example:
      "vendor payment terms" → LFA1 surfaces as #1 (cross-module bridge score)
      vs. naive text-only search which might miss LFB5 (payment history).

    Args:
        query:           Natural language table search query
        auth_context:    Optional SAPAuthContext for role-based filtering
        domain:          Domain filter (auto = all domains)
        top_k:           Return top-K tables (default: 5)
        expand_neighbors: How many graph neighbors to surface per result (default: 2)

    Returns:
        ToolResult with list of discovered tables, each enriched with:
          structural_role, is_cross_module_bridge, centrality_percentile,
          cross_module_paths, composite_score, structural_score, text_score
    """
    try:
        from app.core.graph_embedding_store import graph_embedding_store

        # ── Graph Embedding Store must be initialized ───────────────────────
        try:
            store = graph_embedding_store
            _ = store._structural_ctx  # guard against uninitialized singleton
        except Exception:
            # Lazy init — build if not already built
            from app.core.graph_embedding_store import init_graph_embeddings
            store = init_graph_embeddings(force=False)

        # ── Run hybrid search ─────────────────────────────────────────────
        results = store.search_graph_tables(
            query=query,
            domain=domain,
            top_k=top_k,
            structural_weight=0.6,
            text_weight=0.4,
        )

        if not results:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f"No graph-embedded tables found for: '{query}'",
                metadata={"query": query, "domain": domain},
            )

        # ── Role-based filtering ───────────────────────────────────────────
        allowed = []
        for row in results:
            table_name = row["table"]
            if auth_context and not auth_context.is_table_allowed(table_name):
                continue
            allowed.append(row)

        if not allowed:
            return ToolResult(
                status=ToolStatus.ERROR,
                message="All graph-discovered tables are filtered by role permissions.",
                metadata={"query": query, "domain": domain},
            )

        # ── Enrich with graph neighbor context ─────────────────────────────
        for row in allowed:
            table = row["table"]
            full_ctx = store.get_structural_context(table)
            if full_ctx:
                # Add most relevant neighbors (limited to expand_neighbors)
                row["neighbors"] = [
                    {"table": n["table"], "domain": n["domain"], "cardinality": n["cardinality"]}
                    for n in full_ctx.neighbors[:expand_neighbors]
                ]
            else:
                row["neighbors"] = []

        tables_discovered = [r["table"] for r in allowed]

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "tables": allowed,
                "tables_discovered": tables_discovered,
                "query": query,
                "domain": domain,
            },
            message=f"Graph embedding search found {len(allowed)} table(s): {tables_discovered}",
            metadata={
                "query": query,
                "domain": domain,
                "num_results": len(allowed),
            },
        )

    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Graph enhanced discovery failed: {str(e)}",
            metadata={"query": query},
        )


# =============================================================================
# Pillar 4: SQL RAG — Pattern Lookup Tool
# =============================================================================

def sql_pattern_lookup(
    query: str,
    auth_context=None,
    domain: str = "auto",
    n_results: int = 2,
) -> ToolResult:
    """
    [Pillar 4] SQL RAG — Find proven SAP HANA SQL patterns matching a query.

    Uses the VectorStoreManager (ChromaDB by default, Qdrant when
    VECTOR_STORE_BACKEND=qdrant is set) to search the sql_patterns
    collection across all 18 SAP domains.

    Each stored pattern includes: intent, validated SQL, domain, tables_used.

    Args:
        query: Natural language business question (e.g., "show open purchase orders")
        auth_context: Optional SAPAuthContext for role-based table filtering
        domain: Domain filter (auto, purchasing, business_partner, etc.)
        n_results: Max number of patterns to return

    Returns:
        ToolResult with list of matching SQL patterns
    """
    from app.core.vector_store import store_manager

    try:
        # Vector search via unified store manager (ChromaDB or Qdrant backend)
        raw_results = store_manager.search_sql_patterns(
            query, n_results=n_results, domain=domain
        )

        if not raw_results:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f"No SQL patterns found matching: '{query}'",
                metadata={"query": query}
            )

        # Normalize Qdrant response (intent + sql) to ChromaDB-compatible shape
        patterns = []
        for r in raw_results:
            intent = r.get("intent", "")
            pattern = {
                "query_id": intent[:60] if intent else "unknown",
                "intent": intent,
                "business_use_case": r.get("business_use_case", ""),
                "tables": r.get("tables_used", []) or r.get("tables", []),
                "distance": 0.0,  # Qdrant doesn't return distance in search_schema/search_sql_patterns output
                "sql": r.get("sql", ""),
                "domain": r.get("domain", ""),
            }
            patterns.append(pattern)

        # Role-based table filtering
        if auth_context:
            filtered = []
            for p in patterns:
                tables = p.get("tables", [])
                if isinstance(tables, str):
                    tables = [t.strip() for t in tables.split(",") if t.strip()]
                if all(auth_context.is_table_allowed(str(t).strip()) for t in tables):
                    filtered.append(p)
            if not filtered and patterns:
                return ToolResult(
                    status=ToolStatus.PARTIAL,
                    data={"patterns": filtered, "original_count": len(patterns)},
                    message="Some patterns filtered due to role restrictions.",
                    metadata={"query": query}
                )
            patterns = filtered

        if not patterns:
            return ToolResult(
                status=ToolStatus.ERROR,
                message="No authorized SQL patterns found for your role.",
                metadata={"query": query, "role": getattr(auth_context, 'role_id', None)}
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "patterns": patterns,
                "query": query,
                "top_match_distance": patterns[0]["distance"] if patterns else None,
                "backend": store_manager.backend_name,
            },
            message=f"Found {len(patterns)} proven SQL pattern(s) [backend={store_manager.backend_name}]",
            metadata={"query": query, "backend": store_manager.backend_name}
        )

    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"SQL pattern lookup failed: {str(e)}",
            metadata={"query": query}
        )


# =============================================================================
# Pillar 5: Graph RAG — Join Path Traversal Tool
# =============================================================================

def graph_traverse(
    start_table: str,
    end_table: str,
    format: str = "join",
) -> ToolResult:
    """
    [Pillar 5] Graph RAG — Find the shortest JOIN path between two SAP tables.

    Uses NetworkX to traverse the SAP Foreign Key relationship graph.
    Returns formatted SQL JOIN clause, path list, or raw JSON.

    Args:
        start_table: Starting table (e.g., "LFA1")
        end_table: Target table (e.g., "MARA")
        format: Output format — "join" (SQL), "path" (table list), "json"

    Returns:
        ToolResult with JOIN path details
    """
    from app.core.graph_store import graph_store

    try:
        start = start_table.upper().strip()
        end = end_table.upper().strip()

        all_nodes = list(graph_store.G.nodes)
        missing = []
        if start not in all_nodes:
            missing.append(start)
        if end not in all_nodes:
            missing.append(end)

        if missing:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f"Tables not found in Graph schema: {', '.join(missing)}",
                metadata={"start": start, "end": end, "available_nodes": all_nodes[:20]}
            )

        result = graph_store.traverse_graph(start, end)

        if "No direct join" in result or "No JOIN needed" in result:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=result,
                metadata={"start": start, "end": end}
            )

        # Extract tables from path
        tables_in_path = []
        for line in result.split("\n"):
            if "Start at" in line:
                tables_in_path.append(line.split("Start at")[1].strip())
            elif "INNER JOIN" in line or "LEFT JOIN" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    tables_in_path.append(parts[2])

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "start": start,
                "end": end,
                "join_path": result,
                "tables_in_path": tables_in_path,
                "join_count": len([l for l in result.split("\n") if "JOIN" in l]),
            },
            message=f"Found JOIN path: {' -> '.join(tables_in_path)}",
            metadata={"start": start, "end": end, "hops": len(tables_in_path) - 1}
        )

    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Graph traversal failed: {str(e)}",
            metadata={"start": start_table, "end": end_table}
        )


# =============================================================================
# Security: SQL Validation Tool
# =============================================================================

def sql_validate(
    sql: str,
    auth_context=None,
    strict: bool = False,
) -> ToolResult:
    """
    [Security] Validate SAP HANA SQL for safety, syntax, and role-based access.

    Checks:
    1. SELECT-only (no DML/DDL)
    2. No forbidden keywords (UPDATE, DELETE, INSERT, DROP, etc.)
    3. MANDT filter present
    4. Role-based table access
    5. AuthContext WHERE clause injection suggestions

    Args:
        sql: SQL query to validate
        auth_context: Optional SAPAuthContext for role-based validation
        strict: If True, warnings become errors

    Returns:
        ToolResult with validation result and suggested WHERE clauses
    """
    import re
    from app.core.security import security_mesh, SAPAuthContext

    FORBIDDEN = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                 "TRUNCATE", "GRANT", "REVOKE", "CREATE", "EXECUTE",
                 "MERGE", "COMMIT", "ROLLBACK"]

    try:
        sql_upper = sql.strip().upper()
        issues = []
        errors = []
        warnings = []

        # Check 1: Must be SELECT
        if not sql_upper.startswith("SELECT"):
            errors.append("Query must be a SELECT statement. No DML/DDL permitted.")

        # Check 2: No forbidden keywords
        for kw in FORBIDDEN:
            if re.search(rf"\b{kw}\b", sql_upper):
                errors.append(f"Forbidden keyword: {kw}")

        # Check 3: MANDT presence
        if "MANDT" not in sql_upper and "CLIENT" not in sql_upper:
            warnings.append("No MANDT/CLIENT filter detected. Best practice: always filter by client.")

        # Check 4: Role-based table access
        if auth_context:
            pattern = r"(?:FROM|JOIN)\s+([A-Z0-9_]+)"
            tables = re.findall(pattern, sql_upper)
            for table in tables:
                table = table.split()[0]
                if not auth_context.is_table_allowed(table):
                    errors.append(f"Access DENIED to table {table} for role {auth_context.role_id}")

        # Determine status
        if errors:
            status = ToolStatus.ERROR
        elif warnings and strict:
            status = ToolStatus.ERROR
        else:
            status = ToolStatus.SUCCESS

        # Suggest WHERE clauses
        suggestions = []
        if auth_context:
            if auth_context.allowed_company_codes and "*" not in auth_context.allowed_company_codes:
                b = "', '".join(auth_context.allowed_company_codes)
                suggestions.append(f"BUKRS IN ('{b}')")
            if auth_context.allowed_purchasing_orgs and "*" not in auth_context.allowed_purchasing_orgs:
                e = "', '".join(auth_context.allowed_purchasing_orgs)
                suggestions.append(f"EKORG IN ('{e}')")
            if auth_context.allowed_plants and "*" not in auth_context.allowed_plants:
                w = "', '".join(auth_context.allowed_plants)
                suggestions.append(f"WERKS IN ('{w}')")

        return ToolResult(
            status=status,
            data={
                "sql": sql,
                "valid": status == ToolStatus.SUCCESS,
                "errors": errors,
                "warnings": warnings,
                "suggestions": suggestions,
            },
            message="VALIDATION FAILED" if errors else "VALIDATION PASSED",
            metadata={"error_count": len(errors), "warning_count": len(warnings)}
        )

    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Validation error: {str(e)}",
            metadata={"sql": sql[:100]}
        )


# =============================================================================
# Execution: SQL Execute Tool (Dry-Run)
# =============================================================================

def sql_execute(
    sql: str,
    auth_context=None,
    dry_run: bool = True,
    max_rows: int = 1000,
) -> ToolResult:
    """
    [Execution] Execute validated SAP HANA SQL against mock or real database.

    Args:
        sql: SELECT statement to execute
        auth_context: SAPAuthContext for masking
        dry_run: If True, validates and returns mock data only
        max_rows: Row limit (default: 1000)

    Returns:
        ToolResult with execution results
    """
    import pandas as pd
    from app.tools.sql_executor import SAPSQLExecutor

    try:
        # Validate first
        validation = sql_validate(sql, auth_context)
        if validation.status == ToolStatus.ERROR:
            return validation

        # Execute
        executor = SAPSQLExecutor(connection=None, max_rows=max_rows)

        if dry_run or not executor.connection:
            df = executor._mock_execution(sql)
        else:
            df = executor.execute(sql, auth_context)

        # Apply masking
        if auth_context:
            df = executor._mask_results(df, auth_context)

        masked_fields = [
            f for f in getattr(auth_context, "masked_fields", {}).keys()
            if any(c.upper() in f.upper() for c in df.columns)
        ] if not df.empty else []

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "rows": df.to_dict(orient="records") if df is not None else [],
                "row_count": len(df) if df is not None else 0,
                "masked_fields": masked_fields,
                "executed_sql": sql,
            },
            message=f"Executed successfully. {len(df) if df is not None else 0} row(s) returned.",
            metadata={"mock": dry_run or not executor.connection}
        )

    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Execution failed: {str(e)}",
            metadata={"sql": sql[:100]}
        )


# =============================================================================
# Masking: Result Set Masking Tool
# =============================================================================

def result_mask(
    data: List[Dict],
    auth_context,
) -> ToolResult:
    """
    [Pillar 1] Apply role-based column masking to result sets.

    Args:
        data: List of row dictionaries
        auth_context: SAPAuthContext with masked_fields definition

    Returns:
        ToolResult with masked data and list of masked field names
    """
    try:
        if not data or not auth_context:
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={"rows": data, "masked_fields": []},
                message="No masking needed."
            )

        masked_fields = []
        result = []

        for row in data:
            masked_row = {}
            for col, val in row.items():
                is_masked = any(
                    mask.upper() in f"{col}".upper() or mask.upper() == f"{col}".upper()
                    for mask in auth_context.masked_fields.keys()
                )
                if is_masked:
                    masked_row[col] = "*****"
                    if col not in masked_fields:
                        masked_fields.append(col)
                else:
                    masked_row[col] = val
            result.append(masked_row)

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"rows": result, "masked_fields": masked_fields},
            message=f"Masked {len(masked_fields)} field(s): {', '.join(masked_fields)}",
            metadata={"row_count": len(result)}
        )

    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Masking failed: {str(e)}",
            metadata={}
        )


# =============================================================================
# New Pillar 5 Tools: Meta-Path Match & All-Paths Explore
# =============================================================================

def meta_path_match(query: str, auth_context=None, domain: str = None, top_k: int = 2) -> ToolResult:
    """[Pillar 5] Check pre-computed meta-paths for an exact business intent match."""
    from app.core.meta_path_library import meta_path_library
    try:
        results = meta_path_library.match(query, domain=domain, top_k=top_k)
        if not results:
            return ToolResult(status=ToolStatus.ERROR, message="No meta-path match found.")
            
        top_match = results[0]
        # Only use it if confidence is relatively high (>5.0 is a solid hit)
        if top_match["match_score"] < 5.0:
            return ToolResult(
                status=ToolStatus.PARTIAL, 
                data={"best_match": top_match},
                message=f"Weak match found ({top_match['match_score']}), falling back to dynamic RAG."
            )
            
        # Optional: check if the tables in the meta-path are allowed by auth_context
        if auth_context:
            for table in top_match["tables"]:
                if not auth_context.is_table_allowed(table):
                    return ToolResult(status=ToolStatus.ERROR, message=f"Meta-path requires unauthorized table {table}")
                    
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"match": top_match},
            message=f"Meta-path MATCHED: {top_match['name']} (score: {top_match['match_score']})"
        )
    except Exception as e:
        return ToolResult(status=ToolStatus.ERROR, message=f"Meta-path match failed: {str(e)}")

def all_paths_explore(start_table: str, end_table: str, max_depth: int = 5, top_k: int = 3) -> ToolResult:
    """[Pillar 5] Find all valid JOIN paths ranked by score."""
    from app.core.graph_store import path_explorer
    try:
        start = start_table.upper().strip()
        end = end_table.upper().strip()
        paths = path_explorer.find_all_ranked_paths(start, end, max_depth=max_depth, top_k=top_k)
        
        if not paths:
            return ToolResult(status=ToolStatus.ERROR, message=f"No paths found between {start} and {end}")
            
        # Format the best path as a JOIN clause for the orchestrator
        best_path = paths[0]
        join_lines = [f"Start at {best_path['path'][0]}"]
        for d in best_path["details"]:
            join_lines.append(f"{d['condition']} → ({d['from']} → {d['to']}) [{d['cardinality']}]")
            
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "ranked_paths": paths,
                "best_join_clause": "\n".join(join_lines),
                "best_path_tables": best_path["path"]
            },
            message=f"Found {len(paths)} ranked paths. Best score: {best_path['score']} ({' → '.join(best_path['path'])})"
        )
    except Exception as e:
        return ToolResult(status=ToolStatus.ERROR, message=f"Path exploration failed: {str(e)}")


def temporal_graph_search(
    query: str,
    start_table: str = None,
    end_table: str = None,
    key_date: str = None,
) -> ToolResult:
    """
    [Pillar 5] Temporal-aware Graph RAG.

    Detects if the query contains a temporal anchor (specific date, fiscal period,
    month name, "as of", "for period", "as on", etc.) and resolves the JOIN path
    with temporal validity filters applied.

    Supports:
    - Specific date:   "as of March 15 2024", "as on 01.01.2024"
    - Month/year:      "for February 2025", "Q4 2024", "FY2024"
    - Relative:        "current", "as of today", "latest"
    - Fiscal:          "FY25 P3", "period 007 2024", "GJAHR 2024 PERBL 12"

    Returns the best JOIN path + temporal SQL WHERE clauses for the key date.
    """
    from app.core.graph_store import temporal_graph
    import re

    try:
        from datetime import date
    except ImportError:
        from datetime import date as _date

    detected_date = None
    detected_period = None
    fiscal_year = None
    fiscal_period = None

    # Relative anchors
    if re.search(r'\b(today|current|latest|present)\b', query, re.IGNORECASE):
        detected_date = date.today()

    # SAP period format: FY25, FY2025
    fy_match = re.search(r'\b(FY ?(\d{2,4}))\b', query, re.IGNORECASE)
    if fy_match:
        fy_raw = fy_match.group(2).lstrip('0')
        if len(fy_raw) == 2:
            fy_int = int(fy_raw)
            fiscal_year = str(2000 + fy_int if fy_int < 50 else 1900 + fy_int)
        else:
            fiscal_year = fy_raw

    period_match = re.search(r'\b(?:period|p\.?)(\d{1,3})\b', query, re.IGNORECASE)
    if period_match:
        fiscal_period = f"{int(period_match.group(1)):03d}"

    q_match = re.search(r'\b(Q[1-4])[ ]?(\d{4})\b', query, re.IGNORECASE)
    if q_match:
        quarter = int(q_match.group(1)[1])
        start_month = (quarter - 1) * 3 + 1
        detected_date = date(int(q_match.group(2)), start_month, 1)

    # Specific date extraction (simple patterns — extensible with dateutil)
    if detected_date is None and fiscal_year is None:
        date_patterns = [
            (r'as of (.+?)(?:\?|\.|$|,)', 1),
            (r'as on (.+?)(?:\?|\.|$|,)', 1),
            (r'(\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4})', 1),
            (r'(\d{4}-\d{2}-\d{2})', 1),
            (r'(\w+ \d{1,2},? \d{4})', 1),
        ]
        for pattern, grp in date_patterns:
            m = re.search(pattern, query, re.IGNORECASE)
            if m:
                raw = m.group(grp).strip(', ')
                # Try parsing common formats
                for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
                    try:
                        from datetime import datetime
                        detected_date = datetime.strptime(raw, fmt).date()
                        break
                    except ValueError:
                        continue
                if detected_date:
                    break

    # Resolve temporal mode
    if fiscal_year and fiscal_period:
        resolved = f"FY{fiscal_year} P{fiscal_period.lstrip('0')}"
        temporal_mode = "fiscal"
    elif fiscal_year:
        resolved = f"FY{fiscal_year}"
        temporal_mode = "fiscal_year"
    elif detected_date:
        resolved = detected_date.strftime("%Y-%m-%d")
        temporal_mode = "key_date"
    else:
        return ToolResult(
            status=ToolStatus.ERROR,
            message="No temporal anchor detected in query.",
            metadata={"temporal_mode": "none"}
        )

    # Validate table names
    if not start_table or not end_table:
        return ToolResult(
            status=ToolStatus.ERROR,
            message="temporal_graph_search requires start_table and end_table.",
            metadata={"temporal_mode": temporal_mode, "resolved": resolved}
        )

    start = start_table.upper().strip()
    end = end_table.upper().strip()

    # Execute temporal path query
    from datetime import date as _date
    _resolved_date = detected_date or _date(int(fiscal_year), 1, 1)
    result = temporal_graph.query_as_of_date(start, end, _resolved_date)

    if "error" in result:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=result["error"],
            metadata={"start": start, "end": end, "temporal_mode": temporal_mode}
        )

    return ToolResult(
        status=ToolStatus.SUCCESS,
        data={
            "path": result["path"],
            "join_clause": result["join_clause"],
            "temporal_filters": result["temporal_filters"],
            "key_date": result["key_date"],
            "temporal_mode": temporal_mode,
            "resolved": resolved,
        },
        message=(
            f"Temporal path for {resolved}. "
            f"Filters: {' | '.join(result['temporal_filters'][:3])}"
        ),
        metadata={
            "temporal_mode": temporal_mode,
            "resolved": resolved,
            "filter_count": len(result["temporal_filters"]),
        }
    )


# =============================================================================
# Tool Registry — Unified Tool Dictionary
# =============================================================================

@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    execute: Callable
    pillars: List[str]  # Which pillars this tool belongs to


TOOL_REGISTRY: Dict[str, Tool] = {
    "schema_lookup": Tool(
        name="schema_lookup",
        description="[Pillar 3] Schema RAG. Find SAP tables matching a natural language query. "
                    "Returns table names, descriptions, and safe column lists filtered by role.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query (e.g., 'find vendor tables')"},
                "domain": {"type": "string", "description": "Domain filter (auto, purchasing, business_partner, etc.)"},
                "n_results": {"type": "integer", "description": "Max results (default: 4)"},
            },
            "required": ["query"]
        },
        execute=schema_lookup,
        pillars=["Pillar 3"],
    ),

    "graph_enhanced_schema_discovery": Tool(
        name="graph_enhanced_schema_discovery",
        description="[Pillar 5\u00bd] Graph Embedding Search. Uses Node2Vec structural embeddings "
                    "+ context-rich text embeddings to find semantically AND structurally relevant "
                    "SAP tables. Hybrid fusion: 0.6*structural_centrality + 0.4*text_similarity. "
                    "Discovers cross-module bridge tables that text-only search would miss. "
                    "Call this BEFORE sql_pattern_lookup when query involves cross-module concepts "
                    "(e.g., 'vendor payment history', 'material stock across plants').",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query (e.g., 'vendor payment terms') "
                                       "— can include cross-module intent"},
                "domain": {"type": "string", "description": "Domain filter (auto = all domains)"},
                "top_k": {"type": "integer", "description": "Top-K results (default: 5)"},
                "expand_neighbors": {"type": "integer", "description": "Graph neighbors to surface per result (default: 2)"},
            },
            "required": ["query"]
        },
        execute=graph_enhanced_schema_discovery,
        pillars=["Pillar 5\u00bd"],
    ),

    "sql_pattern_lookup": Tool(
        name="sql_pattern_lookup",
        description="[Pillar 4] SQL RAG. Find proven SAP HANA SQL patterns from the 68-pattern library "
                    "across 18 domains. Returns intent, business use case, tables, and validated SQL.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Business question (e.g., 'show open purchase orders')"},
                "domain": {"type": "string", "description": "Domain filter"},
                "n_results": {"type": "integer", "description": "Max patterns (default: 2)"},
            },
            "required": ["query"]
        },
        execute=sql_pattern_lookup,
        pillars=["Pillar 4"],
    ),

    "graph_traverse": Tool(
        name="graph_traverse",
        description="[Pillar 5] Graph RAG. Find the shortest JOIN path between two SAP tables "
                    "using the NetworkX Foreign Key graph. Returns formatted SQL JOIN clause.",
        input_schema={
            "type": "object",
            "properties": {
                "start_table": {"type": "string", "description": "Starting table (e.g., LFA1)"},
                "end_table": {"type": "string", "description": "Target table (e.g., MARA)"},
                "format": {"type": "string", "enum": ["join", "path", "json"], "description": "Output format"},
            },
            "required": ["start_table", "end_table"]
        },
        execute=graph_traverse,
        pillars=["Pillar 5"],
    ),

    "sql_validate": Tool(
        name="sql_validate",
        description="[Security] Validate SAP HANA SQL for safety, syntax, and role-based access. "
                    "Checks SELECT-only, MANDT filter, denied tables, and suggests AuthContext WHERE clauses.",
        input_schema={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL query to validate"},
                "strict": {"type": "boolean", "description": "Treat warnings as errors"},
            },
            "required": ["sql"]
        },
        execute=sql_validate,
        pillars=["Security"],
    ),

    "sql_execute": Tool(
        name="sql_execute",
        description="[Execution] Execute validated SAP HANA SQL against mock or real database. "
                    "Returns row set with role-based masking applied.",
        input_schema={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SELECT statement to execute"},
                "dry_run": {"type": "boolean", "description": "Validate only, no real execution"},
                "max_rows": {"type": "integer", "description": "Row limit (default: 1000)"},
            },
            "required": ["sql"]
        },
        execute=sql_execute,
        pillars=["Execution"],
    ),

    "result_mask": Tool(
        name="result_mask",
        description="[Pillar 1] Apply role-based column masking to a result set. "
                    "Redacts sensitive fields (BANKN, STCD1, etc.) based on user role.",
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "array", "description": "List of row dictionaries to mask"},
            },
            "required": ["data"]
        },
        execute=result_mask,
        pillars=["Pillar 1"],
    ),

    "meta_path_match": Tool(
        name="meta_path_match",
        description="[Pillar 5] Checks the Meta-Path library for an exact semantic match. "
                    "Bypasses dynamic traversal if a pre-computed JOIN template exists.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "User question"},
                "domain": {"type": "string"},
            },
            "required": ["query"]
        },
        execute=meta_path_match,
        pillars=["Pillar 5"],
    ),

    "all_paths_explore": Tool(
        name="all_paths_explore",
        description="[Pillar 5] Finds ALL valid JOIN paths between two tables, scored and ranked "
                    "by cardinality and module transits.",
        input_schema={
            "type": "object",
            "properties": {
                "start_table": {"type": "string"},
                "end_table": {"type": "string"},
            },
            "required": ["start_table", "end_table"]
        },
        execute=all_paths_explore,
        pillars=["Pillar 5"],
    ),

    "temporal_graph_search": Tool(
        name="temporal_graph_search",
        description="[Pillar 5] Temporal-aware Graph RAG. Detects temporal anchors "
                    "(date, fiscal period, FY, Q#) and returns JOIN path "
                    "with temporal validity WHERE clauses for SAP key-date queries.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "User question containing a temporal anchor"},
                "start_table": {"type": "string", "description": "Start table for JOIN path"},
                "end_table": {"type": "string", "description": "End table for JOIN path"},
            },
            "required": ["query", "start_table", "end_table"]
        },
        execute=temporal_graph_search,
        pillars=["Pillar 5"],
    ),

    "meta_harness_propose": Tool(
        name="meta_harness_propose",
        description="[Meta-Harness] Automated Meta-Harness Loop. Reads recent HarnessRun "
                    "failures from Redis, groups by failure pattern, diagnoses root causes "
                    "via LLM, and outputs YAML recommendations for human review. "
                    "ADVISORY MODE: never auto-applies patches. "
                    "Call this tool when the orchestrator detects repeated self-heal failures "
                    "or when confidence_score drops below threshold for the same query pattern. "
                    "Parameters: days (default 7), limit (default 200).",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Look back window in days (default: 7)"},
                "limit": {"type": "integer", "description": "Max failures to collect (default: 200)"},
            },
            "required": []
        },
        execute=meta_harness_propose,
        pillars=["Meta-Harness"],
    ),
}


def get_tool(name: str) -> Optional[Tool]:
    """Get a tool by name from the registry."""
    return TOOL_REGISTRY.get(name)


def get_tools_by_pillar(pillar: str) -> List[Tool]:
    """Get all tools belonging to a specific pillar."""
    return [t for t in TOOL_REGISTRY.values() if pillar in t.pillars]


def list_tools() -> List[Dict[str, Any]]:
    """List all available tools with their schemas for LLM consumption."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
            "pillars": t.pillars,
        }
        for t in TOOL_REGISTRY.values()
    ]


# =============================================================================
# Tool Call Interface — Used by Orchestrator
# =============================================================================

def call_tool(
    tool_name: str,
    params: Dict[str, Any],
    auth_context=None,
) -> ToolResult:
    """
    Call a tool by name with parameters and optional auth context.
    This is the single entry point used by the orchestrator agent loop.
    """
    tool = get_tool(tool_name)
    if not tool:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Unknown tool: {tool_name}",
            metadata={"available_tools": list(TOOL_REGISTRY.keys())}
        )

    # Inject auth_context if the tool accepts it
    if "auth_context" in tool.input_schema.get("properties", {}):
        params["auth_context"] = auth_context

    try:
        result = tool.execute(**params)
        if isinstance(result, ToolResult):
            return result
        else:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f"Tool {tool_name} returned unexpected type: {type(result)}",
                metadata={}
            )
    except Exception as e:
        return ToolResult(
            status=ToolStatus.ERROR,
            message=f"Tool {tool_name} raised exception: {str(e)}",
            metadata={"params": {k: str(v)[:50] for k, v in params.items()}}
        )
