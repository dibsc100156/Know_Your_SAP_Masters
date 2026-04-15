"""
meta_harness_loop.py — Automated Meta-Harness Loop
===================================================
Stanford Research (2026): An "agentic proposer" reads raw execution traces of
failed runs, diagnoses what broke, and writes modifications to the harness.

Design: ADVISORY MODE (safety first)
  collect_failed_runs()
      → build_analysis_context()
          → analyze_with_llm()    ← LLM diagnoses patterns
              → RecommendationYAML  (saved to meta_harness_recommendations/)
                  → [HUMAN APPROVES]
                      → apply_patches()  ← modifies harness files

Recommendation Categories:
  1. agent_routing     — AGENT_TOOL_GRAPH weight adjustments (planner_agent.py)
  2. meta_paths         — New/fixed JOIN paths (meta_path_library.py)
  3. healing_rules      — New HEALING_RULES entries (self_healer.py)
  4. complexity_weights — QueryComplexityAnalyzer dimension weights
  5. schema_rag         — New Qdrant chunking / indexing strategies
  6. sentinel_thresholds — Threat Sentinel threshold tuning

Usage:
  from app.core.meta_harness_loop import MetaHarnessLoop
  mh = MetaHarnessLoop()

  # Step 1: Collect and analyze (LLM-driven diagnosis)
  recommendations = mh.analyze_recent_failures(days=7)

  # Step 2: Review — print pending recommendations
  mh.print_recommendations(recommendations)

  # Step 3: Apply approved recommendations
  mh.apply_recommendations(['agent_routing_fix_001', 'healing_new_rule_003'])
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).parent.parent.parent
RECOMMENDATIONS_DIR = BACKEND_ROOT / "meta_harness_recommendations"
RECOMMENDATIONS_DIR.mkdir(exist_ok=True)

PATCHES_DIR = BACKEND_ROOT / "meta_harness_patches"
PATCHES_DIR.mkdir(exist_ok=True)

ARCHIVE_DIR = BACKEND_ROOT / "meta_harness_archive"
ARCHIVE_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Failure Pattern Taxonomy
# ---------------------------------------------------------------------------
class FailureCategory(str, Enum):
    """High-level failure categories for grouping."""
    ROUTING_MISFIRE       = "routing_misfire"
    SCHEMA_MISS           = "schema_miss"
    SQL_SYNTAX            = "sql_syntax"
    SELF_HEAL_FAIL        = "self_heal_fail"
    SELF_HEAL_CONFIDENTIAL = "self_heal_confidence"
    TEMPORAL_MISS         = "temporal_miss"
    CROSS_MODULE_MISS     = "cross_module_miss"
    SECURITY_BLOCK        = "security_block"
    MASKING_LEAK          = "masking_leak"
    EMPTY_RESULT          = "empty_result"
    UNKNOWN               = "unknown"


# ---------------------------------------------------------------------------
# FailureRecord — normalized record from one failed orchestrator run
# ---------------------------------------------------------------------------
class FailureRecord:
    """Normalized failure record extracted from HarnessRun phase history."""
    def __init__(
        self,
        run_id: str,
        query: str,
        user_role: str,
        status: str,
        swarm_routing: str,
        failure_phase: str,
        error_code: str,
        error_message: str,
        tables_involved: List[str],
        sql_attempted: str,
        self_healed: bool,
        heal_attempts: int,
        heal_success: bool,
        confidence_score: float,
        complexity_score: float,
        created_at: str,
    ):
        self.run_id = run_id
        self.query = query
        self.user_role = user_role
        self.status = status
        self.swarm_routing = swarm_routing
        self.failure_phase = failure_phase
        self.error_code = error_code
        self.error_message = error_message
        self.tables_involved = tables_involved
        self.sql_attempted = sql_attempted
        self.self_healed = self_healed
        self.heal_attempts = heal_attempts
        self.heal_success = heal_success
        self.confidence_score = confidence_score
        self.complexity_score = complexity_score
        self.created_at = created_at

    def category(self) -> FailureCategory:
        """Map error code/message to FailureCategory."""
        code = self.error_code.upper()
        msg = self.error_message.lower()

        sap_code = code.upper()
        if "table not found" in msg or "eiger" in msg or "schema" in msg or "not found" in msg or sap_code in ("ORA-00942", "TABLE_NOT_FOUND"):
            return FailureCategory.SCHEMA_MISS
        if "syntax" in msg or "cartesian" in msg or "division by zero" in msg or "subquery" in msg or "join" in msg or sap_code in ("37000", "CARTESIAN_PRODUCT", "DIVISION_BY_ZERO", "SUBQUERY_JOIN_ERROR"):
            return FailureCategory.SQL_SYNTAX
        if "mandt" in msg or "mandt missing" in msg:
            return FailureCategory.SCHEMA_MISS
        if "not authorized" in msg or "auth" in sap_code.lower():
            return FailureCategory.SECURITY_BLOCK
        if "empty" in msg or "no rows" in msg or "0 rows" in msg or "returns empty" in msg:
            return FailureCategory.EMPTY_RESULT
        if self.self_healed or sap_code == "SELF_HEAL_FAILED":
            if self.heal_success:
                return FailureCategory.SELF_HEAL_CONFIDENTIAL
            return FailureCategory.SELF_HEAL_FAIL
        if self.tables_involved and len(self.tables_involved) > 2:
            return FailureCategory.CROSS_MODULE_MISS
        return FailureCategory.UNKNOWN

    def to_llm_context(self) -> str:
        return (
            f"[RUN {self.run_id}] query=\"{self.query[:100]}\"\n"
            f"  role={self.user_role} | routing={self.swarm_routing}\n"
            f"  failed_at={self.failure_phase} | error={self.error_code}: {self.error_message[:80]}\n"
            f"  tables={self.tables_involved} | self_healed={self.self_healed} "
            f"(attempts={self.heal_attempts}, success={self.heal_success})\n"
            f"  confidence={self.confidence_score:.2f} | complexity={self.complexity_score:.2f}\n"
            f"  sql_attempted: {self.sql_attempted[:120] if self.sql_attempted else '(none)'}"
        )


# ---------------------------------------------------------------------------
# Recommendation — structured output from LLM diagnosis
# ---------------------------------------------------------------------------
class Recommendation:
    """A single harness modification recommendation generated by the LLM."""
    def __init__(
        self,
        rec_id: str,
        category: str,
        title: str,
        evidence: str,
        pattern_description: str,
        recommended_fix: str,
        target_file: str,
        patch_lines: List[str],
        priority: str = "P2",
        effort: str = "medium",
        risk: str = "medium",
        examples: Optional[List[str]] = None,
        llm_model: str = "mock",
        created_at: Optional[str] = None,
        status: str = "pending",
    ):
        self.id = rec_id
        self.category = category
        self.title = title
        self.evidence = evidence
        self.pattern_description = pattern_description
        self.recommended_fix = recommended_fix
        self.target_file = target_file
        self.patch_lines = patch_lines
        self.priority = priority
        self.effort = effort
        self.risk = risk
        self.examples = examples or []
        self.llm_model = llm_model
        self.created_at = created_at or datetime.now().isoformat()
        self.status = status  # pending | approved | applied | rejected

    def to_yaml(self) -> str:
        examples_str = ", ".join(self.examples) if self.examples else "none"
        patch_str = "\n".join(self.patch_lines) if self.patch_lines else "(review manually)"
        return (
            f"recommendation_id: {self.id}\n"
            f"category: {self.category}\n"
            f"title: {self.title}\n"
            f"priority: {self.priority}\n"
            f"effort: {self.effort}\n"
            f"risk: {self.risk}\n"
            f"target_file: {self.target_file}\n"
            f"examples: [{examples_str}]\n"
            f"llm_model: {self.llm_model}\n"
            f"created_at: {self.created_at}\n"
            f"status: {self.status}\n"
            f"\nevidence: |\n"
            f"  {self.evidence.replace(chr(10), chr(10) + '  ')}\n"
            f"\npattern: |\n"
            f"  {self.pattern_description.replace(chr(10), chr(10) + '  ')}\n"
            f"\nrecommended_fix: |\n"
            f"  {self.recommended_fix.replace(chr(10), chr(10) + '  ')}\n"
            f"\npatch: |\n"
            f"  {'=' * 60}\n"
            f"  FILE: {self.target_file}\n"
            f"  {'=' * 60}\n"
            f"  {patch_str}\n"
        )

    def apply(self) -> Tuple[bool, str]:
        """Apply this recommendation's patch to the target file. Returns (success, message)."""
        # Resolve path (strip leading 'backend/' since BACKEND_ROOT already points to it)
        rel_path = self.target_file
        if rel_path.startswith("backend/"):
            rel_path = rel_path[len("backend/"):]
        target = BACKEND_ROOT / rel_path
        if not target.exists():
            return False, f"Target file not found: {target}"

        try:
            with open(target, "r", encoding="utf-8") as f:
                original = f.read()

            # Filter YAML separators from patch_lines
            clean_lines = [
                line for line in self.patch_lines
                if line.strip() not in ("", "---", "...")
            ]
            patch_text = "\n".join(clean_lines)

            # Category-aware patch insertion
            patched_content = self._insert_patch(original, patch_text, self.category)

            # Build unified diff
            diff = difflib.unified_diff(
                original.splitlines(keepends=True),
                patched_content.splitlines(keepends=True),
                fromfile=f"{self.target_file} (original)",
                tofile=f"{self.target_file} (patched: {self.id})",
                lineterm=""
            )
            diff_str = "".join(diff)

            # Apply
            with open(target, "w", encoding="utf-8") as f:
                f.write(patched_content)

            # Archive diff
            archivename = ARCHIVE_DIR / f"{self.id}__{datetime.now():%Y%m%d_%H%M%S}.diff"
            with open(archivename, "w", encoding="utf-8") as f:
                f.write(diff_str)

            self.status = "applied"
            return True, f"Patched {self.target_file} | Diff archived: {archivename.name}"
        except Exception as e:
            return False, f"Failed to apply patch: {e}"

    def _insert_patch(self, original: str, patch_text: str, category: str) -> str:
        """
        Insert patch_text into original content, based on category.
        - healing_rules: insert new HealingRule before closing ] of HEALING_RULES
        - meta_paths:    insert new path dict before closing ] of SAP_META_PATHS
        - default:       append at end of file
        """
        if category == "healing_rules" and "HEALING_RULES" in original:
            # Find where HEALING_RULES list ends
            hr_idx = original.find("HEALING_RULES: List[HealingRule]")
            if hr_idx >= 0:
                last_bracket = original.find("\n]", hr_idx)
                if last_bracket >= 0:
                    rule_block = "    " + patch_text.rstrip().rstrip(",") + ",\n"
                    return original[:last_bracket] + "\n" + rule_block + original[last_bracket:]
        if category == "meta_paths" and "SAP_META_PATHS" in original:
            mp_idx = original.find("SAP_META_PATHS = [")
            if mp_idx >= 0:
                last_bracket = original.find("\n]", mp_idx)
                if last_bracket >= 0:
                    path_block = "    " + patch_text.rstrip().rstrip(",") + ",\n"
                    return original[:last_bracket] + "\n" + path_block + original[last_bracket:]
        # Default: append at end
        return original + "\n" + patch_text + "\n"


class MetaHarnessLoop:
    """
    Automated Meta-Harness Loop (Advisory Mode).

    Safety philosophy: Never apply patches autonomously.
    The loop collects failures, diagnoses with LLM, generates YAML
    recommendations for HUMAN review, and applies only after approval.

    Pipeline:
      1. collect_failed_runs()      — Pull from Redis/HarnessRuns
      2. _group_by_pattern()         — Cluster by error category
      3. _build_analysis_context()   — Format for LLM
      4. _call_llm_diagnosis()       — Get YAML recommendations
      5. _parse_recommendations()    — Parse into Recommendation objects
      6. [HUMAN REVIEW]
      7. apply_recommendations()     — Apply approved patches
    """


    def __init__(self, llm_model: str = "openai/gpt-4o"):
        self.llm_model = llm_model
        self._harness_runs = None

    # -------------------------------------------------------------------------
    # Step 1: Collect failed runs from Redis
    # -------------------------------------------------------------------------
    def collect_failed_runs(self, days: int = 7, limit: int = 200) -> List[FailureRecord]:
        """
        Pull recent failed/partial runs from HarnessRuns Redis table.
        Returns list of FailureRecord normalized from raw phase history.
        """
        records = []
        try:
            from app.core.harness_runs import get_harness_runs
            self._harness_runs = get_harness_runs()

            cutoff = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff.isoformat()

            for role in ["AP_CLERK", "MM_CLERK", "SD_CLERK", "FI_ACCOUNTANT", "SYSTEM"]:
                runs = self._harness_runs.list_runs_by_role(role, limit=limit)
                for run in runs:
                    if run.created_at < cutoff_str:
                        continue
                    if run.status not in ("failed", "partial"):
                        continue

                    phase_states = self._harness_runs.get_phase_history(run.run_id)
                    failed_phase = None
                    error_code = ""
                    error_msg = ""
                    tables = []
                    sql_attempted = ""
                    self_healed = False
                    heal_attempts = 0
                    heal_success = False

                    for ps in reversed(phase_states):
                        if ps.status == "failed":
                            failed_phase = ps.phase
                            err = getattr(ps, "error", "") or ""
                            for code in re.findall(r"(ORA-\d+|SAP\d+|HANA_[A-Z]+|CARTESIAN_PRODUCT|MANDT_MISSING|DIVISION_BY_ZERO|TABLE_NOT_FOUND|SUBQUERY_JOIN_ERROR|SELF_HEAL_FAILED|[37]\d{3})", err):
                                error_code = code
                            error_msg = err[:200]
                            arts = getattr(ps, "artifacts", {}) or {}
                            if isinstance(arts, str):
                                try:
                                    import json as _json
                                    arts = _json.loads(arts)
                                except Exception:
                                    arts = {}
                            if not isinstance(arts, dict):
                                arts = {}
                            tables = arts.get("tables_used", [])
                            sql_attempted = (
                                arts.get("sql_generated", "") or arts.get("sql", "") or ""
                            )
                            self_healed = arts.get("self_healed", False)
                            heal_attempts = arts.get("heal_attempts", 0)
                            heal_success = arts.get("heal_success", False)
                            break

                    if not failed_phase:
                        continue

                    records.append(FailureRecord(
                        run_id=run.run_id,
                        query=run.query,
                        user_role=run.user_role,
                        status=run.status,
                        swarm_routing=run.swarm_routing,
                        failure_phase=failed_phase,
                        error_code=error_code or "UNKNOWN",
                        error_message=error_msg or "No error message captured",
                        tables_involved=tables,
                        sql_attempted=sql_attempted,
                        self_healed=self_healed,
                        heal_attempts=heal_attempts,
                        heal_success=heal_success,
                        confidence_score=run.confidence_score,
                        complexity_score=run.complexity_score,
                        created_at=run.created_at,
                    ))
        except Exception as e:
            logger.error(f"Failed to collect harness runs: {e}")

        return records

    # -------------------------------------------------------------------------
    # Step 2: Group failures into patterns
    # -------------------------------------------------------------------------
    def _group_by_pattern(self, failures: List[FailureRecord]) -> Dict[str, List[FailureRecord]]:
        """Group failures by category + error_code for pattern analysis."""
        groups: Dict[str, List[FailureRecord]] = {}
        for f in failures:
            key = f"{f.category().value}::{f.error_code}"
            if key not in groups:
                groups[key] = []
            groups[key].append(f)
        return groups

    # -------------------------------------------------------------------------
    # Step 3: Build LLM prompt context
    # -------------------------------------------------------------------------
    def _build_analysis_context(
        self, failures: List[FailureRecord], groups: Dict[str, List[FailureRecord]]
    ) -> str:
        """Build the LLM prompt with failure data formatted for diagnosis."""
        ctx_lines = [
            "# META-HARNESS DIAGNOSIS REQUEST",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Failed runs analyzed: {len(failures)}",
            f"Unique failure patterns: {len(groups)}",
            "",
            "## CURRENT HARNESS REFERENCE (do not modify)",
            "",
            "### Agent Routing — AGENT_TOOL_GRAPH (planner_agent.py)",
            "  7 agents: bp_agent, mm_agent, pur_agent, sd_agent, qm_agent, wm_agent, cross_agent",
            "  Scoring: ((1.5 * agent_context_score) + (1.0 * tool_spec_score)) / 2.5",
            "  Routing thresholds: SINGLE>=0.85, PARALLEL>=0.5, complexity_threshold=0.6",
            "  max_parallel_agents=3",
            "",
            "### Self-Healing Rules — HEALING_RULES (self_healer.py)",
            "  9 rules: MANDT_MISSING, CARTESIAN_PRODUCT, DIVISION_BY_ZERO,",
            "  TABLE_NOT_FOUND, INVALID_COLUMN, SYNTAX_ERROR,",
            "  SUBQUERY_JOIN_ERROR, SAP_AUTH_BLOCK, EMPTY_RESULT",
            "",
            "### QueryComplexityAnalyzer dimensions (planner_agent.py)",
            "  multi_entity(15%), aggregation(10%), comparison(10%),",
            "  temporal(15%), cross_module_join(25%), negotiation(10%), qm_long_text(15%)",
            "",
            "### Meta-Path Library (meta_path_library.py)",
            "  14 meta-paths: vendor_master_basic, vendor_material_relationship,",
            "  vendor_financial_exposure, procure_to_pay, open_purchase_orders,",
            "  order_to_cash, customer_open_items, material_stock_position,",
            "  material_cost_rollup, inspection_lot_material, project_costs_wbs,",
            "  asset_register, transportation_delivery, warehouse_quant_inventory",
            "",
            "## FAILED RUNS (chronological, newest first)",
            "",
        ]
        for f in sorted(failures, key=lambda x: x.created_at, reverse=True):
            ctx_lines.append(f.to_llm_context())
            ctx_lines.append("")

        ctx_lines += ["", "## FAILURE PATTERN SUMMARY", ""]
        for key, group in sorted(groups.items(), key=lambda x: -len(x[1])):
            cat, code = key.split("::")
            ctx_lines.append(f"  [{len(group)}x] {cat} | {code}:")
            for ex in group[:3]:
                ctx_lines.append(f"    query=\"{ex.query[:80]}\" | phase={ex.failure_phase}")
            ctx_lines.append("")

        return "\n".join(ctx_lines)

    # -------------------------------------------------------------------------
    # Step 4: LLM Diagnosis
    # -------------------------------------------------------------------------
    def _call_llm_diagnosis(self, context: str) -> str:
        """
        Call LLM with the diagnosis prompt. Falls back to mock when API unavailable.
        Override this method to use a custom LLM backend.
        """
        try:
            import openai
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.strip()},
                    {"role": "user", "content": context}
                ],
                temperature=0.2,
                max_tokens=4000,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"LLM call failed ({e}) — using mock recommendations")
            return self._mock_llm_response(context)

    # -------------------------------------------------------------------------
    # Step 5: Parse LLM output into Recommendation objects
    # -------------------------------------------------------------------------
    def _parse_recommendations(self, llm_output: str, failures: List[FailureRecord]) -> List[Recommendation]:
        """Parse the LLM's YAML-ish output into structured Recommendation objects."""
        recs = []
        blocks = re.split(r"(?=^recommendation_id:)", llm_output, flags=re.MULTILINE)
        for block in blocks:
            if not block.strip():
                continue
            try:
                rec = self._parse_block(block, failures)
                if rec:
                    recs.append(rec)
            except Exception as e:
                logger.warning(f"Failed to parse block: {e}")
                continue
        return recs

    def _parse_block(self, block: str, failures: List[FailureRecord]) -> Optional[Recommendation]:
        """Parse one recommendation block into a Recommendation object."""
        def get(field: str, default: str = "") -> str:
            m = re.search(rf"^{field}:(.*)$", block, re.MULTILINE | re.IGNORECASE)
            return m.group(1).strip() if m else default

        rec_id   = get("recommendation_id")
        category = get("category", "unknown")
        title    = get("title")
        priority = get("priority", "P2")
        effort   = get("effort", "medium")
        risk     = get("risk", "medium")
        target   = get("target_file")
        evidence = get("evidence")
        pattern  = get("pattern")
        fix      = get("recommended_fix")

        patch_lines = []
        patch_idx = block.find("patch: |")
        if patch_idx >= 0:
            patch_content = block[patch_idx + 8:].strip()
            lines = patch_content.splitlines()
            clean = []
            for l in lines:
                if l.strip() == "---":
                    break
                if not l.strip().startswith("===") and not l.strip().startswith("FILE:"):
                    clean.append(l)
            patch_lines = [l.strip() for l in clean if l.strip() and not l.startswith("#")]

        if not rec_id or not title:
            return None

        # Link to example failure run IDs
        examples = []
        keywords = [w.lower() for w in title.split()[:4] if len(w) > 3]
        for f in failures:
            if any(kw in f.query.lower() for kw in keywords):
                examples.append(f.run_id)
        examples = list(dict.fromkeys(examples))[:3]  # dedupe, keep order, max 3

        return Recommendation(
            rec_id=rec_id,
            category=category,
            title=title,
            evidence=evidence[:1000],
            pattern_description=pattern[:500],
            recommended_fix=fix[:500],
            target_file=target,
            patch_lines=patch_lines,
            priority=priority,
            effort=effort,
            risk=risk,
            examples=examples,
            llm_model=self.llm_model,
        )

    # -------------------------------------------------------------------------
    # Step 6: Mock LLM response (dev/demo mode — no API key needed)
    # -------------------------------------------------------------------------
    def _mock_llm_response(self, context: str) -> str:
        """
        Realistic mock recommendations for development and demonstration.
        Triggered automatically when no LLM API key is available.
        """
        return """\
recommendation_id: agent_routing_fix_001
category: agent_routing
title: pur_agent undersells on queries containing 'vendor + purchasing' compound intent
priority: P1
effort: low
risk: low
target_file: backend/app/agents/swarm/planner_agent.py

evidence: |
  Multiple failed runs show pur_agent scoring below the 0.5 parallel threshold
  despite strong purchasing signal (purchase order, EKKO, EKPO) combined with
  'vendor' keyword. The bp_agent context ('vendor') dominates and wins routing.
  pur_agent is the correct handler for these queries.

pattern: |
  Query pattern: ('vendor' OR 'supplier') + ('purchase order' OR 'PO' OR 'contract')
  Currently routes to bp_agent (0.7) over pur_agent (0.4) because 'vendor' alone
  scores 0.7 in bp_agent context. The 1.5:1 Agent:Tool scoring correctly applies
  weights but the bp_agent context is too broad for compound purchasing intent.

recommended_fix: |
  Add a COMPOUND KEYWORD MATCHER in graph_route_query() that detects
  ('vendor' OR 'supplier') + ('purchase order' OR 'contract' OR 'PO' OR 'rfq')
  and applies a +0.3 bonus to pur_agent when both conditions are met.

patch: |
  # Add compound bonus after the standard context scoring in graph_route_query():
      # Compound keyword bonus: 'vendor' + purchasing signal → boost pur_agent
      compound_vendor_purchasing = (
          (any(k in query_lower for k in ["vendor", "supplier"])) and
          (any(k in query_lower for k in ["purchase order", "contract", "rfq", "info record"]))
      )
      if compound_vendor_purchasing:
          agent_context_score = min(1.0, agent_context_score + 0.3)
          if agent_name == "pur_agent":
              final_score = min(1.0, final_score + 0.15)

---
recommendation_id: healing_new_rule_001
category: healing_rules
title: Missing rule for ORA-00918 (column ambiguously defined in multi-JOIN)
priority: P2
effort: medium
risk: low
target_file: backend/app/core/self_healer.py

evidence: |
  Cross-module queries with multiple JOINs to same-named columns (BUKRS, WERKS,
  MATNR) cause ORA-00918 (column ambiguously defined) when schema masking changes
  column visibility. No existing HEALING_RULE handles this error code.

pattern: |
  Error: ORA-00918 column ambiguously defined. Appears in cross-module queries
  joining >3 tables. Root cause: table aliases not used consistently in SELECT.

recommended_fix: |
  Add a new HealingRule for ORA-00918 that detects the offending column name
  from the error message, then rewrites the SELECT list to qualify it with
  the correct table alias using the alias mapping from the SQL text.

patch: |
      HealingRule(
          code="AMBIGUOUS_COLUMN",
          triggers=["ORA-00918", "column ambiguously defined"],
          description="Column reference is ambiguous across multiple JOINed tables",
          apply="qualify_column",
      ),

---
recommendation_id: meta_path_gap_001
category: meta_paths
title: Missing meta-path for vendor quality scorecard (QALS → LFA1 → TQ01T)
priority: P2
effort: medium
risk: low
target_file: backend/app/core/meta_path_library.py

evidence: |
  Queries combining vendor AND quality dimensions (e.g. "vendor quality rating
  for top 10 suppliers by spend") fail to find the correct JOIN path. The graph
  traversal falls back to broad LFA1 scan. A dedicated vendor quality meta-path
  would directly join LFA1 → QALS → TQ01T (quality task/codes).

pattern: |
  Query: vendor quality + purchasing. Phase 3 graph traversal finds multiple
  paths but cannot rank them. A domain-specific vendor quality meta-path with
  bloom filter [QALS, TQ01T, LFA1] would enable the fast path.

recommended_fix: |
  Add a new meta-path 'vendor_quality_scorecard' to SAP_META_PATHS that
  explicitly maps the LFA1 → QALS → TQ01T join chain with correct join
  conditions and select_columns for vendor quality attributes.

patch: |
      {
          "name": "vendor_quality_scorecard",
          "description": "Vendor quality scorecard: LFA1 + QALS inspection results + TQ01T quality codes",
          "table_chain": ["LFA1", "QALS", "TQ01T"],
          "join_conditions": {
              "LFA1": {"QALS": "LFA1~LIFNR = QALS~LIFNR"},
              "QALS": {"TQ01T": "QALS~QSMAT = TQ01T~QSMAT AND TQ01T~SPRAS = 'E'"}
          },
          "select_columns": {
              "LFA1": ["LIFNR", "NAME1", "ORT01"],
              "QALS": ["LIFNR", "ART", "Q Zahlen (lot size)", "UDATE"],
              "TQ01T": ["QSMAT", "QKText"]
          },
          "example_queries": ["vendor quality rating", "supplier inspection results", "top vendors by quality score"],
          "row_count_warning": "LFA1 has ~10000 rows; filter by LIFNR or date range"
      },
"""


# ---------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # Public API Methods
    # -------------------------------------------------------------------------

    def analyze_recent_failures(
        self,
        days: int = 7,
        limit: int = 200,
        save_to=None,
    ) -> list:
        """
        Full pipeline: collect failures -> group by pattern -> LLM diagnosis -> parse.
        Returns list of Recommendation objects saved to:
          meta_harness_recommendations/analysis_<datetime>.yaml
        """
        failures = self.collect_failed_runs(days=days, limit=limit)
        if not failures:
            logger.info("No failed runs — no recommendations generated")
            return []

        groups = self._group_by_pattern(failures)
        context = self._build_analysis_context(failures, groups)
        llm_output = self._call_llm_diagnosis(context)
        recommendations = self._parse_recommendations(llm_output, failures)

        out_path = save_to or (
            RECOMMENDATIONS_DIR / f"analysis_{datetime.now():%Y%m%d_%H%M%S}.yaml"
        )
        with open(out_path, "w", encoding="utf-8") as f_out:
            f_out.write(f"# Meta-Harness Analysis | {datetime.now():%Y-%m-%d %H:%M} UTC\n")
            f_out.write(f"# Failures analyzed: {len(failures)}\n")
            f_out.write(f"# Recommendations: {len(recommendations)}\n\n")
            for rec in recommendations:
                f_out.write(rec.to_yaml())
                f_out.write("\n---\n\n")

        logger.info(f"Saved {len(recommendations)} recommendations to {out_path}")
        return recommendations

    def print_recommendations(self, recommendations: list) -> None:
        """Pretty-print recommendations for human review."""
        if not recommendations:
            print("\n[meta-harness] No recommendations — harness is healthy!")
            return

        print(f"\n{'='*70}")
        print(f"  META-HARNESS LOOP — {len(recommendations)} Recommendation(s)")
        print(f"{'='*70}")
        for rec in sorted(
            recommendations,
            key=lambda r: ["P0", "P1", "P2"].index(r.priority)
        ):
            icons = {"low": "OK", "medium": "!!", "high": "!!"}
            icon = icons.get(rec.risk, "?")
            print(f"\n  [{rec.priority}] [{icon}] {rec.id}")
            print(f"       {rec.title}")
            print(f"       category={rec.category} | effort={rec.effort} | risk={rec.risk}")
            print(f"       target: {rec.target_file}")
            print(f"  Evidence: {rec.evidence[:150]}")
            print(f"  Fix:      {rec.recommended_fix[:150]}")
            if rec.patch_lines:
                print(f"  Patch ({len(rec.patch_lines)} lines):")
                for line in rec.patch_lines[:6]:
                    print(f"    + {line[:100]}")
                if len(rec.patch_lines) > 6:
                    print(f"    ... +{len(rec.patch_lines)-6} more lines")

    def apply_recommendations(
        self,
        rec_ids: list,
        recommendations: list = None,
    ) -> dict:
        """
        Apply approved recommendations by ID.
        Returns dict of rec_id -> (success: bool, message: str).
        """
        if recommendations is None:
            recommendations = self._load_saved_recommendations()
        id_map = {r.id: r for r in recommendations}
        results = {}
        for rec_id in rec_ids:
            rec = id_map.get(rec_id)
            if not rec:
                results[rec_id] = (False, f"Recommendation {rec_id} not found")
                continue
            success, msg = rec.apply()
            results[rec_id] = (success, msg)
            if success:
                self._mark_applied(rec)
        return results

    def _load_saved_recommendations(self) -> list:
        """Load all saved recommendation YAML files."""
        recs = []
        for yaml_file in sorted(RECOMMENDATIONS_DIR.glob("analysis_*.yaml")):
            with open(yaml_file, "r", encoding="utf-8") as f:
                content = f.read()
            blocks = re.split(r"(?=^recommendation_id:)", content, flags=re.MULTILINE)
            for block in blocks:
                rec = self._parse_block(block, [])
                if rec:
                    recs.append(rec)
        return recs

    def _mark_applied(self, rec) -> None:
        """Stamp a recommendation as applied in its YAML file."""
        for yaml_file in sorted(RECOMMENDATIONS_DIR.glob("analysis_*.yaml")):
            with open(yaml_file, "r", encoding="utf-8") as f:
                content = f.read()
            if rec.id in content:
                pattern = "(recommendation_id: " + re.escape(rec.id) + "\\n)"
                replacement = "\\1status: APPLIED at " + datetime.now().isoformat() + "\\n"
                new_content = re.sub(pattern, replacement, content)
                with open(yaml_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
                break

    def load_recommendations_from_file(self, yaml_path) -> list:
        """Load recommendations from a specific YAML file."""
        with open(yaml_path, "r", encoding="utf-8") as f:
            content = f.read()
        blocks = re.split(r"(?=^recommendation_id:)", content, flags=re.MULTILINE)
        return [r for block in blocks if (r := self._parse_block(block, []))]

    def approve_and_apply(
        self,
        yaml_path,
        rec_ids: list = None,
    ) -> dict:
        """
        Load recommendations from YAML, filter by rec_ids (optional),
        mark as approved, then apply.
        """
        recs = self.load_recommendations_from_file(yaml_path)
        if rec_ids:
            recs = [r for r in recs if r.id in rec_ids]
        for rec in recs:
            rec.status = "approved"
        return self.apply_recommendations([r.id for r in recs], recs)


    # -------------------------------------------------------------------------
    # Public API Methods
    # -------------------------------------------------------------------------

    def analyze_recent_failures(
        self,
        days: int = 7,
        limit: int = 200,
        save_to=None,
    ) -> list:
        """
        Full pipeline: collect failures -> group by pattern -> LLM diagnosis -> parse.
        Returns list of Recommendation objects saved to:
          meta_harness_recommendations/analysis_<datetime>.yaml
        """
        failures = self.collect_failed_runs(days=days, limit=limit)
        if not failures:
            logger.info("No failed runs — no recommendations generated")
            return []

        groups = self._group_by_pattern(failures)
        context = self._build_analysis_context(failures, groups)
        llm_output = self._call_llm_diagnosis(context)
        recommendations = self._parse_recommendations(llm_output, failures)

        out_path = save_to or (
            RECOMMENDATIONS_DIR / f"analysis_{datetime.now():%Y%m%d_%H%M%S}.yaml"
        )
        with open(out_path, "w", encoding="utf-8") as f_out:
            f_out.write(f"# Meta-Harness Analysis | {datetime.now():%Y-%m-%d %H:%M} UTC\n")
            f_out.write(f"# Failures analyzed: {len(failures)}\n")
            f_out.write(f"# Recommendations: {len(recommendations)}\n\n")
            for rec in recommendations:
                f_out.write(rec.to_yaml())
                f_out.write("\n---\n\n")

        logger.info(f"Saved {len(recommendations)} recommendations to {out_path}")
        return recommendations

    def print_recommendations(self, recommendations: list) -> None:
        """Pretty-print recommendations for human review."""
        if not recommendations:
            print("\n[meta-harness] No recommendations — harness is healthy!")
            return

        print(f"\n{'='*70}")
        print(f"  META-HARNESS LOOP — {len(recommendations)} Recommendation(s)")
        print(f"{'='*70}")
        for rec in sorted(
            recommendations,
            key=lambda r: ["P0", "P1", "P2"].index(r.priority)
        ):
            icons = {"low": "OK", "medium": "!!", "high": "!!"}
            icon = icons.get(rec.risk, "?")
            print(f"\n  [{rec.priority}] [{icon}] {rec.id}")
            print(f"       {rec.title}")
            print(f"       category={rec.category} | effort={rec.effort} | risk={rec.risk}")
            print(f"       target: {rec.target_file}")
            print(f"  Evidence: {rec.evidence[:150]}")
            print(f"  Fix:      {rec.recommended_fix[:150]}")
            if rec.patch_lines:
                print(f"  Patch ({len(rec.patch_lines)} lines):")
                for line in rec.patch_lines[:6]:
                    print(f"    + {line[:100]}")
                if len(rec.patch_lines) > 6:
                    print(f"    ... +{len(rec.patch_lines)-6} more lines")


# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are the Meta-Harness Optimizer. Your job is to analyze failed AI agent
execution traces and recommend specific, actionable modifications to the
agent's "harness" — the orchestration code, routing logic, and error-handling
rules that wrap the LLM.

You are CONSERVATIVE. Only recommend changes when failure evidence is clear
and the fix is low-risk. Prefer deleting bad rules over adding new ones
("craft of subtraction"). Never suggest changing model parameters.

OUTPUT FORMAT: YAML block per recommendation, separated by "---".

For each recommendation, produce:
  recommendation_id: <kebab-case-id>
  category: agent_routing | meta_paths | healing_rules | complexity_weights | schema_rag | sentinel_thresholds
  title: <one-line description>
  priority: P0 (blocks production) | P1 (correctness gap) | P2 (optimization)
  effort: low (<1hr) | medium (1-4hr) | high (half-day+)
  risk: low | medium | high
  target_file: <relative path from backend root>
  evidence: |
    Why this recommendation is warranted — quote specific failure patterns.
  pattern: |
    What the failures have in common, and why your fix addresses the root cause.
  recommended_fix: |
    Concrete description of what to change and why.
  patch: |
    EXACT code/text to add to the target file. Include surrounding context
    lines so a human reviewer can see exactly where to insert it.

RULES:
1. Never suggest changing LLM model or temperature.
2. If unsure about a pattern, mark it P2 and note the uncertainty.
3. Prioritize "craft of subtraction" — removing noisy rules > adding new ones.
4. For healing_rules: only add rules for errors NOT already handled.
   Current rules: MANDT_MISSING, CARTESIAN_PRODUCT, DIVISION_BY_ZERO,
   TABLE_NOT_FOUND, INVALID_COLUMN, SYNTAX_ERROR, SUBQUERY_JOIN_ERROR,
   SAP_AUTH_BLOCK, EMPTY_RESULT.
5. For agent_routing: use the 1.5:1 Agent:Tool scoring formula.
   Boost an agent's score by adding compound keyword matches.
6. For complexity_weights: scores must sum to 1.0 across all dimensions.
7. Maximum 3 recommendations per analysis. Only the strongest patterns.
"""


# ---------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------
def run_harness_analysis(
    days: int = 7,
    limit: int = 200,
    llm_model: str = "openai/gpt-4o",
    save_to: Optional[Path] = None,
) -> List[Recommendation]:
    """
    Convenience function: run the full Meta-Harness pipeline.
    Returns list of Recommendation objects. Saves YAML to meta_harness_recommendations/.
    """
    mh = MetaHarnessLoop(llm_model=llm_model)
    return mh.analyze_recent_failures(days=days, limit=limit, save_to=save_to)


def print_recommendations(recommendations: List[Recommendation]) -> None:
    """Pretty-print recommendations for human review."""
    if not recommendations:
        print("\n[meta-harness] No recommendations — harness is healthy!")
        return

    print(f"\n{'='*70}")
    print(f"  META-HARNESS LOOP — {len(recommendations)} Recommendation(s)")
    print(f"{'='*70}")
    for rec in sorted(
        recommendations,
        key=lambda r: ["P0", "P1", "P2"].index(r.priority)
    ):
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(rec.risk, "⚪")
        print(f"\n  [{rec.priority}] {risk_icon} {rec.id}")
        print(f"       {rec.title}")
        print(f"       category={rec.category} | effort={rec.effort} | risk={rec.risk}")
        print(f"       target: {rec.target_file}")
        print(f"  Evidence: {rec.evidence[:150]}")
        print(f"  Fix:      {rec.recommended_fix[:150]}")
        if rec.patch_lines:
            print(f"  Patch ({len(rec.patch_lines)} lines):")
            for line in rec.patch_lines[:6]:
                print(f"    + {line[:100]}")
            if len(rec.patch_lines) > 6:
                print(f"    ... +{len(rec.patch_lines)-6} more lines")


# ---------------------------------------------------------------------------
# CLI entry point
# -------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Meta-Harness Loop CLI")
    parser.add_argument("--days", type=int, default=7, help="Look back window (days)")
    parser.add_argument("--limit", type=int, default=200, help="Max runs to analyze")
    parser.add_argument("--apply", nargs="*", help="Apply these recommendation IDs")
    parser.add_argument("--list", action="store_true", help="List saved recommendations")
    parser.add_argument("--model", default="openai/gpt-4o", help="LLM model")
    args = parser.parse_args()

    mh = MetaHarnessLoop(llm_model=args.model)

    if args.list:
        recs = mh._load_saved_recommendations()
        mh.print_recommendations(recs)
    elif args.apply:
        results = mh.apply_recommendations(args.apply)
        for rec_id, (ok, msg) in results.items():
            print(f"  {'[OK]' if ok else '[FAIL]'} {rec_id}: {msg}")
    else:
        print(f"[meta-harness] Analyzing last {args.days} days (max {args.limit} runs)...")
        recs = mh.analyze_recent_failures(days=args.days, limit=args.limit)
        mh.print_recommendations(recs)
        if recs:
            ids = " ".join(r.id for r in recs)
            print(f"\nTo apply approved recommendations:")
            print(f"  python -m app.core.meta_harness_loop --apply {ids}")


if __name__ == "__main__":
    main()
