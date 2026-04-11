"""
rag_service.py — LLM-Powered SAP Master Data Query Engine
=========================================================
Pillar 2 (Agentic) + Pillar 3/4/5 context wiring for the 5-Pillar RAG system.

Architecture:
  1. Intent Analysis      → classify query type (single/cross-module/transactional)
  2. Schema Retrieval     → Pillar 3: vector search for relevant table definitions
  3. SQL Pattern Lookup   → Pillar 4: proven SQL templates for domain/intent
  4. Graph Traversal      → Pillar 5: FK JOIN path for cross-module queries
  5. LLM Generation       → natural language → SAP HANA SQL (with full context)
  6. SQL Validation       → Pillar 1: SELECT-only, MANDT, auth-object, denied tables
  7. Execution            → SAP HANA (real) or mock (development)
  8. Result Masking       → Pillar 1: column-level redaction per role

Providers supported: Anthropic (Claude), OpenAI (GPT-4o / GPT-4o-mini).
Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your environment.
"""

from __future__ import annotations

import os
import re
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field
from openai import OpenAI  # type: ignore

try:
    from anthropic import Anthropic  # type: ignore
except ImportError:
    Anthropic = None  # anthropic package not installed


# Local Services
from app.core.vector_store import store_manager
from app.core.security import security_mesh, SAPAuthContext
from app.core.graph_store import graph_store


# =============================================================================
# LLM Provider Abstraction
# =============================================================================

class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def generate(self, system: str, user: str, **kwargs) -> str:
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    """Anthropic Claude via messages API."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        if Anthropic is None:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment.")
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def generate(self, system: str, user: str, **kwargs) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", 1024),
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o / GPT-4o-mini via Chat Completions API."""

    def __init__(self, model: str = "gpt-4o-mini"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in environment.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, system: str, user: str, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", 1024),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content


# =============================================================================
# Intent Analyzer
# =============================================================================

@dataclass
class IntentResult:
    intent: str            # "single_domain" | "cross_module" | "transactional" | "unknown"
    primary_domain: str    # "business_partner" | "material_master" | "purchasing" | ...
    key_entities: List[str]  # detected entities: vendor numbers, material IDs, etc.
    suggested_tables: List[str]  # tables likely needed
    needs_graph: bool = False  # whether to trigger Pillar 5 Graph RAG


class IntentAnalyzer:
    """
    Classifies the user's query and identifies relevant SAP entities.
    Uses keyword + structure heuristics for routing. Could be replaced
    with an LLM classifier for production.
    """

    DOMAIN_SIGNALS: Dict[str, List[str]] = {
        "business_partner":    ["vendor", "supplier", "customer", "partner", "contact", "address", "company code vendor"],
        "material_master":     ["material", "product", "stock", "valuation", "unit of measure", "material type"],
        "purchasing":          ["purchase order", "po ", "purchasing info record", "source list", "scheduling agreement", "outline agreement"],
        "sales_distribution":  ["sales order", "delivery", "billing", "pricing", "invoice", "customer forecast"],
        "warehouse_management": ["storage location", "transfer order", "bin", "quant", "warehouse"],
        "quality_management":  ["inspection lot", "quality", "usage decision", "certificate", "qm"],
        "financial_accounting":["gl account", "journal entry", "asset", "cost center", "profit center", "fi document"],
        "project_system":       ["wbs", "network", "project", "activity", "work breakdown"],
        "transportation":      ["shipment", "transport", "forwarding", "freight", "carrier", "tm"],
        "customer_service":    ["service order", "warranty", "service notification", "equipment", "functional location"],
    }

    ENTITY_PATTERNS = [
        (r"LIFNR[:\s]+['\"]?([0-9A-Z]+)['\"]?", "vendor_id"),
        (r"EBELN[:\s]+['\"]?([0-9A-Z]+)['\"]?", "po_number"),
        (r"VBELN[:\s]+['\"]?([0-9A-Z]+)['\"]?", "sales_document"),
        (r"MATNR[:\s]+['\"]?([0-9A-Z]+)['\"]?", "material_id"),
        (r"(?:vendor|supplier)[:\s]+([A-Z]{2,})", "vendor_name"),
        (r"(?:material|product)[:\s]+([A-Z0-9]+)", "material_id"),
        (r"plant[:\s]+([0-9A-Z]{4})", "plant"),
        (r"company code[:\s]+([0-9A-Z]{4})", "company_code"),
    ]

    def analyze(self, query: str, explicit_domain: Optional[str]) -> IntentResult:
        q = query.lower().strip()

        # 1. Detect domain
        if explicit_domain and explicit_domain != "auto":
            primary = explicit_domain
        else:
            primary = self._detect_domain(q)

        # 2. Detect cross-module signals
        cross_module_signals = [
            ("vendor", "material"), ("supplier", "material"),
            ("purchase order", "vendor"), ("po", "material"),
            ("vendor", "plant"), ("material", "valuation"),
            ("customer", "material"), ("sales", "material"),
        ]
        is_cross = any(a in q and b in q for a, b in cross_module_signals)
        is_transactional = any(w in q for w in ["open purchase order", "unpaid invoice", "pending delivery", "overdue", "open po"])

        # 3. Extract key entities
        entities = []
        for pattern, entity_type in self.ENTITY_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                entities.append(f"{entity_type}={match.group(1)}")

        # 4. Determine intent
        if is_transactional:
            intent = "transactional"
        elif is_cross or primary in ("cross_module_purchasing", "cross_module"):
            intent = "cross_module"
        elif primary in ("business_partner", "material_master", "purchasing", "sales_distribution",
                         "warehouse_management", "quality_management", "financial_accounting",
                         "project_system", "transportation", "customer_service"):
            intent = "single_domain"
        else:
            intent = "unknown"

        # 5. Suggest tables based on domain
        domain_tables = {
            "business_partner":    ["BUT000", "LFA1", "LFB1", "LFBK", "ADRC"],
            "material_master":      ["MARA", "MARC", "MARD", "MBEW", "MAKT"],
            "purchasing":           ["EKKO", "EKPO", "EINA", "EINE", "EORD"],
            "sales_distribution":   ["VBAK", "VBAP", "LIKP", "LIPS", "VBRK"],
            "warehouse_management": ["MARD", "MLGN", "LQUA", "LAGP", "LEU4"],
            "quality_management":   ["QALS", "QAVE", "MAPL", "PLMK"],
            "financial_accounting": ["BKPF", "BSEG", "BSIK", "BSAK", "SKA1"],
            "project_system":       ["PROJ", "PRPS", "AFVC", "AFVV", "COSP"],
            "transportation":       ["VTTK", "VTLP", "VTFA"],
            "customer_service":     ["ASMD", "IHPA", "EQUI", "IHK6"],
        }
        suggested = domain_tables.get(primary, [])

        return IntentResult(
            intent=intent,
            primary_domain=primary,
            key_entities=entities,
            suggested_tables=suggested,
            needs_graph=(intent == "cross_module" or intent == "transactional"),
        )

    def _detect_domain(self, q: str) -> str:
        scores: Dict[str, float] = {}
        for domain, keywords in self.DOMAIN_SIGNALS.items():
            score = sum(1 for kw in keywords if kw in q)
            if score > 0:
                scores[domain] = score
        if not scores:
            return "unknown"
        return max(scores, key=scores.get)


# =============================================================================
# SQL Generator — LLM-powered with 5-pillar context
# =============================================================================

SAP_SQL_SYSTEM_PROMPT = """You are an expert SAP S/4 HANA SQL generator. You convert natural language business questions into precise, secure, executable SAP HANA SQL queries.

CRITICAL RULES — never violate:
1. SELECT ONLY — no INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, or EXECUTE
2. MANDT (client) must always be filtered: AND MANDT = '{mandt}'
3. Never reference tables the user's role is not authorized for (denied tables listed in context)
4. Use actual SAP HANA SQL syntax (not standard SQL — SAP-specific field names and conventions)
5. Always qualify fields with table aliases when joining multiple tables
6. Only SELECT fields relevant to the question — never SELECT * in production queries
7. Dates: SAP stores dates as CHAR(8) in format YYYYMMDD — use DATS_* functions for date arithmetic
8. Numeric fields: NUMC fields must be compared as strings or CAST appropriately
9. All tables must be valid SAP S/4 HANA tables from the provided schema context

AUTH CONTEXT:
{auth_context}

SCHEMA CONTEXT (available tables and columns):
{schema_context}

SQL PATTERN EXAMPLES (proven SAP queries for this domain):
{sql_patterns}

{f_graph_context}
""".strip()


class SQLGenerator:
    """
    Builds the LLM prompt with full 5-pillar context and validates the output.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider
        self._provider_init()

    def _provider_init(self):
        """Initialize the LLM provider from environment."""
        if self.provider is not None:
            return
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        provider_type = os.getenv("LLM_PROVIDER", "openai").lower()

        if not api_key:
            self.provider = None
            return

        if provider_type == "openai":
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            self.provider = OpenAIProvider(model=model)
        else:
            model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
            self.provider = AnthropicProvider(model=model)

    def build_prompt(self, query: str, intent: IntentResult,
                     schemas: List[Dict], patterns: List[Dict],
                     auth: SAPAuthContext) -> tuple[str, str]:
        """
        Build (system_prompt, user_prompt) for the LLM.
        Returns (system, user) strings ready for the provider.
        """
        # Auth context summary
        auth_ctx = (
            f"Role: {auth.role_id} | {auth.description}\n"
            f"Allowed Company Codes: {', '.join(auth.allowed_company_codes) or 'ALL'}\n"
            f"Allowed Plants:       {', '.join(auth.allowed_plants) or 'ALL'}\n"
            f"Allowed Purchasing Orgs: {', '.join(auth.allowed_purchasing_orgs) or 'ALL'}\n"
            f"Denied Tables:       {', '.join(auth.denied_tables) or 'none'}\n"
            f"Masked Fields:       {json.dumps(auth.masked_fields, indent=2)}"
        )

        # Schema context
        schema_lines = []
        for s in schemas:
            meta = s.get("metadata", {})
            schema_lines.append(
                f"  [{meta.get('domain','?')}] Table: {meta.get('table','?')}\n"
                f"    {s.get('document', meta.get('document',''))[:300]}"
            )
        schema_context = "\n".join(schema_lines) if schema_lines else "  No schema context available."

        # SQL patterns
        pattern_lines = []
        for p in patterns:
            pattern_lines.append(
                f"  Intent: {p.get('intent', p.get('metadata',{}).get('intent',''))}\n"
                f"  SQL: {p.get('sql', p.get('document',''))[:400]}"
            )
        sql_patterns = "\n".join(pattern_lines) if pattern_lines else "  No SQL patterns available."

        # Graph context
        graph_context = ""
        if intent.needs_graph and len(schemas) >= 2:
            table_list = [s.get("metadata", {}).get("table") for s in schemas if s.get("metadata", {}).get("table")]
            if len(table_list) >= 2:
                t1, t2 = table_list[0], table_list[1]
                path = graph_store.find_path(t1, t2)
                if path:
                    subgraph = graph_store.get_subgraph_context(path)
                    edges = subgraph.get("joins", [])
                    bridge_info = ""
                    if edges:
                        bridge_info = "  Required JOIN path:\n" + "\n".join(
                            f"    {e['from']} → {e['to']} ON {e['condition']}"
                            for e in edges
                        )
                    graph_context = (
                        f"\n\nGRAPH CONTEXT (Pillar 5 — required for cross-module queries):\n"
                        f"  Path: {' → '.join(path)}\n"
                        f"  Cross-module bridges: {', '.join(subgraph.get('cross_module_bridges', []) or ['none'])}\n"
                        f"{bridge_info}"
                    )

        # System prompt
        system = SAP_SQL_SYSTEM_PROMPT.format(
            mandt=os.getenv("SAP_MANDT", "100"),
            auth_context=auth_ctx,
            schema_context=schema_context,
            sql_patterns=sql_patterns,
            f_graph_context=graph_context,
        )

        # User prompt
        user = (
            f"Business Question: {query}\n\n"
            f"Detected Intent: {intent.intent} ({intent.primary_domain})\n"
            f"Entities Identified: {', '.join(intent.key_entities) or 'none'}\n\n"
            f"Generate the SAP HANA SQL query that answers this question. "
            f"Follow all rules in the system prompt. "
            f"Return ONLY the SQL query — no markdown, no explanation, no preamble."
        )

        return system, user

    def generate(self, query: str, intent: IntentResult,
                 schemas: List[Dict], patterns: List[Dict],
                 auth: SAPAuthContext) -> str:
        """
        Generate SQL using the LLM. Falls back to template SQL if no API key.
        """
        system, user = self.build_prompt(query, intent, schemas, patterns, auth)

        if self.provider is None:
            # Development fallback: use template SQL from patterns
            return self._fallback_template(query, intent, patterns)

        try:
            raw_sql = self.provider.generate(system=system, user=user, max_tokens=1024)
            # Strip any markdown code fences
            sql = raw_sql.strip().strip("```sql").strip("```").strip()
            return sql
        except Exception as e:
            return f"-- LLM generation failed: {e}\n-- Falling back to template:\n" + \
                   self._fallback_template(query, intent, patterns)

    def _fallback_template(self, query: str, intent: IntentResult,
                           patterns: List[Dict]) -> str:
        """Use the top SQL pattern as a template when no LLM is available."""
        if patterns:
            top = patterns[0]
            return top.get("sql", top.get("document", "SELECT * FROM MARA LIMIT 10;")).strip()
        return "SELECT * FROM MARA LIMIT 10;"


# =============================================================================
# SQL Validator — Pillar 1 enforcement
# =============================================================================

DANGEROUS_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
    "CREATE", "EXECUTE", "EXEC ", "CALL ", "GRANT", "REVOKE",
    "COMMIT", "ROLLBACK", "SAVEPOINT",
]


class SQLValidator:
    """
    Validates generated SQL before execution:
    - SELECT-only enforcement
    - MANDT presence
    - Role-based table access
    - Auth object compliance
    """

    def __init__(self, auth: SAPAuthContext):
        self.auth = auth

    def validate(self, sql: str) -> tuple[bool, Optional[str], str]:
        """
        Returns (is_safe, error_message, corrected_sql).
        If MANDT is missing, auto-injects it.
        """
        sql_upper = sql.upper()
        sql_upper_one = re.sub(r"'[^']*'", "'X'", sql_upper)  # hide string literals

        # 1. DML check
        for kw in DANGEROUS_KEYWORDS:
            if kw in sql_upper_one:
                return False, f"Forbidden keyword '{kw}' in SQL — SELECT-only enforced.", sql

        # 2. Denied table check
        denied_found = [t for t in self.auth.denied_tables if re.search(rf"\b{t}\b", sql_upper, re.IGNORECASE)]
        if denied_found:
            return False, f"Tables not authorized for role {self.auth.role_id}: {', '.join(denied_found)}", sql

        # 3. MANDT injection (if not present and SAP_MANDT is configured)
        mandt = os.getenv("SAP_MANDT", "100")
        if not re.search(r"MANDT\s*=", sql_upper):
            # Try to inject after WHERE or before ORDER BY/LIMIT
            if re.search(r"\bWHERE\b", sql_upper, re.IGNORECASE):
                inject = f" AND MANDT = '{mandt}'"
                # Find first WHERE and inject there
                match = re.search(r"(\bWHERE\b)", sql_upper)
                pos = match.start()
                corrected = sql[:pos] + match.group(1) + inject + sql[pos + len(match.group(1)):]
            else:
                # No WHERE — append to end
                for suffix in [";", "LIMIT", "ORDER BY", "GROUP BY"]:
                    idx = sql_upper.rfind(suffix)
                    if idx != -1:
                        corrected = sql[:idx] + f" WHERE MANDT = '{mandt}' " + sql[idx:]
                        break
                else:
                    corrected = sql.rstrip().rstrip(";") + f" WHERE MANDT = '{mandt}';"
            return True, "MANDT auto-injected", corrected

        return True, None, sql


# =============================================================================
# Orchestrator — wires all 5 pillars together
# =============================================================================

class OrchestratorAgent:
    """
    Pillar 2: The Agentic Orchestrator.
    Coordinates all 5 Pillars:
      Pillar 1  → Auth context, SQL validation, result masking
      Pillar 2  → Intent analysis, LLM generation
      Pillar 3  → Schema RAG (Qdrant table lookup)
      Pillar 4  → SQL Pattern RAG (ChromaDB proven templates)
      Pillar 5  → Graph RAG (NetworkX FK JOIN path)
    """

    def __init__(self):
        self.intent_analyzer = IntentAnalyzer()
        self.sql_generator = SQLGenerator()
        self.mock_mode = os.getenv("MOCK_EXECUTION", "true").lower() != "false"

    def execute_rag_pipeline(self, query: str, domain: str, role_id: str) -> Dict[str, Any]:
        """
        Main agent loop. Returns a dict with sql, data, explanation, tables, masked.
        """
        # ── Pillar 1: Auth Context ───────────────────────────────────────────
        auth = security_mesh.get_context(role_id)
        print(f"[{auth.role_id}] Query: '{query}'")

        # ── Pillar 2: Intent Analysis ────────────────────────────────────────
        intent = self.intent_analyzer.analyze(query, domain if domain != "auto" else None)
        print(f"[{auth.role_id}] Intent: {intent.intent} | Domain: {intent.primary_domain}")

        # ── Pillar 3: Schema RAG (Qdrant) ──────────────────────────────────
        schemas = store_manager.search_schema(query, n_results=4, domain=intent.primary_domain)
        if not schemas:
            schemas = store_manager.search_schema(query, n_results=4, domain=None)
        safe_schemas = security_mesh.filter_schema_context(auth, schemas)
        tables_used = [s.get("metadata", {}).get("table") for s in safe_schemas]
        print(f"[{auth.role_id}] Schema RAG: {len(safe_schemas)}/{len(schemas)} tables authorized")

        if not safe_schemas:
            return {
                "sql": None,
                "data": None,
                "explanation": "No accessible tables found for your request. Your role may not have access to the required data domain.",
                "tables": [],
                "masked": [],
            }

        # ── Pillar 4: SQL Pattern RAG (ChromaDB) ────────────────────────────
        patterns = store_manager.search_sql_patterns(query, n_results=2, domain=intent.primary_domain)
        print(f"[{auth.role_id}] SQL Pattern RAG: {len(patterns)} patterns retrieved")

        # ── Pillar 5: Graph RAG (NetworkX) ──────────────────────────────────
        graph_info = ""
        if intent.needs_graph and len(tables_used) >= 2:
            path = graph_store.find_path(tables_used[0], tables_used[1])
            if path:
                subgraph = graph_store.get_subgraph_context(path)
                graph_info = f"Graph RAG path: {' → '.join(path)}"
                print(f"[{auth.role_id}] Graph RAG: {' → '.join(path)}")

        # ── LLM SQL Generation ───────────────────────────────────────────────
        raw_sql = self.sql_generator.generate(query, intent, safe_schemas, patterns, auth)
        print(f"[{auth.role_id}] Generated SQL: {raw_sql[:100]}")

        # ── Pillar 1: SQL Validation ─────────────────────────────────────────
        validator = SQLValidator(auth)
        is_safe, validation_msg, validated_sql = validator.validate(raw_sql)
        if not is_safe:
            return {
                "sql": None,
                "data": None,
                "explanation": f"SQL validation failed: {validation_msg}",
                "tables": tables_used,
                "masked": [],
            }
        if validation_msg:
            print(f"[{auth.role_id}] SQL Validation: {validation_msg}")

        # ── Row-level filter injection ───────────────────────────────────────
        scoped_sql = security_mesh.inject_row_level_filters(auth, validated_sql)

        # ── Execution (real or mock) ───────────────────────────────────────
        if self.mock_mode:
            data = self._mock_execute(scoped_sql, tables_used, intent)
        else:
            # TODO: wire real SAP HANA executor
            data = self._mock_execute(scoped_sql, tables_used, intent)

        # ── Pillar 1: Result Masking ─────────────────────────────────────────
        primary_table = tables_used[0]
        masked_data = security_mesh.mask_result_set(auth, primary_table, data)

        masked_fields = []
        if data and masked_data:
            for key in (data[0] or {}):
                if masked_data[0].get(key) == "REDACTED" and data[0].get(key) != "REDACTED":
                    masked_fields.append(f"{primary_table}.{key}")

        # ── Explanation ──────────────────────────────────────────────────────
        explanation = (
            f"I analyzed your question in the **{intent.primary_domain.replace('_', ' ').title()}** domain "
            f"({intent.intent} query). "
            f"{graph_info}. " if graph_info else ""
            f"Found {len(safe_schemas)} relevant tables ({', '.join(tables_used[:3])}). "
            f"{validation_msg + '. ' if validation_msg else ''}"
            f"Generated SQL uses your **{auth.role_id}** scope "
            f"(company codes: {', '.join(auth.allowed_company_codes) or 'all'}, "
            f"plants: {', '.join(auth.allowed_plants) or 'all'}). "
            f"{len(masked_fields)} sensitive field(s) redacted."
        )

        return {
            "sql": scoped_sql,
            "data": masked_data,
            "explanation": explanation,
            "tables": tables_used,
            "masked": masked_fields,
        }

    def _mock_execute(self, sql: str, tables: List[str], intent: IntentResult) -> List[Dict]:
        """Returns realistic mock data when no SAP HANA connection is available."""
        if intent.primary_domain == "business_partner":
            return [
                {"LIFNR": "1000", "NAME1": "Acme GmbH", "ORT01": "Berlin", "LAND1": "DE", "STCD1": "DE123456789", "BANKS": "DEUT"},
                {"LIFNR": "2000", "NAME1": "TechParts AG", "ORT01": "Munich", "LAND1": "DE", "STCD1": "DE987654321", "BANKS": "COBADEFF"},
            ]
        elif intent.primary_domain == "material_master":
            return [
                {"MATNR": "P-100-A", "MTART": "FERT", "MATKL": "001", "MEINS": "PC", "MTPOS_MARA": "NORM"},
                {"MATNR": "RM-200-B", "MTART": "ROH", "MATKL": "002", "MEINS": "KG", "MTPOS_MARA": "NORM"},
            ]
        elif intent.primary_domain == "purchasing":
            return [
                {"EBELN": "4500000001", "LIFNR": "1000", "BSTYP": "F", "MENGE": "500", "NETPR": "12.50", "WAERS": "USD"},
                {"EBELN": "4500000002", "LIFNR": "2000", "BSTYP": "F", "MENGE": "200", "NETPR": "85.00", "WAERS": "EUR"},
            ]
        elif intent.primary_domain == "sales_distribution":
            return [
                {"VBELN": "SD00000001", "KUNNR": "5000", "AUART": "OR", "NETWR": "12500.00", "WAERK": "USD", "ERDAT": "20260301"},
                {"VBELN": "SD00000002", "KUNNR": "5100", "AUART": "OR", "NETWR": "3400.00", "WAERK": "EUR", "ERDAT": "20260315"},
            ]
        else:
            return [{"TABLE": tables[0] if tables else "?", "SAMPLE": "Mock data — wire SAP HANA for real results"}]


# =============================================================================
# Module exports
# =============================================================================

agent = OrchestratorAgent()


async def query_master_data(query: str, domain: str, role: str) -> Dict[str, Any]:
    """
    FastAPI endpoint entry point.
    Called from app/api/endpoints/chat.py.
    """
    return agent.execute_rag_pipeline(query, domain, role)
