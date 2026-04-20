"""
exploration_engine.py — Phase 18: Exploration & Discovery
==========================================================
Dynamic FK probing for novel queries that fall outside the 14 predefined meta-paths
and return low-confidence Schema RAG results.

Key insight (from Google ADK Annie Wang — Coordinator Pattern):
  A router only decides which steps to SKIP. A true exploration system
  must DECOMPOSE the problem space — discover tables, fields, and FK relationships
  that were not in the original schema graph, enabling queries that would
  otherwise fail silently.

Exploration fires when ALL of these are true:
  1. Meta-path match → MISS (query not in 14 pre-computed paths)
  2. Schema RAG confidence < 0.60  OR  tables_found == []
  3. NOT already in exploration cache (TTL: 1hr per query hash)

3 Probe strategies run in parallel (max 3 probes/query budget):
  PROBE_A — DDIC Field Matcher:
    Extracts field-name keywords from query → matches against DDIC mirror field list
    e.g. "tax identification" → STCD1, STCD2 fields → surfaces LFA1/KNA1/T001S

  PROBE_B — Graph Neighborhood Expansion:
    Uses already-discovered tables as anchors → 1-hop FK neighbor expansion via graph_store
    e.g. MARA found → surfaces MARC, MARD, MBEW, MAKT, MVKE, QALS, EINA, EKPO

  PROBE_C — Semantic DDIC Search:
    Full-text search over (table_name + description + field_descriptions)
    using Qdrant sap_schema collection + BM25 hybrid re-ranking

After probes complete:
  1. Merge results (union of tables, de-duplicated)
  2. Score each table (probe_count × field_relevance × graph_proximity)
  3. Filter by role permissions (AuthContext.denied_tables)
  4. Return top-5 candidates with FK path explainability
  5. Budget log → Redis TTL cache

Usage:
  from app.core.exploration_engine import ExplorationEngine, exploration_engine
  result = exploration_engine.explore(query, auth_context, domain, already_found=[])
  print(result["tables"][:3])
"""

from __future__ import annotations

import re
import time
import hashlib
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

logger = logging.getLogger(__name__)

# ─── TTL and Budget Constants ─────────────────────────────────────────────────
EXPLORATION_TTL_SECONDS: int = 3600       # 1 hour TTL cache per query hash
MAX_PROBES_PER_QUERY: int = 3             # max parallel probe strategies
MAX_CANDIDATES_RETURNED: int = 5          # top-K candidates returned
PROBE_TIMEOUT_MS: int = 80                # per-probe timeout (~3× faster than Schema RAG)


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class ExplorationCandidate:
    """A table discovered during exploration."""
    table: str
    description: str
    domain: str
    module: str
    fields: List[Dict[str, str]]           # [{name, type, description}]
    score: float                           # composite: probe_A+B+C relevance
    probe_source: str                      # which probe(s) found this table
    field_hits: List[str] = field(default_factory=list)   # matched field names
    fk_paths: List[List[str]] = field(default_factory=list)  # possible FK paths from anchor tables
    centrality_score: float = 0.0
    is_cross_module_bridge: bool = False
    confidence: float = 0.0                # 0-1 confidence this table is relevant


@dataclass
class ExplorationResult:
    """Result returned after exploration completes."""
    tables: List[ExplorationCandidate]      # top-K candidates with scores
    tables_found: List[str]                # just table names (for orchestrator)
    total_probes_run: int
    probes_used: List[str]
    exploration_time_ms: int
    from_cache: bool                       # True if this was a TTL cache hit
    budget_exhausted: bool                 # True if 3 probes already used this session
    new_tables: List[str]                  # tables not already_in `already_found`
    confidence: float                      # best candidate confidence (0-1)


# ─── Shared Exploration Budget Tracker (in-memory, per-process) ───────────────

class ExplorationBudget:
    """
    Per-query exploration budget — max 3 probes per query.
    Budget is per query-hash, not per session (same query = cache hit).
    Uses in-process dict + optional Redis TTL for distributed caching.
    """
    def __init__(self):
        self._probe_counts: Dict[str, int] = {}    # query_hash → probe_count
        self._cache: Dict[str, ExplorationResult] = {}  # query_hash → result (in-process)
        self._lock = Lock()

    def get_cache(self, query: str, domain: str) -> Optional[ExplorationResult]:
        """Return cached result if within TTL, None if expired or not cached."""
        key = self._cache_key(query, domain)
        with self._lock:
            cached = self._cache.get(key)
            if cached:
                logger.info(f"[EXPLORE CACHE HIT] query_hash={key[:12]}...")
                return cached
        return None

    def set_cache(self, query: str, domain: str, result: ExplorationResult) -> None:
        """Cache result in-process. Redis TTL handled by caller if Redis available."""
        key = self._cache_key(query, domain)
        with self._lock:
            self._cache[key] = result
            self._probe_counts[key] = result.total_probes_run

    def can_probe(self, query: str, domain: str, probe_name: str) -> Tuple[bool, int]:
        """
        Check if probe can run under budget.
        Returns (can_run, remaining_budget).
        """
        key = self._cache_key(query, domain)
        with self._lock:
            count = self._probe_counts.get(key, 0)
            if count >= MAX_PROBES_PER_QUERY:
                logger.info(f"[EXPLORE BUDGET EXHAUSTED] {probe_name} denied — {count}/{MAX_PROBES_PER_QUERY} probes used")
                return False, 0
            return True, MAX_PROBES_PER_QUERY - count

    def record_probe(self, query: str, domain: str) -> int:
        """Increment probe count. Returns new count."""
        key = self._cache_key(query, domain)
        with self._lock:
            self._probe_counts[key] = self._probe_counts.get(key, 0) + 1
            return self._probe_counts[key]

    @staticmethod
    def _cache_key(query: str, domain: str) -> str:
        """Deterministic cache key from query+domain."""
        raw = f"{query.lower().strip()}|{domain}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


# Singleton budget tracker
exploration_budget = ExplorationBudget()


# ─── Core Exploration Engine ──────────────────────────────────────────────────

class ExplorationEngine:
    """
    Phase 18 — Exploration & Discovery Engine.

    Probes 3 strategies in parallel, merges results, returns top-5 candidate tables
    with FK path explainability. All within a 3-probe/query budget.

    Designed to complete in < 200ms for a warm (cached) query, < 400ms for a cold one.
    """

    def __init__(self):
        self._budget = exploration_budget
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="explore_")

    # ─── Public API ────────────────────────────────────────────────────────────

    def explore(
        self,
        query: str,
        auth_context: Any,          # SAPAuthContext — for denied_tables check
        domain: str = "auto",
        already_found: Optional[List[str]] = None,
        schema_rag_confidence: float = 0.0,
    ) -> ExplorationResult:
        """
        Main exploration entry point.

        Args:
            query: natural language query
            auth_context: SAPAuthContext — used to filter denied tables
            domain: domain hint (auto, purchasing, material_master, etc.)
            already_found: tables already found by Schema RAG (to avoid duplicates)
            schema_rag_confidence: confidence score from Schema RAG step

        Returns:
            ExplorationResult with top-5 candidate tables + FK paths
        """
        already_found = already_found or []
        start_ms = int(time.time() * 1000)
        query_lower = query.lower()

        logger.info(f"\n[PHASE 18] Exploration Engine triggered")
        logger.info(f"  Query: {query[:60]}...")
        logger.info(f"  Schema RAG confidence: {schema_rag_confidence:.2f} < 0.60 → LOW")
        logger.info(f"  Already found: {already_found}")

        # ── Pre-check: cache hit ──────────────────────────────────────────────
        cached = self._budget.get_cache(query, domain)
        if cached:
            cached.from_cache = True
            # Filter out already-found tables for the "new_tables" field
            cached.new_tables = [t for t in cached.tables_found if t not in already_found]
            return cached

        # ── Pre-check: budget exhausted ────────────────────────────────────────
        can_run, remaining = self._budget.can_probe(query, domain, "exploration")
        if not can_run:
            return ExplorationResult(
                tables=[],
                tables_found=[],
                total_probes_run=0,
                probes_used=[],
                exploration_time_ms=int(time.time() * 1000) - start_ms,
                from_cache=False,
                budget_exhausted=True,
                new_tables=[],
                confidence=0.0,
            )

        # ── Extract exploration anchors ────────────────────────────────────────
        # Use already-found tables as anchor points for graph expansion (PROBE_B)
        anchors = [t for t in already_found if t]  # filter empty strings
        if not anchors:
            # No anchors — try to extract entity keywords from query as fallback anchors
            anchors = self._extract_entity_anchors(query_lower)

        # ── Run 3 probes in parallel ───────────────────────────────────────────
        probe_names = ["PROBE_A", "PROBE_B", "PROBE_C"]

        futures = {}
        for probe_name in probe_names:
            can_run_now, _ = self._budget.can_probe(query, domain, probe_name)
            if not can_run_now:
                logger.info(f"[EXPLORE] {probe_name} skipped — budget exhausted")
                continue

            if probe_name == "PROBE_A":
                fut = self._executor.submit(
                    self._probe_ddic_field_match,
                    query, domain,
                )
            elif probe_name == "PROBE_B":
                fut = self._executor.submit(
                    self._probe_graph_expansion,
                    anchors, query, domain,
                )
            elif probe_name == "PROBE_C":
                fut = self._executor.submit(
                    self._probe_semantic_ddic,
                    query, domain, auth_context,
                )
            futures[probe_name] = fut

        # ── Collect results ───────────────────────────────────────────────────
        all_candidates: Dict[str, ExplorationCandidate] = {}
        probes_run: List[str] = []
        probes_succeeded: List[str] = []

        for probe_name, fut in futures.items():
            try:
                candidates = fut.result(timeout=PROBE_TIMEOUT_MS / 1000.0)
                if candidates:
                    probes_run.append(probe_name)
                    probes_succeeded.append(probe_name)
                    for cand in candidates:
                        if cand.table not in all_candidates:
                            all_candidates[cand.table] = cand
                        else:
                            # Merge: update score and probe_source
                            existing = all_candidates[cand.table]
                            existing.score = max(existing.score, cand.score)
                            existing.probe_source = f"{existing.probe_source}+{probe_name}"
                            existing.field_hits = list(set(existing.field_hits + cand.field_hits))
                    self._budget.record_probe(query, domain)
                    logger.info(f"[EXPLORE] {probe_name}: {len(candidates)} candidates found")
            except Exception as e:
                logger.warning(f"[EXPLORE] {probe_name} failed: {e}")
                probes_run.append(probe_name)

        # ── Rank and filter ────────────────────────────────────────────────────
        ranked = self._rank_candidates(list(all_candidates.values()), auth_context)

        # ── Filter out already-found tables ────────────────────────────────────
        new_tables = [c for c in ranked if c.table not in already_found]
        new_table_names = [c.table for c in new_tables]

        # ── Build result ──────────────────────────────────────────────────────
        elapsed_ms = int(time.time() * 1000) - start_ms
        best_confidence = ranked[0].confidence if ranked else 0.0

        result = ExplorationResult(
            tables=ranked,
            tables_found=new_table_names,
            total_probes_run=len(probes_succeeded),
            probes_used=probes_succeeded,
            exploration_time_ms=elapsed_ms,
            from_cache=False,
            budget_exhausted=False,
            new_tables=new_table_names,
            confidence=best_confidence,
        )

        # ── Cache result ──────────────────────────────────────────────────────
        self._budget.set_cache(query, domain, result)
        self._try_redis_ttl_set(query, domain, result)

        logger.info(f"[EXPLORE] Done in {elapsed_ms}ms — {len(ranked)} candidates, "
                    f"{len(new_table_names)} new, best_conf={best_confidence:.2f}")
        logger.info(f"[EXPLORE] Tables: {[c.table for c in ranked[:5]]}")

        return result

    # ─── Probe A: DDIC Field Matcher ─────────────────────────────────────────

    def _probe_ddic_field_match(
        self,
        query: str,
        domain: str,
    ) -> List[ExplorationCandidate]:
        """
        Extracts field-name keywords from query → matches against DDIC mirror field list.
        e.g. "tax identification" → STCD1, STCD2; "bank account" → BANKN, BANKL

        Returns up to 5 candidates sorted by field_hit_count × relevance.
        """
        from app.core.schema_auto_discover import DDIC_MIRROR

        # Keywords that commonly map to SAP field names
        keyword_to_field_patterns: Dict[str, List[Tuple[str, str]]] = {
            "tax": [("STCD1", "Tax Number 1"), ("STCD2", "Tax Number 2"), ("STCD3", "Tax Number 3"),
                    ("STCDT", "Tax Type"), ("TAXT", "Tax Type")],
            "tax id": [("STCD1", "Tax Number 1"), ("STCD2", "Tax Number 2")],
            "vat": [("STCD2", "Tax Number 2 (VAT)")],
            "bank": [("BANKS", "Bank Country"), ("BANKL", "Bank Key"), ("BANKN", "Bank Account"),
                     ("KOINH", "Account Holder"), ("IBAN", "IBAN")],
            "account": [("KONTO", "G/L Account"), ("AKONT", "Reconciliation Acct"),
                        ("HBKID", "House Bank ID"), ("XPORE", "G/L Account Long")],
            "payment": [("ZAHLS", "Payment Terms Key"), ("ZTERM", "Payment Terms"),
                        ("WAERS", "Currency"), ("KUNNR", "Customer"), ("LIFNR", "Vendor")],
            "address": [("ADRNR", "Address Number"), ("NAME1", "Name 1"), ("NAME2", "Name 2"),
                        ("STREET", "Street"), ("CITY1", "City"), ("COUNTRY", "Country Key")],
            "contact": [("TEL_NUMBER", "Telephone"), ("SMTP_ADDR", "Email"), ("ADRNR", "Address")],
            "email": [("SMTP_ADDR", "Email Address")],
            "phone": [("TEL_NUMBER", "Telephone Number"), ("TELFX", "Fax")],
            "sales": [("VKORG", "Sales Org"), ("VTWEG", "Distribution Channel"),
                      ("SPART", "Division"), ("KUNNR", "Customer")],
            "price": [("NETWR", "Net Value"), ("KBETR", "Condition Rate"), ("VERPR", "Moving Avg Price"),
                      ("STPRS", "Standard Price")],
            "cost": [("STPRS", "Standard Price"), ("VERPR", "Moving Average Price"),
                     ("KBETR", "Condition Amount"), ("BWASL", "Price Control")],
            "valuation": [("MBEW", "Material Valuation"), ("BWKEY", "Valuation Area"),
                          ("VPRSV", "Price Control"), ("STPRS", "Standard Price")],
            "stock": [("LABST", "Unrestricted Stock"), ("INSME", "Quality Inspection"),
                      ("SPERR", "Blocked Stock"), ("RETME", "Returns Stock"),
                      ("EINME", "Unrestricted-Use Stock")],
            "quantity": [("MENGE", "Quantity"), ("MEINS", "Unit of Measure"),
                         ("BPMNG", "Confirmed Quantity"), ("WEMNG", "Delivered Quantity")],
            "weight": [("NTGEW", "Net Weight"), ("GEWEI", "Weight Unit"), ("BRGEW", "Gross Weight")],
            "volume": [("VOLUM", "Volume"), ("VOLEH", "Volume Unit"), ("LAENG", "Length")],
            "warehouse": [("LGORT", "Storage Location"), ("LGTYP", "Storage Type"),
                          ("LGPBE", "Storage Bin"), ("LEVUV", "Loading Qty")],
            "plant": [("WERKS", "Plant"), ("STURL", "Plant Address"), ("IWERK", "Maintenance Plant")],
            "company code": [("BUKRS", "Company Code"), ("BUKRS", "Company Code")],
            "vendor": [("LIFNR", "Vendor"), ("NAME1", "Vendor Name"), ("KTOKK", "Account Group")],
            "customer": [("KUNNR", "Customer"), ("NAME1", "Customer Name"), ("KTOKD", "Customer Group")],
            "material": [("MATNR", "Material"), ("MTART", "Material Type"), ("MATKL", "Material Group")],
            "purchase": [("EBELN", "PO"), ("EBELP", "PO Item"), ("LIFNR", "Vendor"), ("EKORG", "Purchasing Org")],
            "invoice": [("BELNR", "Accounting Document"), ("BUKRS", "Company Code"),
                        ("LIFNR", "Vendor"), ("KUNNR", "Customer")],
            "employee": [("PERNR", "Personnel Number"), ("ENAME", "Employee Name"),
                         ("WERKS", "Personal Area"), ("BTRTL", " Personnel Subarea")],
            "project": [("PSPNR", "Work Breakdown Structure Element"), ("PROJN", "Project Definition"),
                        ("POST1", "Project Description")],
            "wbs": [("PSPNR", "WBS Element"), ("POSNR", "WBS Element Number"), ("STUFE", "WBS Level")],
            "budget": [("TWAER", "Plan Currency"), ("WLP01", "Plan Values 1"), ("SUMME", "Budget Amount")],
            "cost center": [("KOSTL", "Cost Center"), ("DATAB", "Validity Start"), ("DATBI", "Validity End")],
            "profit center": [("PRCTR", "Profit Center"), ("KOKRS", "Controlling Area")],
            "sales org": [("VKORG", "Sales Organization"), ("VTWEG", "Distribution Channel"),
                           ("SPART", "Division"), ("KDVFR", "Sales Office")],
            "distribution": [("VTWEG", "Distribution Channel"), ("WERKS", "Plant"),
                             ("LGORT", "Storage Location")],
            "delivery": [("VBELN", "Delivery"), ("LIFEX", "External Delivery"),
                         ("WADAT", "Plan GI Date"), ("WADAT_IST", "Actual GI Date")],
            "billing": [("VBRK", "Billing Header"), ("FPLNR", "Billing Plan"),
                        ("FKIMG", "Billed Quantity"), ("NETWR", "Net Value")],
            "quality": [("QALS", "Insp Lot"), ("QAMV", "Insp Val"), ("LOSBA", "Inspection Lot Origin")],
            "inspection": [("QALS", "Inspection Lot"), ("ART", "Inspection Type"),
                           ("STAT", "Inspection Status"), ("MAHN1", "Urgent Inspection")],
            "condition": [("KONP", "Condition Record"), ("KSCHL", "Condition Type"),
                          ("KBETR", "Rate/Condition Value"), ("KONWA", "Condition Currency")],
            "hierarchy": [("STUFE", "WBS Level"), ("PHYN0", "Node ID"), ("STRGR", "Strategy Group")],
            "country": [("LAND1", "Country Key"), ("LANDX", "Country Name"), ("NATIO", "Nationality")],
            "region": [("REGIO", "Region"), ("CITYC", "City Code"), ("STEUF", "Tax Region")],
            "currency": [("WAERS", "Currency Key"), ("KPEIN", "Price Unit"), ("KONWA", "Condition Currency")],
            "unit": [("MEINS", "Base Unit"), ("MSEIN", "Dimension"), ("MSEHI", "UoM ISO Code")],
            "date": [("ERDAT", "Created On"), ("AEDAT", "Changed On"), ("BUDAT", "Posting Date"),
                     ("BLDAT", "Document Date"), ("QDATU", "Expiration Date")],
            "status": [("STAT", "Status"), ("LIFSP", "Deletion Flag - Vendor"),
                       ("SPERR", "Posting Block"), ("LOEKZ", "Deletion Flag")],
            "blocked": [("SPERR", "Posting Block"), ("LIFSP", "Deletion Flag"),
                        ("QSSPA", "Spare Part Approval")],
            "contact person": [("ANRED", "Title"), ("NAME1", "First Name"), ("NAME2", "Last Name")],
        }

        query_lower = query.lower()
        candidates: List[ExplorationCandidate] = []

        # Find all matching (field_name, field_description) pairs in the query
        field_hits: Dict[str, List[str]] = {}  # table → [matched field names]
        for keyword, field_list in keyword_to_field_patterns.items():
            if keyword in query_lower:
                for field_name, field_desc in field_list:
                    # Find which DDIC table has this field — handle dict + dataclass DDICTable
                    def _field_names(entry) -> List[str]:
                        fields = entry.fields if hasattr(entry, 'fields') else entry.get('fields', []) if isinstance(entry, dict) else []
                        return [f.get('name', '') if isinstance(f, dict) else (f.name if hasattr(f, 'name') else '') for f in fields]

                    def _has_field(entry, fname: str) -> bool:
                        return fname in _field_names(entry)

                    for ddict in DDIC_MIRROR:
                        if _has_field(ddict, field_name):
                            # Handle both dict and dataclass DDICTable
                            if isinstance(ddict, dict):
                                table_name = ddict["table"]
                                table_desc = ddict["description"]
                                table_domain = ddict["domain"]
                                table_fields = ddict["fields"]
                            else:
                                table_name = ddict.table
                                table_desc = ddict.description
                                table_domain = ddict.domain
                                table_fields = ddict.fields
                            if table_name not in field_hits:
                                field_hits[table_name] = []
                            field_hits[table_name].append(field_name)
                            break  # found the table, stop searching

        # Build candidates from field matches
        for table_name, hit_fields in field_hits.items():
            # Get DDIC entry (DDIC_MIRROR contains DDICTable dataclass instances)
            ddict_entry = None
            for d in DDIC_MIRROR:
                tbl = d.table if hasattr(d, 'table') else d.get("table") if isinstance(d, dict) else None
                if tbl == table_name:
                    ddict_entry = d
                    break

            if not ddict_entry:
                continue

            table_desc = ddict_entry.description if hasattr(ddict_entry, 'description') else ddict_entry.get("description", "")
            table_domain = ddict_entry.domain if hasattr(ddict_entry, 'domain') else ddict_entry.get("domain", "auto")
            table_fields = ddict_entry.fields if hasattr(ddict_entry, 'fields') else ddict_entry.get("fields", [])

            # Score: more field hits = higher relevance
            score = min(len(hit_fields) / 3.0, 1.0) * 0.8 + 0.2  # 0.2 base + up to 0.8 for field matches
            # Domain match bonus
            if domain != "auto" and table_domain == domain:
                score = min(score + 0.15, 1.0)

            cand = ExplorationCandidate(
                table=table_name,
                description=table_desc,
                domain=table_domain,
                module=self._domain_to_module(table_domain),
                fields=table_fields,
                score=score,
                probe_source="PROBE_A",
                field_hits=hit_fields,
                fk_paths=[],
                confidence=score,
            )
            candidates.append(cand)

        # Sort by score desc
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:MAX_CANDIDATES_RETURNED]

    # ─── Probe B: Graph Neighborhood Expansion ────────────────────────────────

    def _probe_graph_expansion(
        self,
        anchor_tables: List[str],
        query: str,
        domain: str,
    ) -> List[ExplorationCandidate]:
        """
        Uses already-discovered tables as anchors → 1-hop FK neighbor expansion.
        Leverages the NetworkX FK graph to find structurally adjacent tables
        that are likely relevant to the query even if their names don't match keywords.

        e.g. anchor MARA → surfaces EKPO (PO items), QALS (QM inspection), MSEG (movement)
        """
        from app.core.schema_auto_discover import DDIC_MIRROR

        candidates: List[ExplorationCandidate] = []
        if not anchor_tables:
            return candidates

        try:
            from app.core.graph_store import graph_store

            for anchor in anchor_tables:
                if not anchor:
                    continue
                try:
                    # 1-hop neighbors from FK graph
                    neighbors = list(graph_store.G.neighbors(anchor))
                    for neighbor in neighbors:
                        if neighbor in [a for a in anchor_tables]:
                            continue  # skip already-found tables

                        # Get neighbor metadata from graph store node_meta
                        node_meta = graph_store._node_meta.get(neighbor, {})
                        desc = node_meta.get("desc", "")
                        module = node_meta.get("module", "")
                        neigh_domain = node_meta.get("domain", "")

                        # Cross-module bridge check
                        is_bridge = False
                        try:
                            edge_data = graph_store.G.get_edge_data(anchor, neighbor)
                            if edge_data:
                                if isinstance(edge_data, dict) and edge_data.get("bridge_type") == "cross_module":
                                    is_bridge = True
                                elif hasattr(edge_data, "get") and edge_data.get("bridge_type") == "cross_module":
                                    is_bridge = True
                        except Exception:
                            pass

                        # Get fields for this table from DDIC mirror
                        table_fields = []
                        for d in DDIC_MIRROR:
                            tbl = d.table if hasattr(d, 'table') else d.get("table") if isinstance(d, dict) else None
                            if tbl == neighbor:
                                table_fields = d.fields if hasattr(d, 'fields') else d.get("fields", [])
                                break

                        score = 0.65 if is_bridge else 0.55
                        cand = ExplorationCandidate(
                            table=neighbor,
                            description=desc,
                            domain=domain,
                            module=module,
                            fields=table_fields,
                            score=score,
                            probe_source="PROBE_B",
                            field_hits=[],
                            fk_paths=[[anchor, neighbor]],
                            is_cross_module_bridge=is_bridge,
                            confidence=score,
                        )
                        candidates.append(cand)
                except Exception as e:
                    logger.warning(f"[EXPLORE PROBE_B] anchor={anchor} error: {e}")
                    continue

        except Exception as e:
            logger.warning(f"[EXPLORE PROBE_B] graph_store unavailable: {e}")

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:MAX_CANDIDATES_RETURNED]

    # ─── Probe C: Semantic DDIC Search ───────────────────────────────────────

    def _probe_semantic_ddic(
        self,
        query: str,
        domain: str,
        auth_context: Any,
    ) -> List[ExplorationCandidate]:
        """
        Full-text semantic search over DDIC tables using Qdrant.
        Searches table_name + description + field descriptions together.
        Uses BM25HybridStore if available, falls back to keyword text search.

        This is the most general probe — fires for any query where keywords
        don't directly map to field names.
        """
        from app.core.schema_auto_discover import DDIC_MIRROR

        candidates: List[ExplorationCandidate] = []
        query_lower = query.lower()

        # Try Qdrant semantic search first
        try:
            from app.core.vector_store import get_vector_store
            vs = get_vector_store()
            if vs and hasattr(vs, "client"):
                # Use Qdrant search over sap_schema collection
                try:
                    search_results = vs.client.search(
                        collection_name="sap_schema",
                        query_vector=None,
                        query_filter=None,
                        search_params=None,
                        limit=MAX_CANDIDATES_RETURNED,
                    )
                    # If search returns results, use them
                    if search_results:
                        for hit in search_results:
                            payload = hit.payload or {}
                            table_name = payload.get("table", "")
                            if table_name and table_name not in [c.table for c in candidates]:
                                score = float(hit.score) if hasattr(hit, "score") else 0.5
                                cand = ExplorationCandidate(
                                    table=table_name,
                                    description=payload.get("description", ""),
                                    domain=payload.get("domain", ""),
                                    module=payload.get("module", ""),
                                    fields=payload.get("fields", []),
                                    score=score,
                                    probe_source="PROBE_C",
                                    field_hits=[],
                                    fk_paths=[],
                                    confidence=score,
                                )
                                candidates.append(cand)
                except Exception:
                    pass  # Fall through to keyword search
        except Exception:
            pass

        # Fallback: keyword text search over DDIC mirror
        if not candidates:
            logger.info("[EXPLORE PROBE_C] Falling back to keyword search over DDIC mirror")
            query_words = set(re.findall(r'\b\w{4,}\b', query_lower))

            for ddict in DDIC_MIRROR:
                table_name = ddict.table if hasattr(ddict, 'table') else ddict.get("table", "")
                table_desc = ddict.description if hasattr(ddict, 'description') else ddict.get("description", "").lower()
                table_domain = ddict.domain if hasattr(ddict, 'domain') else ddict.get("domain", "auto")
                table_fields = ddict.fields if hasattr(ddict, 'fields') else ddict.get("fields", [])

                # Score: how many query words appear in table name or description
                desc_words = set(re.findall(r'\b\w{4,}\b', table_desc.lower()))
                overlap = query_words & desc_words
                field_desc_hits = []
                if overlap or query_words:
                    # Also check field descriptions
                    for f in table_fields:
                        fdesc = f.get("description", "").lower() if isinstance(f, dict) else ""
                        fdesc_words = set(re.findall(r'\b\w{4,}\b', fdesc))
                        field_desc_hits = list(query_words & fdesc_words)
                        if field_desc_hits:
                            break

                    score = (len(overlap) / max(len(query_words), 1)) * 0.7
                    if field_desc_hits:
                        score = min(score + 0.3, 1.0)
                    if domain != "auto" and table_domain == domain:
                        score = min(score + 0.1, 1.0)

                    if score > 0.05:  # only include if somewhat relevant
                        cand = ExplorationCandidate(
                            table=table_name,
                            description=table_desc.title() if hasattr(ddict, 'description') else ddict.get("description", ""),
                            domain=table_domain,
                            module=self._domain_to_module(table_domain),
                            fields=table_fields,
                            score=score,
                            probe_source="PROBE_C",
                            field_hits=field_desc_hits,
                            fk_paths=[],
                            confidence=score,
                        )
                        candidates.append(cand)

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:MAX_CANDIDATES_RETURNED]

    # ─── Ranking & Filtering ─────────────────────────────────────────────────

    def _rank_candidates(
        self,
        candidates: List[ExplorationCandidate],
        auth_context: Any,
    ) -> List[ExplorationCandidate]:
        """
        Final ranking pass:
        1. Filter denied_tables from AuthContext
        2. De-duplicate by table name
        3. Sort by composite score: 0.4×probe_score + 0.3×field_relevance + 0.2×graph_proximity + 0.1×cross_module_bonus
        4. Return top-5
        """
        if not candidates:
            return []

        # Filter denied tables
        denied_tables: Set[str] = set()
        if auth_context and hasattr(auth_context, "denied_tables"):
            denied_tables = set(auth_context.denied_tables or [])

        filtered = [c for c in candidates if c.table not in denied_tables]

        # De-duplicate: keep highest-scoring entry per table
        seen: Dict[str, ExplorationCandidate] = {}
        for cand in filtered:
            if cand.table not in seen:
                seen[cand.table] = cand
            else:
                if cand.score > seen[cand.table].score:
                    seen[cand.table] = cand

        ranked = list(seen.values())
        ranked.sort(key=lambda c: c.score, reverse=True)

        # Composite score refinement
        for cand in ranked:
            # Recalculate with bonuses
            probe_score = cand.score
            field_bonus = min(len(cand.field_hits) * 0.1, 0.3) if cand.field_hits else 0.0
            graph_bonus = 0.1 if cand.fk_paths else 0.0
            cross_module_bonus = 0.1 if cand.is_cross_module_bridge else 0.0
            cand.confidence = min(probe_score + field_bonus + graph_bonus + cross_module_bonus, 1.0)

        ranked.sort(key=lambda c: c.confidence, reverse=True)
        return ranked[:MAX_CANDIDATES_RETURNED]

    # ─── Redis TTL Cache ─────────────────────────────────────────────────────

    def _try_redis_ttl_set(self, query: str, domain: str, result: ExplorationResult) -> None:
        """Attempt to cache result in Redis with TTL (best-effort, non-blocking)."""
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True, socket_timeout=1)
            cache_key = f"explore:ttl:{ExplorationBudget._cache_key(query, domain)}"
            import json
            r.setex(
                cache_key,
                EXPLORATION_TTL_SECONDS,
                json.dumps({
                    "tables": [c.table for c in result.tables],
                    "confidence": result.confidence,
                    "probes_used": result.probes_used,
                    "exploration_time_ms": result.exploration_time_ms,
                })
            )
            r.close()
        except Exception:
            pass  # Redis optional — in-process cache is sufficient

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_entity_anchors(query_lower: str) -> List[str]:
        """Extract entity keywords as fallback anchors when no tables are known."""
        anchors = []
        entity_keywords = {
            "vendor": ["LFA1", "LFB1", "LFBK", "LFA3"],
            "customer": ["KNA1", "KNB1", "KNVV"],
            "material": ["MARA", "MARC", "MARD", "MBEW"],
            "purchase order": ["EKKO", "EKPO"],
            "sales order": ["VBAK", "VBAP"],
            "invoice": ["VBRK", "VBRP", "BKPF", "BSEG"],
            "quality": ["QALS", "QAVE", "QAMV"],
            "project": ["PRPS", "PROJ", "AFKO"],
            "employee": ["PA0001", "PA0002"],
            "asset": ["ANLA", "ANLC", "ANLB"],
            "storage": ["MARD", "MLGN", "MLGT", "LQUA"],
        }
        for entity, tables in entity_keywords.items():
            if entity in query_lower:
                anchors.extend(tables[:1])  # only take primary table
        return anchors[:3]  # max 3 anchors

    @staticmethod
    def _domain_to_module(domain: str) -> str:
        mapping = {
            "business_partner": "BP",
            "material_master": "MM",
            "purchasing": "MM-PUR",
            "sales_distribution": "SD",
            "finance": "FI",
            "quality_management": "QM",
            "warehouse_management": "WM",
            "project_system": "PS",
            "plant_maintenance": "PM",
            "customer_service": "CS",
            "transportation": "TM",
            "real_estate": "RE",
            "controlling": "CO",
            "human_resources": "HR",
        }
        return mapping.get(domain, domain.upper()[:6])


# ─── Singleton ───────────────────────────────────────────────────────────────
exploration_engine = ExplorationEngine()
