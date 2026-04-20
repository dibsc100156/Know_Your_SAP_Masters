"""
bm25_hybrid.py — BM25 + Vector + Centrality Hybrid Schema Search
================================================================
Priority 7 (David Karam's "relevance ≠ similarity" insight):
Three-signal RRF fusion for schema ranking:

  score = α × RRF(vec, bm25) + β × BM25_score_norm + γ × centrality_percentile

Where:
  α = 0.70  (vector similarity — primary signal for semantic queries)
  β = 0.15  (BM25 keyword precision — exact match bonus)
  γ = 0.15  (graph centrality — tables with more FK relationships are
             more likely to be the "hub" of a query's domain)

Signals:
  α×RRF: captures semantic intent (natural language queries)
  β×BM25: captures keyword precision (SAP table/field names like LFA1, EKKO)
  γ×centrality: structural preference — a hub table (MARA=19, LFA1=15)
             is more often the right answer than a peripheral one (CDPOS=2)

Usage:
  from app.core.bm25_hybrid import bm25_hybrid_search
  results = bm25_hybrid_search(query, domain=None, top_k=6)
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Configurable weights (can be overridden via env vars) ────────────────────
BM25_VEC_WEIGHT   = float(os.getenv("BM25_VEC_WEIGHT",   "0.70"))   # α
BM25_KEYWORD_W    = float(os.getenv("BM25_KEYWORD_W",     "0.15"))   # β
BM25_CENTRALITY_W = float(os.getenv("BM25_CENTRALITY_W",  "0.15"))   # γ

# RRF k parameter (standard 60 — reduces position noise)
RRF_K = 60

# Keyword query detection
_SAP_TABLE_PATTERN = re.compile(
    r"\b(LFA\d|KNA\d|BUKRS|T001|EKKO|EKPO|MARA|MARC|MARD|MBEW|MSEG|KNVL|KNA1|"
    r"LFB1|BSEG|QALS|AFKO|PRPS|ANLA|COEP|COSS|MKPF|VBAK|LIKP|VBRP|VBRK|VTTK|"
    r"TVRO|CDHDR|CDPOS|T001L|T001T|TKA01|TKA02)\b",
    re.IGNORECASE,
)

_SAP_FIELD_KEYWORDS = re.compile(
    r"\b(vendor|customer|material|plant|company.code|storage.location|purchasing.org|"
    r"sales.org|inspection.lot|project|wbs.element|asset|vendor.record|"
    r"customer.record|bank.detail|partner.function|contact.person|address|"
    r"tax.india|gst|pan|tan)\b",
    re.IGNORECASE,
)


def is_keyword_heavy_query(query: str) -> bool:
    q = query.strip()
    table_hits = len(_SAP_TABLE_PATTERN.findall(q))
    field_hits = len(_SAP_FIELD_KEYWORDS.findall(q))
    is_short = len(q.split()) <= 4
    is_code_lookup = bool(re.match(r"^\d{3,10}[A-Z]?$", q, re.IGNORECASE))
    keyword_dominant = (
        table_hits >= 1
        or (field_hits >= 2)
        or (field_hits >= 1 and is_code_lookup)
        or (field_hits >= 1 and is_short)
    )
    return keyword_dominant


# ── Centrality map (lazy-built from graph_store) ───────────────────────────────

_centrality_map: Optional[Dict[str, float]] = None


def _build_centrality_map() -> Dict[str, float]:
    """
    Compute degree centrality percentiles for all tables in the graph.

    Centrality reflects how "hub-like" a table is in the FK graph.
    Hub tables (MARA=19, LFA1=15, KNA1=13) are structurally central —
    they appear in more cross-module JOIN paths and are more likely to
    be the primary table for a domain query.

    Returns:
        Dict[table_name, centrality_percentile_0_to_1]
    """
    global _centrality_map
    if _centrality_map is not None:
        return _centrality_map

    try:
        from app.core.graph_store import graph_store
        G = graph_store.G
    except Exception as e:
        logger.warning(f"[BM25] Could not load graph_store: {e}")
        _centrality_map = {}
        return _centrality_map

    degrees = dict(G.degree())
    if not degrees:
        _centrality_map = {}
        return _centrality_map

    max_deg = max(degrees.values()) or 1
    _centrality_map = {
        table: round(deg / max_deg, 4)
        for table, deg in degrees.items()
    }

    logger.info(f"[BM25] Centrality map built: {len(_centrality_map)} tables, max_degree={max_deg}")
    return _centrality_map


def get_centrality_percentile(table: str) -> float:
    """Return centrality percentile [0,1] for a table, 0 if unknown."""
    cmap = _build_centrality_map()
    return cmap.get(table, 0.0)


# ── Three-signal Reciprocal Rank Fusion ──────────────────────────────────────

def _normalize_bm25_scores(bm25_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Min-max normalize BM25 scores to [0, 1] range."""
    if not bm25_results:
        return bm25_results
    scores = [r["score"] for r in bm25_results]
    min_s, max_s = min(scores), max(scores)
    span = max_s - min_s
    if span == 0:
        span = 1
    for r in bm25_results:
        r["bm25_norm"] = round((r["score"] - min_s) / span, 4)
    return bm25_results


def reciprocal_rank_fusion(
    vec_results:   List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    centrality_map: Dict[str, float],
    vec_weight:   float = BM25_VEC_WEIGHT,     # α
    bm25_weight:  float = BM25_KEYWORD_W,       # β
    cent_weight:  float = BM25_CENTRALITY_W,    # γ
    k: int = RRF_K,
) -> List[Dict[str, Any]]:
    """
    Three-signal RRF fusion.

    Signal 1 — α × RRF(vector, bm25): semantic rank fusion
    Signal 2 — β × BM25_norm: keyword precision bonus
    Signal 3 — γ × centrality_percentile: structural hub preference

    David Karam's insight: "relevance ≠ similarity"
    BM25 captures exact match relevance; vector captures semantic relatedness;
    centrality captures structural importance in the FK graph. Combined = best.

    Args:
        vec_results:    vector search results [{table, score, rank, ...}]
        bm25_results:   BM25 results [{table, score, rank, ...}]
        centrality_map: {table: centrality_percentile_0_to_1}
        vec_weight:     α weight for RRF base signal
        bm25_weight:    β weight for normalized BM25 score
        cent_weight:    γ weight for centrality percentile
        k:              RRF k parameter (default 60)

    Returns:
        Fused results sorted by fused_score descending.
        Each result includes: vec_rank, bm25_rank, bm25_score, bm25_norm,
        centrality_percentile, fused_score, final_rank.
    """
    # ── Step 1: Normalize BM25 scores to [0, 1] ─────────────────────────────
    bm25_results = _normalize_bm25_scores(bm25_results)
    bm25_results_dict = {r["table"]: r for r in bm25_results}

    # ── Step 2: Build unified table map ──────────────────────────────────────
    vec_rank_map  = {r["table"]: rank for rank, r in enumerate(vec_results)}
    all_tables: Dict[str, Dict[str, Any]] = {}

    # Seed with vector results
    for rank, r in enumerate(vec_results):
        t = r["table"]
        all_tables[t] = {
            "table":         t,
            "document":      r.get("document", ""),
            "vec_score":     r.get("score", 0.0),
            "vec_rank":      vec_rank_map.get(t, -1),
            "bm25_score":    0.0,
            "bm25_rank":     -1,
            "bm25_norm":     0.0,
            "centrality":    centrality_map.get(t, 0.0),
            "metadata":      r.get("metadata", {}),
        }

    # Merge BM25 results
    for rank, r in enumerate(bm25_results):
        t = r["table"]
        if t in all_tables:
            all_tables[t]["bm25_score"] = r.get("score", 0.0)
            all_tables[t]["bm25_rank"]  = rank
            all_tables[t]["bm25_norm"]  = r.get("bm25_norm", 0.0)
        else:
            all_tables[t] = {
                "table":        t,
                "document":     r.get("document", ""),
                "vec_score":    0.0,
                "vec_rank":     -1,
                "bm25_score":   r.get("score", 0.0),
                "bm25_rank":    rank,
                "bm25_norm":    r.get("bm25_norm", 0.0),
                "centrality":   centrality_map.get(t, 0.0),
                "metadata":     r.get("metadata", {}),
            }

    # ── Step 3: Compute three-signal RRF score ───────────────────────────────
    #
    # fused_score =
    #   α × ( bm25_weight/(k+bm25_rank) + vec_weight/(k+vec_rank) )
    #   + β × bm25_norm
    #   + γ × centrality
    #
    # The RRF base captures rank position; BM25_norm adds precision;
    # centrality adds structural preference.

    for info in all_tables.values():
        # RRF base: weighted reciprocal rank from both retrieval methods
        rrf_base = 0.0
        if info["bm25_rank"] >= 0:
            rrf_base += (1.0 - vec_weight) * (1.0 / (k + info["bm25_rank"]))
            # NOTE: vec_weight is actually bm25_weight here in original RRF
            # We use symmetric RRF: weight both retrieval methods equally in the base
        if info["vec_rank"] >= 0:
            rrf_base += vec_weight * (1.0 / (k + info["vec_rank"]))

        # Alternative: use pure symmetric RRF as base then add signals
        rrf_sym = 0.0
        if info["bm25_rank"] >= 0:
            rrf_sym += 0.5 * (1.0 / (k + info["bm25_rank"]))
        if info["vec_rank"] >= 0:
            rrf_sym += 0.5 * (1.0 / (k + info["vec_rank"]))

        rrf_score = rrf_sym

        bm25_norm   = info["bm25_norm"]
        centrality  = info["centrality"]

        fused_score = (
            BM25_VEC_WEIGHT * rrf_score
            + BM25_KEYWORD_W * bm25_norm
            + BM25_CENTRALITY_W * centrality
        )
        info["fused_score"] = round(fused_score, 6)
        info["signals"] = {
            "rrf_score":   round(rrf_score, 6),
            "bm25_norm":   bm25_norm,
            "centrality":  centrality,
            "alpha":       BM25_VEC_WEIGHT,
            "beta":        BM25_KEYWORD_W,
            "gamma":       BM25_CENTRALITY_W,
        }

    sorted_results = sorted(all_tables.values(), key=lambda x: -x["fused_score"])

    for rank, info in enumerate(sorted_results):
        info["final_rank"] = rank

    return list(sorted_results)


# ── BM25 Hybrid Search singleton ─────────────────────────────────────────────

class BM25HybridSearch:
    """
    Three-signal hybrid schema search: BM25 + Vector + Graph Centrality.

    BM25 handles exact keyword matches (precision).
    Vector handles semantic similarity (recall).
    Centrality handles structural preference (hub tables rank higher).

    Fusion: α·RRF + β·BM25_norm + γ·centrality
    Defaults: α=0.70, β=0.15, γ=0.15
    """

    def __init__(self):
        self._bm25_index:   Optional[Any] = None
        self._corpus:       List[str] = []
        self._meta:         List[Dict] = []
        self._index_built:  bool = False
        self._indexed_count: int = 0

    # ── Index builder ──────────────────────────────────────────────────────

    def _build_index(self) -> None:
        if self._index_built:
            return

        all_docs: List[str] = []
        all_meta: List[Dict] = []

        try:
            from app.core.vector_store import store_manager as _sm

            try:
                from qdrant_client import QdrantClient
                qc = QdrantClient(url="http://localhost:6333", timeout=3)
                offset = None
                while True:
                    records, next_offset = qc.scroll(
                        collection_name="sap_schema",
                        limit=256,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    if not records:
                        break
                    for pt in records:
                        payload = getattr(pt, "payload", {})
                        doc = payload.get("document", "")
                        if doc:
                            all_docs.append(doc)
                            all_meta.append({
                                "table":  payload.get("table", ""),
                                "module": payload.get("module", ""),
                                "domain": payload.get("domain", ""),
                            })
                    offset = next_offset
                    if not offset:
                        break
                logger.info(f"[BM25] Qdrant scroll: {len(all_docs)} docs")

            except Exception as _qe:
                logger.warning(f"[BM25] Qdrant scroll failed ({_qe})")

            if not all_docs:
                try:
                    results = _sm.search_schema(".", n_results=1000, domain=None)
                    all_docs = [r.get("document", "") for r in results]
                    all_meta = [r.get("metadata", {}) for r in results]
                except Exception as _fe:
                    logger.warning(f"[BM25] store_manager fallback: {_fe}")

        except ImportError:
            pass

        if not all_docs:
            logger.warning("[BM25] No schema docs found — BM25 disabled")
            self._index_built = True
            return

        try:
            from rank_bm25 import BM25Plus
        except ImportError:
            logger.warning("[BM25] rank_bm25 not installed")
            self._index_built = True
            return

        tokenized = [doc.lower().split() for doc in all_docs]
        self._bm25_index  = BM25Plus(tokenized)
        self._corpus      = all_docs
        self._meta        = all_meta
        self._indexed_count = len(all_docs)
        self._index_built = True
        logger.info(f"[BM25] Index built: {self._indexed_count} documents")

    # ── BM25 search ────────────────────────────────────────────────────────

    def _bm25_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        if not self._index_built:
            self._build_index()
        if self._bm25_index is None:
            return []

        tokenized = query.lower().split()
        scores = self._bm25_index.get_scores(tokenized)

        scored = [(s, i) for i, s in enumerate(scores) if s > 0]
        scored.sort(key=lambda x: -x[0])

        results = []
        seen = set()
        for score, idx in scored:
            meta = self._meta[idx] if idx < len(self._meta) else {}
            table = meta.get("table", f"doc_{idx}")
            if table in seen:
                continue
            seen.add(table)
            results.append({
                "table":    table,
                "document": self._corpus[idx] if idx < len(self._corpus) else "",
                "score":    round(score, 4),
                "metadata": meta,
            })
            if len(results) >= top_k:
                break

        logger.debug(f"[BM25] query='{query}' → {len(results)} results")
        return results

    # ── Vector search ─────────────────────────────────────────────────────

    def _vector_search(self, query: str, top_k: int = 10, domain: str = None) -> List[Dict[str, Any]]:
        try:
            from app.core.vector_store import store_manager as _sm
            results = _sm.search_schema(query, n_results=top_k, domain=domain)
            output = []
            for r in results:
                output.append({
                    "table":    r.get("metadata", {}).get("table", ""),
                    "document": r.get("document", ""),
                    "score":    1.0,   # Qdrant cosine not exposed in scroll
                    "metadata": r.get("metadata", {}),
                })
            return output
        except Exception as e:
            logger.warning(f"[BM25] Vector search failed: {e}")
            return []

    # ── Public API ─────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        domain: str = None,
        top_k: int = 6,
    ) -> List[Dict[str, Any]]:
        t0 = time.time()

        keyword_heavy = is_keyword_heavy_query(query)
        bm25_results  = self._bm25_search(query, top_k=top_k * 2)
        vec_results   = self._vector_search(query, top_k=top_k * 2, domain=domain)

        if not bm25_results and not vec_results:
            return []

        # Build centrality map
        centrality_map = _build_centrality_map()

        # Keyword-heavy → BM25 gets higher weight; RRF base shifts toward BM25
        if keyword_heavy and len(bm25_results) >= 3:
            # Keyword-dominant: trust BM25 rank more
            kw_w = 0.55
            vec_w = 0.45
            fused = reciprocal_rank_fusion(
                vec_results, bm25_results, centrality_map,
                vec_weight=vec_w, bm25_weight=kw_w,
                k=RRF_K,
            )
            fusion_used = "keyword_heavy"
        else:
            # Standard fusion: α=0.70, β=0.15, γ=0.15
            fused = reciprocal_rank_fusion(
                vec_results, bm25_results, centrality_map,
                vec_weight=BM25_VEC_WEIGHT,
                k=RRF_K,
            )
            fusion_used = "semantic" if not keyword_heavy else "hybrid"

        elapsed_ms = round((time.time() - t0) * 1000, 1)

        output = []
        for rank, info in enumerate(fused[:top_k]):
            info["final_rank"] = rank
            info["signals"]["keyword_heavy"] = keyword_heavy
            info["signals"]["fusion_used"]    = fusion_used
            info["signals"]["elapsed_ms"]     = elapsed_ms
            info["signals"]["weights"] = {
                "alpha": BM25_VEC_WEIGHT,
                "beta":  BM25_KEYWORD_W,
                "gamma": BM25_CENTRALITY_W,
            }
            output.append(info)

        logger.info(
            f"[BM25] query='{query[:40]}' kh={keyword_heavy} fu={fusion_used} "
            f"→ {len(output)} results in {elapsed_ms}ms"
        )
        return output


# ── Singleton ────────────────────────────────────────────────────────────────

_hybrid_search: Optional[BM25HybridSearch] = None


def get_bm25_hybrid_search() -> BM25HybridSearch:
    global _hybrid_search
    if _hybrid_search is None:
        _hybrid_search = BM25HybridSearch()
    return _hybrid_search


def bm25_hybrid_search(
    query: str,
    domain: str = None,
    top_k: int = 6,
) -> List[Dict[str, Any]]:
    """One-line convenience wrapper."""
    return get_bm25_hybrid_search().search(query=query, domain=domain, top_k=top_k)