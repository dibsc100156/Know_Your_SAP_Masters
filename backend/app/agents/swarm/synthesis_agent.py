"""
synthesis_agent.py — Multi-Agent Domain Swarm: Synthesis Agent
==============================================================
The Synthesis Agent receives results from multiple Domain Agents
and produces a single, coherent, ranked response.

Responsibilities:
  1. MERGE — Combine result sets from multiple agents, deduplicate
  2. RANK  — Score and rank results by relevance to the original query
  3. RESOLVE — Handle conflicting information across agents
  4. ANSWER — Generate natural language answer + data table
  5. EXPLAIN — Surface which domains were involved and why

Usage:
    from app.agents.swarm.synthesis_agent import SynthesisAgent
    synthesizer = SynthesisAgent()
    result = synthesizer.synthesize(query, agent_results, auth_context, routing)
"""

from __future__ import annotations

import time
import hashlib
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

from app.core.security import SAPAuthContext, security_mesh
from app.agents.swarm.contracts import validate_contract, build_contract, get_contract_for_agent


@dataclass
class MergedRecord:
    """A deduplicated, scored record from a multi-agent result set."""
    original_data: Dict[str, Any]
    source_agents: List[str]
    merge_key: str          # Deterministic key for deduplication
    relevance_score: float  # 0.0–1.0
    domain_tags: List[str]  # Which domains this record spans


class SynthesisAgent:
    """
    Merges and synthesizes results from parallel domain agents.
    Produces a unified answer with full traceability.
    """

    # Field synonyms — normalize across SAP tables
    FIELD_SYNONYMS = {
        "LIFNR": "vendor_id",
        "KUNNR": "customer_id",
        "MATNR": "material_id",
        "EBELN": "po_number",
        "VBELN": "sales_document",
        "NETWR": "net_value",
        "DMBTR": "amount",
        "WAERS": "currency",
        "NAME1": "name",
        "BUKRS": "company_code",
        "WERKS": "plant",
        "EKORG": "purchasing_org",
        "ERNAM": "created_by",
        "AEDAT": "creation_date",
    }

    def synthesize(
        self,
        query: str,
        agent_results: Dict[str, Any],
        auth_context: SAPAuthContext,
        routing,  # RoutingType enum
    ) -> Dict[str, Any]:
        """
        Main synthesis entry point.

        Args:
            query: Original user query
            agent_results: {agent_name: result_dict} from parallel domain agents
            auth_context: SAPAuthContext for masking
            routing: RoutingType enum value

        Returns:
            Synthesized result dict with:
              - merged_data: Combined and deduplicated records
              - answer: Natural language synthesis
              - agent_summary: Per-agent result overview
              - domain_coverage: Which domains contributed
              - conflicts: Any data conflicts resolved
        """
        start = time.time()

        # Filter out error results
        valid_results = {
            name: r for name, r in agent_results.items()
            if "error" not in r and r.get("data")
        }
        error_results = {
            name: r["error"] for name, r in agent_results.items()
            if "error" in r or not r.get("data")
        }

        if not valid_results:
            return {
                "answer": "None of the domain agents could resolve this query.",
                "merged_data": [],
                "agent_summary": {name: {"status": "error", "error": error_results.get(name, "no data")}
                                  for name in agent_results},
                "domain_coverage": [],
                "conflicts": [],
                "execution_time_ms": int((time.time() - start) * 1000),
                "record_count": 0,
                "validation_summary": {"agents_validated": 0, "agents_passed": 0, "agents_failed": 0},
            }

        # [Harness] Validate each agent's output before merging
        # Contract validation failures flag outputs as partial but NEVER block synthesis
        validation_summary = {
            "agents_validated": 0,
            "agents_passed": 0,
            "agents_failed": 0,
            "per_agent": {},
        }
        for name, result in valid_results.items():
            validation_summary["agents_validated"] += 1
            is_valid, errors = False, []
            try:
                contract_cls = get_contract_for_agent(name)
                # If the result is already a contract dict (from build_contract), rebuild from raw
                # If it's a plain dict, build a contract now
                if result.get("validation_passed") is not None:
                    # Already validated by domain agent — trust it
                    is_valid = bool(result.get("validation_passed"))
                    errors = result.get("validation_errors", [])
                else:
                    # Not yet validated — build contract and validate now
                    contract = build_contract(name, result)
                    is_valid, errors = validate_contract(contract)
            except Exception as e:
                is_valid, errors = False, [f"validation error: {e}"]

            validation_summary["per_agent"][name] = {
                "validation_passed": is_valid,
                "validation_errors": errors,
            }
            if is_valid:
                validation_summary["agents_passed"] += 1
            else:
                validation_summary["agents_failed"] += 1

        # Step 2: Merge records from all agents
        merged = self._merge_results(valid_results, query)

        # Step 3: Apply masking based on auth context
        merged = self._apply_masking(merged, auth_context)

        # Step 4: Rank by relevance
        ranked = self._rank_results(merged, query)

        # Step 5: Build per-agent summary (now includes validation results)
        agent_summary = {}
        for name, result in valid_results.items():
            agent_summary[name] = {
                "status": "success",
                "record_count": len(result.get("data", [])),
                "tables_used": result.get("tables_used", []),
                "execution_time_ms": result.get("execution_time_ms", 0),
                "answer_excerpt": result.get("answer", "")[:80],
                # [Harness] Contract validation results
                "validation_passed": validation_summary["per_agent"].get(name, {}).get("validation_passed"),
                "validation_errors": validation_summary["per_agent"].get(name, {}).get("validation_errors", []),
            }

        for name, err in error_results.items():
            agent_summary[name] = {"status": "error", "error": str(err),
                                   "validation_passed": False, "validation_errors": ["agent returned error"]}

        # Step 6: Detect and resolve conflicts
        conflicts = self._detect_conflicts(valid_results)

        # Step 7: Generate natural language synthesis
        answer = self._generate_answer(query, ranked, agent_summary, routing)

        # Step 8: Domain coverage
        domain_coverage = list(valid_results.keys())

        elapsed = int((time.time() - start) * 1000)

        return {
            "answer": answer,
            "merged_data": ranked[:100],          # Top 100 records
            "total_records_after_merge": len(ranked),
            "agent_summary": agent_summary,
            "domain_coverage": domain_coverage,
            "conflicts": conflicts,
            "execution_time_ms": elapsed,
            "record_count": len(ranked),
            "masked_fields": self._get_masked_fields(ranked, auth_context),
            # [Harness] Contract validation summary
            "validation_summary": validation_summary,
        }

    # =========================================================================
    # Merge Logic
    # =========================================================================

    def _merge_results(
        self,
        agent_results: Dict[str, Any],
        query: str,
    ) -> List[MergedRecord]:
        """
        Merge records from multiple agents, deduplicating on a synthetic key.
        Key is built from: entity_id + document_type + date_field.
        """
        seen: Dict[str, MergedRecord] = {}
        q_lower = query.lower()

        for agent_name, result in agent_results.items():
            data = result.get("data", [])
            if not isinstance(data, list):
                data = [data] if data else []

            for row in data:
                if not isinstance(row, dict):
                    continue

                # Build merge key
                merge_key = self._build_merge_key(row, agent_name)

                if merge_key in seen:
                    # Deduplicate — merge source agents
                    existing = seen[merge_key]
                    if agent_name not in existing.source_agents:
                        existing.source_agents.append(agent_name)
                        existing.domain_tags = list(set(existing.domain_tags + [agent_name.split("_")[0]]))
                else:
                    # Score relevance
                    score = self._score_record_relevance(row, q_lower, agent_name)
                    seen[merge_key] = MergedRecord(
                        original_data=row,
                        source_agents=[agent_name],
                        merge_key=merge_key,
                        relevance_score=score,
                        domain_tags=[agent_name.split("_")[0]],
                    )

        merged = list(seen.values())
        return sorted(merged, key=lambda x: x.relevance_score, reverse=True)

    def _build_merge_key(self, row: Dict[str, Any], agent_name: str) -> str:
        """Build a deterministic merge key from a record."""
        # Try entity ID fields first
        for field in ["LIFNR", "KUNNR", "MATNR", "EBELN", "VBELN", "QALS", "BELNR"]:
            if field in row and row[field]:
                return f"{field}:{row[field]}"

        # Fallback: hash of sorted row items
        stable_items = sorted(
            (str(k), str(v)) for k, v in row.items()
            if v is not None and str(v) != ""
        )
        key_str = "|".join(f"{k}={v}" for k, v in stable_items[:8])
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def _score_record_relevance(
        self,
        row: Dict[str, Any],
        query_lower: str,
        agent_name: str,
    ) -> float:
        """Score how relevant a record is to the query."""
        score = 0.5  # Base

        # Boost if record has entity IDs mentioned in query
        entity_boost_fields = {
            "LIFNR": "vendor", "KUNNR": "customer",
            "MATNR": "material", "EBELN": "order", "VBELN": "sales",
        }
        for field, entity in entity_boost_fields.items():
            if field in row and row[field]:
                if entity in query_lower:
                    score += 0.2

        # Boost if named field has content
        for field in ["NAME1", "NAME2", "MAKTX", "MAKTG"]:
            if field in row and row[field] and len(str(row[field])) > 3:
                score += 0.05

        # Boost based on agent-domain match
        domain_keywords = {
            "bp": ["vendor", "customer", "partner", "name", "address"],
            "mm": ["material", "stock", "valuation", "unit"],
            "pur": ["order", "value", "item", "quantity", "po"],
            "sd": ["sales", "order", "delivery", "billing"],
            "qm": ["quality", "inspection", "result", "status"],
            "wm": ["warehouse", "storage", "bin", "stock"],
        }
        agent_domain = agent_name.split("_")[0]
        if agent_domain in domain_keywords:
            for kw in domain_keywords[agent_domain]:
                if kw in query_lower:
                    score += 0.1
                    break

        return min(score, 1.0)

    # =========================================================================
    # Masking
    # =========================================================================

    def _apply_masking(
        self,
        merged: List[MergedRecord],
        auth_context: SAPAuthContext,
    ) -> List[MergedRecord]:
        """Apply AuthContext field masking to merged records."""
        if not auth_context or not auth_context.masked_fields:
            return merged

        for record in merged:
            row = record.original_data
            for col, val in list(row.items()):
                if auth_context.is_column_masked("", col):
                    row[col] = "***RESTRICTED***"

        return merged

    # =========================================================================
    # Ranking
    # =========================================================================

    def _rank_results(
        self,
        merged: List[MergedRecord],
        query: str,
    ) -> List[Dict[str, Any]]:
        """Return merged records sorted by relevance score, highest first."""
        q_lower = query.lower()

        # Secondary sort: prefer records with more source agents (cross-domain)
        def sort_key(r: MergedRecord) -> tuple:
            has_cross_domain = len(r.source_agents) > 1
            return (r.relevance_score, has_cross_domain)

        sorted_records = sorted(merged, key=sort_key, reverse=True)
        return [r.original_data for r in sorted_records]

    # =========================================================================
    # Conflict Resolution
    # =========================================================================

    def _detect_conflicts(
        self,
        agent_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Detect conflicting values for the same entity across agents.
        e.g., BPAgent says NETWR=50000, PURAgent says NETWR=48000 for same LIFNR.
        """
        conflicts = []

        # Build entity → value maps per agent
        entity_fields = ["LIFNR", "KUNNR", "MATNR", "EBELN", "VBELN"]
        value_fields = ["NETWR", "DMBTR", "MENGE", "STPRS", "LABST"]

        for ef in entity_fields:
            for vf in value_fields:
                agent_values: Dict[str, Dict[str, Any]] = {}
                for name, result in agent_results.items():
                    for row in result.get("data", []):
                        if ef in row and row[ef] and vf in row:
                            entity_id = str(row[ef])
                            if entity_id not in agent_values:
                                agent_values[entity_id] = {}
                            agent_values[entity_id][name] = row[vf]

                # Check for conflict
                for entity_id, values in agent_values.items():
                    if len(values) >= 2:
                        numeric_values = {n: v for n, v in values.items()
                                         if isinstance(v, (int, float))}
                        if len(numeric_values) >= 2:
                            vals = list(numeric_values.values())
                            if max(vals) / max(abs(min(vals)), 0.01) > 1.05:  # 5% diff
                                conflicts.append({
                                    "entity_field": ef,
                                    "entity_id": entity_id,
                                    "value_field": vf,
                                    "values": values,
                                    "conflict_type": "value_mismatch",
                                    "resolution": "use_highest" if max(vals) > 0 else "use_lowest",
                                })

        return conflicts[:10]  # Cap at 10 conflicts

    # =========================================================================
    # Answer Generation
    # =========================================================================

    def _generate_answer(
        self,
        query: str,
        ranked_data: List[Dict[str, Any]],
        agent_summary: Dict[str, Any],
        routing,  # RoutingType
    ) -> str:
        """Generate a natural language synthesis."""
        if not ranked_data:
            return "No results found across the domain agents."

        total_records = len(ranked_data)
        agents_used = [n for n, s in agent_summary.items() if s.get("status") == "success"]
        domains_hit = len(agents_used)

        # Build answer
        answer_parts = []

        # Opening
        if domains_hit == 1:
            answer_parts.append(
                f"Resolved by the {agents_used[0].replace('_agent','').upper()} agent. "
            )
        else:
            answer_parts.append(
                f"Synthesized from {domains_hit} domain agents ({', '.join(a.replace('_agent','') for a in agents_used)}). "
            )

        # Record summary
        answer_parts.append(f"Found {total_records} record(s) matching your query.")

        # Top records (first 5)
        if ranked_data:
            answer_parts.append("\nTop results:")
            for i, row in enumerate(ranked_data[:5], 1):
                name_field = row.get("NAME1") or row.get("MAKTX") or row.get("MATNR", "")
                id_field = (row.get("LIFNR") or row.get("KUNNR")
                             or row.get("MATNR") or row.get("EBELN") or "")
                val_field = row.get("NETWR") or row.get("DMBTR") or row.get("MENGE") or ""
                if val_field:
                    answer_parts.append(
                        f"  {i}. {name_field} ({id_field}): {val_field}"
                    )
                else:
                    answer_parts.append(f"  {i}. {name_field} ({id_field})")

        # Conflicts note
        if ranked_data and any("conflict" in str(v) for v in agent_summary.values()):
            answer_parts.append(
                "\nNote: Some values were reconciled from multiple domains."
            )

        return " ".join(answer_parts)

    # =========================================================================
    # Masked Fields Detection
    # =========================================================================

    @staticmethod
    def _get_masked_fields(
        data: List[Dict[str, Any]],
        auth_context: SAPAuthContext,
    ) -> List[str]:
        """Return list of columns that were masked in the result."""
        if not data or not auth_context:
            return []
        masked = []
        for row in data[:5]:  # Sample first 5 rows
            for col in row:
                if row[col] == "***RESTRICTED***":
                    masked.append(col)
        return list(set(masked))
