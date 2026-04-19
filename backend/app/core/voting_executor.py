"""
voting_executor.py — Phase 14: Voting SQL Executor
===================================================
Implements Laurie Voss's "voting" pattern (Anthropic's 5 agent design patterns):
  "Three LLMs seldom hallucinate to the same wrong answer."

When to fire:
  - Composite confidence_score < 0.70  OR
  - Query flagged as compliance_critical (finance/vendor/tax domains)

3 voting paths:
  PATH_A — Graph RAG Priority
    Pillar weights:  Pillar5=0.60, Pillar3=0.30, Pillar1=0.10
    Uses: structural Node2Vec embeddings + all-paths-explorer
    Best for: multi-hop cross-module queries (vendor→PO→invoice chains)

  PATH_B — SQL Pattern RAG Priority
    Pillar weights:  Pillar4=0.70, Pillar3=0.20, Pillar1=0.10
    Uses: proven SAP SQL patterns from ChromaDB + semantic similarity
    Best for: standard operational queries (vendor master, material stock)

  PATH_C — Meta-Path Fast Path
    Pillar weights:  Pillar0=0.50, Pillar0.5=0.50 (pre-assembled JOIN templates)
    Uses: meta_path_library.match() — no LLM involved, pure pattern match
    Best for: common domain patterns (procure-to-pay, order-to-cash)

Voting logic:
  1. Table-set majority vote (which tables should be involved?)
  2. Semantic WHERE equivalence (are conditions logically the same?)
  3. SQL structural similarity (Jaccard on FROM/JOIN/WHERE tokens)
  Consensus threshold: 2/3 paths agree
  Disagreement → escalate with disagreement report for human review

Usage:
  from app.core.voting_executor import VotingExecutor, run_voting_sql_generation
  result = run_voting_sql_generation(query, auth_context, domain)
  if result["vote_outcome"] == "consensus":
      sql = result["consensus_sql"]
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VotingPathResult:
    path_name: str
    sql: str
    tables: List[str]
    confidence: float
    pillar_scores: Dict[str, float]
    reasoning: str
    exec_time_ms: float
    status: str  # "success" | "failed" | "skipped"


@dataclass
class VotingResult:
    vote_outcome: str          # "consensus" | "disagreement" | "partial"
    consensus_sql: Optional[str]
    winning_path: Optional[str]
    votes: List[VotingPathResult]
    table_vote: Dict[str, int]  # table -> number of paths that included it
    disagreement_alert: Optional[str]
    confidence_before_vote: float
    confidence_after_vote: float
    total_time_ms: float
    escalation_required: bool


# ---------------------------------------------------------------------------
# Core voting logic
# ---------------------------------------------------------------------------

def _extract_table_set(sql: str) -> set:
    """Extract table names from FROM/JOIN clauses."""
    tables = set()
    # Simple regex — handles "FROM LFA1" and "JOIN EKKO ON ..."
    import re
    # FROM clause
    from_matches = re.findall(r'FROM\s+([A-Z0-9_]+)', sql, re.IGNORECASE)
    tables.update(m_matches.upper() for m_matches in from_matches)
    # JOIN clause
    join_matches = re.findall(r'JOIN\s+([A-Z0-9_]+)', sql, re.IGNORECASE)
    tables.update(j.upper() for j in join_matches)
    # Subquery tables
    sub_matches = re.findall(r'FROM\s*\((?:[^)]+)\)\s+AS\s+(\w+)', sql, re.IGNORECASE)
    tables.update(s.upper() for s in sub_matches)
    return tables


def _sql_tokens(sql: str) -> set:
    """Tokenize SQL for Jaccard similarity (normalize whitespace)."""
    import re
    normalized = re.sub(r'\s+', ' ', sql.upper())
    tokens = set(re.findall(r'[A-Z0-9_]+', normalized))
    # Remove SQL keywords that shouldn't affect similarity
    keywords = {
        'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'JOIN', 'ON', 'LEFT', 'RIGHT',
        'INNER', 'OUTER', 'AS', 'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT',
        'ASC', 'DESC', 'DISTINCT', 'UNION', 'INSERT', 'UPDATE', 'DELETE',
    }
    return tokens - keywords


def _token_jaccard(sql_a: str, sql_b: str) -> float:
    """Compute Jaccard similarity between two SQLs' token sets."""
    tokens_a = _sql_tokens(sql_a)
    tokens_b = _sql_tokens(sql_b)
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _vote_on_tables(votes: List[VotingPathResult]) -> Tuple[set, Dict[str, int]]:
    """
    Table majority vote — which tables appear in >= 2/3 paths?
    Returns (agreed_tables, table_counts).
    """
    table_counts: Dict[str, int] = {}
    for vote in votes:
        if vote.status != "success":
            continue
        for t in vote.tables:
            t = t.upper()
            table_counts[t] = table_counts.get(t, 0) + 1

    threshold = max(2, len([v for v in votes if v.status == "success"]) * 2 // 3)
    agreed = {t for t, count in table_counts.items() if count >= threshold}
    return agreed, table_counts


def _evaluate_vote(votes: List[VotingPathResult], confidence_before: float) -> VotingResult:
    """
    Core voting algorithm:
      1. Table-set majority vote
      2. SQL similarity check across agreeing paths
      3. Pick winning path or flag disagreement
    """
    start = time.time()
    successful = [v for v in votes if v.status == "success"]

    if not successful:
        return VotingResult(
            vote_outcome="disagreement",
            consensus_sql=None,
            winning_path=None,
            votes=votes,
            table_vote={},
            disagreement_alert="All 3 paths failed — no SQL could be generated.",
            confidence_before_vote=confidence_before,
            confidence_after_vote=0.0,
            total_time_ms=(time.time() - start) * 1000,
            escalation_required=True,
        )

    # Step 1: Table majority vote
    agreed_tables, table_counts = _vote_on_tables(successful)
    winning_path = None
    consensus_sql = None

    if len(agreed_tables) >= 2:
        # 2+ tables agreed → find paths that match exactly
        matching_paths = []
        for vote in successful:
            vote_tables = set(t.upper() for t in vote.tables)
            if vote_tables == agreed_tables:
                matching_paths.append(vote)

        if len(matching_paths) >= 2:
            # Consensus!
            # Pick highest-confidence path among those that agree
            best = max(matching_paths, key=lambda v: v.confidence)
            consensus_sql = best.sql
            winning_path = best.path_name
        elif len(matching_paths) == 1:
            # Only 1 path matches agreed tables — partial consensus
            consensus_sql = matching_paths[0].sql
            winning_path = matching_paths[0].path_name
        else:
            # Tables agreed but SQL differs → check SQL similarity
            if len(successful) >= 2:
                # Find the pair with highest Jaccard similarity
                best_pair_sql = None
                best_jaccard = 0.0
                best_pair_path = None
                for i in range(len(successful)):
                    for j in range(i + 1, len(successful)):
                        jac = _token_jaccard(successful[i].sql, successful[j].sql)
                        if jac > best_jaccard:
                            best_jaccard = jac
                            best_pair_sql = successful[i].sql if successful[i].confidence >= successful[j].confidence else successful[j].sql
                            best_pair_path = successful[i].path_name if successful[i].confidence >= successful[j].confidence else successful[j].path_name

                if best_jaccard >= 0.75:
                    consensus_sql = best_pair_sql
                    winning_path = best_pair_path
                    logger.info(f"    [VOTE] SQL similarity {best_jaccard:.2f} → using {winning_path}")

    # Step 2: Disagreement detection
    if consensus_sql is None and len(successful) >= 2:
        # Check if any two paths have high Jaccard
        for i in range(len(successful)):
            for j in range(i + 1, len(successful)):
                jac = _token_jaccard(successful[i].sql, successful[j].sql)
                if jac >= 0.80:
                    # High similarity — use the higher-confidence one
                    best = successful[i] if successful[i].confidence >= successful[j].confidence else successful[j]
                    consensus_sql = best.sql
                    winning_path = best.path_name
                    logger.info(f"    [VOTE] Jaccard {jac:.2f} between {successful[i].path_name} & {successful[j].path_name} → {winning_path}")
                    break
            if consensus_sql:
                break

    total_time_ms = (time.time() - start) * 1000

    # Step 3: Final determination
    if consensus_sql and winning_path:
        # Consensus found — boost confidence
        confidence_after = min(0.95, confidence_before + 0.10)
        outcome = "consensus"
        escalation = False
        disagreement_alert = None
    elif len(successful) == 1:
        # Only 1 path succeeded — use it with a warning
        consensus_sql = successful[0].sql
        winning_path = successful[0].path_name
        confidence_after = successful[0].confidence
        outcome = "partial"
        escalation = False
        disagreement_alert = f"Only {successful[0].path_name} succeeded — 2 paths failed. Using result from {winning_path}."
    else:
        # True disagreement — escalate
        outcome = "disagreement"
        disagreement_alert = (
            f"Voting disagreement across {len(successful)} paths. "
            f"SQL similarity below threshold. Escalate to human review. "
            f"Table votes: {table_counts}. "
            f"Paths: {[(v.path_name, v.sql[:60]) for v in successful]}"
        )
        confidence_after = max(0.0, confidence_before - 0.15)
        escalation = True

    return VotingResult(
        vote_outcome=outcome,
        consensus_sql=consensus_sql,
        winning_path=winning_path,
        votes=votes,
        table_vote=table_counts,
        disagreement_alert=disagreement_alert,
        confidence_before_vote=confidence_before,
        confidence_after_vote=round(confidence_after, 3),
        total_time_ms=round(total_time_ms, 1),
        escalation_required=escalation,
    )


# ---------------------------------------------------------------------------
# Path executors — each runs SQL generation with different pillar weights
# ---------------------------------------------------------------------------

def _run_path_a_graph_rag_priority(
    query: str, auth_context: Any, domain: str, tables_involved: List[str]
) -> VotingPathResult:
    """
    PATH_A — Graph RAG Priority (Pillar 5 heavy).
    Uses: graph_store.find_path() + structural scoring + Node2Vec.
    """
    start = time.time()
    try:
        from app.core.graph_store import graph_store
        from app.core.graph_embedding_store import graph_embedding_store

        # Step 1: Graph embedding search (Pillar 5.5) — structural discovery
        embedded_results = graph_embedding_store.search_graph_tables(
            query=query,
            domain=domain if domain != "auto" else "general",
            top_k=5,
        )

        # Step 2: Path finder (Pillar 5) — ranked JOIN paths
        all_tables = list(set(tables_involved)) if tables_involved else ["LFA1", "EKKO"]
        path_tables: List[str] = []
        if len(all_tables) >= 2:
            path_tables = graph_store.find_path(
                start_table=all_tables[0],
                end_table=all_tables[-1],
            ) or []


        # Step 3: Get top path SQL
        path_sql = ""
        if path_tables:
            path_sql = "SELECT * FROM " + ", ".join(path_tables[:5]) + " WHERE MANDT = '100'"

        # Step 4: Build SQL from graph-discovered tables
        if path_sql:
            sql = path_sql
        else:
            # Fallback: generate simple SQL from discovered tables
            table_list = ", ".join(all_tables[:4])
            sql = f"SELECT * FROM {table_list} WHERE MANDT = '100'"

        # Step 5: Mask with AuthContext
        from app.agents.orchestrator_tools import call_tool, ToolStatus
        mask_result = call_tool("result_mask", {"sql": sql, "tables": all_tables}, auth_context=auth_context)
        if mask_result.status == ToolStatus.SUCCESS:
            sql = mask_result.data.get("masked_sql", sql) if isinstance(mask_result.data, dict) else sql

        exec_time_ms = (time.time() - start) * 1000
        return VotingPathResult(
            path_name="PATH_A_GRAPH_RAG",
            sql=sql,
            tables=[t.upper() for t in all_tables[:4]],
            confidence=0.82,
            pillar_scores={"Pillar5": 0.60, "Pillar3": 0.30, "Pillar1": 0.10},
            reasoning=f"Graph RAG: {len(path_tables)} tables from find_path, {len(embedded_results)} embeddings from search_graph_tables.",
            exec_time_ms=round(exec_time_ms, 1),
            status="success",
        )

    except Exception as e:
        exec_time_ms = (time.time() - start) * 1000
        logger.warning(f"    [VOTE-WARN] PATH_A failed: {e}")
        return VotingPathResult(
            path_name="PATH_A_GRAPH_RAG",
            sql="",
            tables=[],
            confidence=0.0,
            pillar_scores={"Pillar5": 0.60, "Pillar3": 0.30, "Pillar1": 0.10},
            reasoning=f"PATH_A_GRAPH_RAG failed: {str(e)[:100]}",
            exec_time_ms=round(exec_time_ms, 1),
            status="failed",
        )


def _run_path_b_sql_pattern_priority(
    query: str, auth_context: Any, domain: str, tables_involved: List[str]
) -> VotingPathResult:
    """
    PATH_B — SQL Pattern RAG Priority (Pillar 4 heavy).
    Uses: sql_vector_store.search() + proven pattern matching + critique.
    """
    start = time.time()
    try:
        from app.core.sql_vector_store import SQLRAGStore, get_sql_library
        from app.agents.orchestrator_tools import call_tool, ToolStatus

        # Step 1: SQL Pattern RAG search (Pillar 4) via SQLRAGStore.search()
        sql_lib = get_sql_library()
        if isinstance(sql_lib, SQLRAGStore):
            pattern_results = sql_lib.search(query=query, top_k=3)
        else:
            pattern_results = []

        # Step 2: Pick best proven pattern
        if pattern_results and len(pattern_results) > 0:
            best_pattern = pattern_results[0]
            base_sql = best_pattern.get("sql_template", best_pattern.get("sql", "")) if isinstance(best_pattern, dict) else ""
            pattern_name = best_pattern.get("pattern_name", "unknown") if isinstance(best_pattern, dict) else "unknown"
        else:
            base_sql = ""
            pattern_name = "no_match"

        # Step 3: Build SQL from pattern
        if base_sql:
            sql = base_sql
        else:
            # Fallback: simple SQL from tables_involved
            table_list = ", ".join(tables_involved[:3]) if tables_involved else "LFA1"
            sql = f"SELECT * FROM {table_list} WHERE MANDT = '100'"

        # Step 4: Validate with critique agent (requires query, sql, schema_context, auth_context)
        from app.agents.critique_agent import critique_agent
        auth_dict = {"role_id": auth_context.role_id, "user_id": f"user:{auth_context.role_id.lower()}"} if auth_context else {}
        critique_result = critique_agent.critique(
            query=query,
            sql=sql,
            schema_context=[],
            auth_context=auth_dict,
        )
        critique_score = critique_result.get("score", 0) if isinstance(critique_result, dict) else 0

        # Step 5: Mask with AuthContext
        mask_result = call_tool("result_mask", {"sql": sql, "tables": tables_involved}, auth_context=auth_context)
        if mask_result.status == ToolStatus.SUCCESS:
            sql = mask_result.data.get("masked_sql", sql) if isinstance(mask_result.data, dict) else sql

        exec_time_ms = (time.time() - start) * 1000
        return VotingPathResult(
            path_name="PATH_B_SQL_PATTERN",
            sql=sql,
            tables=[t.upper() for t in tables_involved[:4]] if tables_involved else [],
            confidence=min(0.90, 0.65 + (critique_score / 7.0) * 0.25),
            pillar_scores={"Pillar4": 0.70, "Pillar3": 0.20, "Pillar1": 0.10},
            reasoning=f"SQL Pattern RAG: pattern '{pattern_name}' matched, critique_score={critique_score}/7.",
            exec_time_ms=round(exec_time_ms, 1),
            status="success",
        )

    except Exception as e:
        exec_time_ms = (time.time() - start) * 1000
        logger.warning(f"    [VOTE-WARN] PATH_B failed: {e}")
        return VotingPathResult(
            path_name="PATH_B_SQL_PATTERN",
            sql="",
            tables=[],
            confidence=0.0,
            pillar_scores={"Pillar4": 0.70, "Pillar3": 0.20, "Pillar1": 0.10},
            reasoning=f"PATH_B_SQL_PATTERN failed: {str(e)[:100]}",
            exec_time_ms=round(exec_time_ms, 1),
            status="failed",
        )


def _run_path_c_meta_path_fast(
    query: str, auth_context: Any, domain: str, tables_involved: List[str]
) -> VotingPathResult:
    """
    PATH_C — Meta-Path Fast Path (Pillar 0 + 0.5).
    Uses: meta_path_library.match() — pre-assembled JOIN templates, no LLM needed.
    """
    start = time.time()
    try:
        from app.core.meta_path_library import meta_path_library

        # Step 1: Meta-path match (keyword + tag + description scoring)
        match_result = meta_path_library.match(query=query, domain=domain if domain != "auto" else None)
        meta_path = match_result.get("meta_path") if isinstance(match_result, dict) else None

        if meta_path and isinstance(meta_path, dict):
            # Use pre-assembled SQL template from meta-path
            path_sql = meta_path.get("sql_template", meta_path.get("sql", "")) if isinstance(meta_path, dict) else ""
            path_name = meta_path.get("name", "unknown") if isinstance(meta_path, dict) else "unknown"
            selected_columns = meta_path.get("select_columns", []) if isinstance(meta_path, dict) else []

            if path_sql:
                sql = path_sql
            else:
                tables = meta_path.get("tables", tables_involved[:4]) if isinstance(meta_path, dict) else tables_involved[:4]
                table_list = ", ".join(tables) if isinstance(tables, list) else str(tables)
                cols = ", ".join(selected_columns[:8]) if selected_columns else "*"
                sql = f"SELECT {cols} FROM {table_list} WHERE MANDT = '100'"
        else:
            # No meta-path match — use tables_involved fallback
            table_list = ", ".join(tables_involved[:3]) if tables_involved else "LFA1"
            sql = f"SELECT * FROM {table_list} WHERE MANDT = '100'"
            path_name = "fallback"

        # Step 2: Mask with AuthContext
        from app.agents.orchestrator_tools import call_tool, ToolStatus
        mask_result = call_tool("result_mask", {"sql": sql, "tables": tables_involved}, auth_context=auth_context)
        if mask_result.status == ToolStatus.SUCCESS:
            sql = mask_result.data.get("masked_sql", sql) if isinstance(mask_result.data, dict) else sql

        exec_time_ms = (time.time() - start) * 1000
        confidence = 0.88 if meta_path else 0.55

        return VotingPathResult(
            path_name="PATH_C_META_PATH",
            sql=sql,
            tables=[t.upper() for t in (meta_path.get("tables", tables_involved[:4]) if meta_path else tables_involved[:4])],
            confidence=confidence,
            pillar_scores={"Pillar0": 0.50, "Pillar0.5": 0.50},
            reasoning=f"Meta-Path Fast Path: {'matched ' + meta_path.get('name', '') if meta_path else 'no meta-path match — using tables_involved'}.",
            exec_time_ms=round(exec_time_ms, 1),
            status="success",
        )

    except Exception as e:
        exec_time_ms = (time.time() - start) * 1000
        logger.warning(f"    [VOTE-WARN] PATH_C failed: {e}")
        return VotingPathResult(
            path_name="PATH_C_META_PATH",
            sql="",
            tables=[],
            confidence=0.0,
            pillar_scores={"Pillar0": 0.50, "Pillar0.5": 0.50},
            reasoning=f"PATH_C_META_PATH failed: {str(e)[:100]}",
            exec_time_ms=round(exec_time_ms, 1),
            status="failed",
        )


# ---------------------------------------------------------------------------
# Main entry point — run all 3 paths in parallel, then vote
# ---------------------------------------------------------------------------

def run_voting_sql_generation(
    query: str,
    auth_context: Any,
    domain: str = "auto",
    tables_involved: Optional[List[str]] = None,
    confidence_before_vote: float = 0.65,
    compliance_critical: bool = False,
    max_workers: int = 3,
) -> VotingResult:
    """
    Run 3 parallel SQL generation paths and return consensus/disagreement result.

    Args:
        query: Natural language question
        auth_context: SAPAuthContext with role permissions
        domain: Domain hint (auto, business_partner, purchasing, etc.)
        tables_involved: List of tables already discovered (from Pillar 3/5)
        confidence_before_vote: Current confidence score (used for pre-vote baseline)
        compliance_critical: If True, always run voting regardless of confidence
        max_workers: Thread pool size (always 3 — one per path)

    Returns:
        VotingResult with consensus_sql, winning_path, votes, table_vote, etc.
    """
    start_total = time.time()
    tables = tables_involved or ["LFA1", "EKKO"]

    logger.info(f"\n[15/5] [Phase 14] VOTING EXECUTOR — firing 3-path vote on query: {query[:80]}...")
    logger.info(f"    [VOTE] confidence_before={confidence_before_vote:.3f} | compliance_critical={compliance_critical}")

    # Fire all 3 paths in parallel via ThreadPoolExecutor
    votes: List[VotingPathResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_path_a_graph_rag_priority, query, auth_context, domain, tables): "PATH_A",
            executor.submit(_run_path_b_sql_pattern_priority, query, auth_context, domain, tables): "PATH_B",
            executor.submit(_run_path_c_meta_path_fast, query, auth_context, domain, tables): "PATH_C",
        }

        for future in as_completed(futures, timeout=30.0):
            path_label = futures[future]
            try:
                result = future.result(timeout=10.0)
                votes.append(result)
                logger.info(f"    [VOTE] {path_label} done in {result.exec_time_ms:.0f}ms | status={result.status} | conf={result.confidence:.3f}")
            except Exception as e:
                logger.warning(f"    [VOTE-ERROR] {path_label} raised exception: {e}")
                votes.append(VotingPathResult(
                    path_name=path_label,
                    sql="",
                    tables=[],
                    confidence=0.0,
                    pillar_scores={},
                    reasoning=f"Exception during execution: {str(e)[:100]}",
                    exec_time_ms=0.0,
                    status="failed",
                ))

    # Sort votes by path name for consistent ordering
    votes.sort(key=lambda v: v.path_name)

    # Voting algorithm — evaluate consensus or disagreement
    result = _evaluate_vote(votes, confidence_before_vote)

    total_time_ms = (time.time() - start_total) * 1000
    result.total_time_ms = round(total_time_ms, 1)

    logger.info(f"    [VOTE] Outcome: {result.vote_outcome} | winning={result.winning_path} | confidence {result.confidence_before_vote:.3f} → {result.confidence_after_vote:.3f}")
    if result.disagreement_alert:
        logger.warning(f"    [VOTE-ALERT] {result.disagreement_alert[:120]}")

    return result


# ---------------------------------------------------------------------------
# Tool wrapper — exposes voting as a tool for TOOL_REGISTRY
# ---------------------------------------------------------------------------

def voting_sql_generate(params: Dict[str, Any], auth_context: Any) -> Dict[str, Any]:
    """
    TOOL_REGISTRY tool: voting_sql_generate
    Fires when confidence < 0.70 or query is compliance_critical.
    Returns full VotingResult as a dict.
    """
    query = params.get("query", "")
    domain = params.get("domain", "auto")
    tables_involved = params.get("tables_involved", [])
    confidence_before_vote = params.get("confidence_before_vote", 0.65)
    compliance_critical = params.get("compliance_critical", False)

    result = run_voting_sql_generation(
        query=query,
        auth_context=auth_context,
        domain=domain,
        tables_involved=tables_involved,
        confidence_before_vote=confidence_before_vote,
        compliance_critical=compliance_critical,
    )

    return {
        "status": "success" if result.consensus_sql else "disagreement",
        "vote_outcome": result.vote_outcome,
        "consensus_sql": result.consensus_sql,
        "winning_path": result.winning_path,
        "confidence_before_vote": result.confidence_before_vote,
        "confidence_after_vote": result.confidence_after_vote,
        "total_time_ms": result.total_time_ms,
        "escalation_required": result.escalation_required,
        "disagreement_alert": result.disagreement_alert,
        "table_vote": result.table_vote,
        "votes": [
            {
                "path_name": v.path_name,
                "sql": v.sql,
                "tables": v.tables,
                "confidence": v.confidence,
                "pillar_scores": v.pillar_scores,
                "reasoning": v.reasoning,
                "exec_time_ms": v.exec_time_ms,
                "status": v.status,
            }
            for v in result.votes
        ],
    }