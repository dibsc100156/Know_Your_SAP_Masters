"""
contracts.py — Typed Sub-Agent Output Contracts
==============================================
Every domain agent returns a strongly-typed Pydantic contract instead of a raw dict.
The Synthesis Agent validates the contract before merging — malformed outputs are
flagged (validation_passed=False) but never block synthesis.

Why contracts matter:
  - Schema violations are caught before merge, not after
  - Domain-specific field validation (e.g. PO must have net_value as float)
  - Synthesis can reason about data quality per agent
  - Enables failure attribution: which agent's contract failed and why

Usage:
    from app.agents.swarm.contracts import (
        AgentOutputContract, PURAgentContract,
        validate_contract, get_contract_for_agent,
    )
    contract = PURAgentContract.from_agent_result(agent_result_dict)
    is_valid, errors = validate_contract(contract)
    contract.validation_passed = is_valid
    contract.validation_errors = errors
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Type
from datetime import date, datetime
from enum import Enum

try:
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC_AVAILABLE = True
except ImportError:
    BaseModel = object  # type: ignore
    _PYDANTIC_AVAILABLE = False
    # Fake Field for non-pydantic environments
    def Field(self, *args, **kwargs):
        return None


# =============================================================================
# Enums
# =============================================================================

class ContractStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class SynthesisStatus(str, Enum):
    MERGED = "merged"
    PARTIAL = "partial"
    FAILED = "failed"


class EntityType(str, Enum):
    VENDOR = "vendor"
    CUSTOMER = "customer"
    UNKNOWN = "unknown"


# =============================================================================
# Base Contract
# =============================================================================

class AgentOutputContract(BaseModel if _PYDANTIC_AVAILABLE else object):
    """
    Base contract returned by every domain agent.
    All domain-specific contracts inherit from this.
    """

    agent_name: str = Field(description="Name of the agent that produced this output")
    run_id: str = Field(description="Harness run ID for traceability")
    status: ContractStatus = Field(description="Execution status")
    tables_used: List[str] = Field(default_factory=list, description="SAP tables accessed")
    executed_sql: str = Field(default="", description="SQL query that was executed")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="Raw result rows")
    record_count: int = Field(default=0, description="Number of records returned")
    execution_time_ms: int = Field(default=0, description="Execution duration")
    output_schema_version: str = Field(default="1.0")
    error_message: Optional[str] = Field(default=None)
    validation_passed: Optional[bool] = Field(default=None, description="Set by validator")
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors")

    if _PYDANTIC_AVAILABLE:

        @field_validator("status", mode="before")
        def _coerce_status(cls, v):
            if isinstance(v, str):
                return ContractStatus(v)
            return v

        @field_validator("data", mode="before")
        @classmethod
        def _coerce_data(cls, v):
            if not isinstance(v, list):
                return [v] if v else []
            return v

    def is_valid(self) -> bool:
        """True if no validation errors were recorded."""
        return bool(self.validation_passed)

    def to_summary_dict(self) -> Dict[str, Any]:
        """Compact dict for synthesis agent logging."""
        return {
            "agent_name": self.agent_name,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "record_count": self.record_count,
            "tables_used": self.tables_used,
            "validation_passed": self.validation_passed,
            "validation_errors": self.validation_errors,
        }


# =============================================================================
# Domain-Specific Contracts
# =============================================================================

class BPAgentContract(AgentOutputContract if _PYDANTIC_AVAILABLE else object):
    """
    Business Partner Agent contract.
    Tables: LFA1 (vendors), KNA1 (customers), BUT000 (business partners)
    Required per row: LIFNR (vendor_id) OR KUNNR (customer_id)
    Domain fields: entity_type, credit_limit, payment_terms
    """

    # Domain-specific typed fields
    vendor_count: int = Field(default=0, description="Count of vendor records")
    customer_count: int = Field(default=0, description="Count of customer records")
    entity_types_found: List[str] = Field(
        default_factory=list,
        description="Entity types detected: vendor, customer"
    )

    @classmethod
    def from_agent_result(cls, result: Dict[str, Any]) -> "BPAgentContract":
        """Build contract from raw agent result dict."""
        data = result.get("data", [])
        vendor_count = sum(1 for r in data if r.get("LIFNR"))
        customer_count = sum(1 for r in data if r.get("KUNNR"))
        entity_types = []
        if vendor_count > 0:
            entity_types.append("vendor")
        if customer_count > 0:
            entity_types.append("customer")

        return cls(
            agent_name=result.get("agent", "bp_agent"),
            run_id=result.get("run_id", ""),
            status=ContractStatus.SUCCESS if result.get("data") else ContractStatus.ERROR,
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql", ""),
            data=data,
            record_count=len(data),
            execution_time_ms=result.get("execution_time_ms", 0),
            error_message=result.get("error"),
            vendor_count=vendor_count,
            customer_count=customer_count,
            entity_types_found=entity_types,
        )

    def validate_output(self) -> Tuple[bool, List[str]]:
        """Validate BP-specific contract constraints."""
        errors = []

        # Check for entity IDs
        has_vendor = any(r.get("LIFNR") for r in self.data if isinstance(r, dict))
        has_customer = any(r.get("KUNNR") for r in self.data if isinstance(r, dict))
        if not has_vendor and not has_customer and self.record_count > 0:
            errors.append("No LIFNR or KUNNR found in any row — expected at least one entity ID field")

        # Check data is list of dicts
        if not all(isinstance(r, dict) for r in self.data):
            errors.append("data must be a list of dicts")

        return (len(errors) == 0, errors)


class MMAgentContract(AgentOutputContract if _PYDANTIC_AVAILABLE else object):
    """
    Material Master Agent contract.
    Tables: MARA (general material), MARC (plant data), MBEW (valuation)
    Required per row: MATNR (material_id)
    Domain fields: material_type, valuation_class, standard_price
    """

    material_count: int = Field(default=0)
    material_types_found: List[str] = Field(default_factory=list)

    @classmethod
    def from_agent_result(cls, result: Dict[str, Any]) -> "MMAgentContract":
        data = result.get("data", [])
        mat_count = sum(1 for r in data if isinstance(r, dict) and r.get("MATNR"))
        mat_types = list(set(
            r.get("MTART", "") for r in data if isinstance(r, dict) and r.get("MTART")
        ))

        return cls(
            agent_name=result.get("agent", "mm_agent"),
            run_id=result.get("run_id", ""),
            status=ContractStatus.SUCCESS if result.get("data") else ContractStatus.ERROR,
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql", ""),
            data=data,
            record_count=len(data),
            execution_time_ms=result.get("execution_time_ms", 0),
            error_message=result.get("error"),
            material_count=mat_count,
            material_types_found=mat_types,
        )

    def validate_output(self) -> Tuple[bool, List[str]]:
        errors = []
        has_material = any(
            r.get("MATNR") for r in self.data if isinstance(r, dict)
        )
        if not has_material and self.record_count > 0:
            errors.append("No MATNR found — expected material_id per row")
        if not all(isinstance(r, dict) for r in self.data):
            errors.append("data must be a list of dicts")
        return (len(errors) == 0, errors)


class PURAgentContract(AgentOutputContract if _PYDANTIC_AVAILABLE else object):
    """
    Purchasing Agent contract.
    Tables: EKKO (PO header), EKPO (PO item), EINE (info record)
    Required per row: EBELN (po_number)
    Domain fields: vendor_id, po_date, net_value, currency, open_qty
    """

    po_count: int = Field(default=0)
    total_po_value: float = Field(default=0.0)
    currencies_found: List[str] = Field(default_factory=list)
    vendor_ids_found: List[str] = Field(default_factory=list)

    @classmethod
    def from_agent_result(cls, result: Dict[str, Any]) -> "PURAgentContract":
        data = result.get("data", [])
        po_count = sum(1 for r in data if isinstance(r, dict) and r.get("EBELN"))

        total_value = 0.0
        currencies = set()
        vendors = set()
        for r in data:
            if isinstance(r, dict):
                val = r.get("NETWR") or r.get("DMBTR") or 0
                if isinstance(val, (int, float)):
                    total_value += val
                if r.get("WAERS"):
                    currencies.add(str(r.get("WAERS")))
                if r.get("LIFNR"):
                    vendors.add(str(r.get("LIFNR")))

        return cls(
            agent_name=result.get("agent", "pur_agent"),
            run_id=result.get("run_id", ""),
            status=ContractStatus.SUCCESS if result.get("data") else ContractStatus.ERROR,
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql", ""),
            data=data,
            record_count=len(data),
            execution_time_ms=result.get("execution_time_ms", 0),
            error_message=result.get("error"),
            po_count=po_count,
            total_po_value=round(total_value, 2),
            currencies_found=list(currencies),
            vendor_ids_found=list(vendors),
        )

    def validate_output(self) -> Tuple[bool, List[str]]:
        errors = []
        has_po = any(r.get("EBELN") for r in self.data if isinstance(r, dict))
        if not has_po and self.record_count > 0:
            errors.append("No EBELN found in any row — expected po_number per row")

        # Check net_value is numeric where present
        for i, r in enumerate(self.data[:10]):  # check first 10 rows
            if isinstance(r, dict) and "NETWR" in r:
                val = r["NETWR"]
                if val is not None and not isinstance(val, (int, float)):
                    errors.append(f"Row {i}: NETWR={val!r} is not numeric")

        if not all(isinstance(r, dict) for r in self.data):
            errors.append("data must be a list of dicts")

        return (len(errors) == 0, errors)


class SDAgentContract(AgentOutputContract if _PYDANTIC_AVAILABLE else object):
    """
    Sales & Distribution Agent contract.
    Tables: VBAK (sales header), VBAP (item), LIKP (delivery)
    Required per row: VBELN (sales_document)
    Domain fields: sold_to_party, net_value, order_status
    """

    order_count: int = Field(default=0)
    total_sales_value: float = Field(default=0.0)
    statuses_found: List[str] = Field(default_factory=list)

    @classmethod
    def from_agent_result(cls, result: Dict[str, Any]) -> "SDAgentContract":
        data = result.get("data", [])
        order_count = sum(1 for r in data if isinstance(r, dict) and r.get("VBELN"))
        total_val = sum(
            r.get("NETWR", 0) or 0
            for r in data if isinstance(r, dict)
            if isinstance(r.get("NETWR"), (int, float))
        )
        statuses = list(set(
            r.get("BSTDK", "") or r.get("LFDAT", "") or ""
            for r in data if isinstance(r, dict)
        ))

        return cls(
            agent_name=result.get("agent", "sd_agent"),
            run_id=result.get("run_id", ""),
            status=ContractStatus.SUCCESS if result.get("data") else ContractStatus.ERROR,
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql", ""),
            data=data,
            record_count=len(data),
            execution_time_ms=result.get("execution_time_ms", 0),
            error_message=result.get("error"),
            order_count=order_count,
            total_sales_value=round(total_val, 2),
            statuses_found=[s for s in statuses if s],
        )

    def validate_output(self) -> Tuple[bool, List[str]]:
        errors = []
        has_doc = any(r.get("VBELN") for r in self.data if isinstance(r, dict))
        if not has_doc and self.record_count > 0:
            errors.append("No VBELN found — expected sales_document per row")
        if not all(isinstance(r, dict) for r in self.data):
            errors.append("data must be a list of dicts")
        return (len(errors) == 0, errors)


class QMAgentContract(AgentOutputContract if _PYDANTIC_AVAILABLE else object):
    """
    Quality Management Agent contract.
    Tables: QALS (inspection lot), QMEL (notification), MAPL (task/object link)
    Required per row: QALS (inspection_lot)
    Domain fields: inspection_result, material_id, defect_code
    """

    inspection_lot_count: int = Field(default=0)
    defect_count: int = Field(default=0)
    result_types_found: List[str] = Field(default_factory=list)

    @classmethod
    def from_agent_result(cls, result: Dict[str, Any]) -> "QMAgentContract":
        data = result.get("data", [])
        lot_count = sum(1 for r in data if isinstance(r, dict) and r.get("QALS"))
        defect_count = sum(
            1 for r in data if isinstance(r, dict)
            and r.get("QMTYP") in ("1", "2", "3") or r.get("ERNAM") == "QA"
        )
        results = list(set(
            r.get("QSTATUS", "") or r.get("ART", "") or ""
            for r in data if isinstance(r, dict)
        ))

        return cls(
            agent_name=result.get("agent", "qm_agent"),
            run_id=result.get("run_id", ""),
            status=ContractStatus.SUCCESS if result.get("data") else ContractStatus.ERROR,
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql", ""),
            data=data,
            record_count=len(data),
            execution_time_ms=result.get("execution_time_ms", 0),
            error_message=result.get("error"),
            inspection_lot_count=lot_count,
            defect_count=defect_count,
            result_types_found=[r for r in results if r],
        )

    def validate_output(self) -> Tuple[bool, List[str]]:
        errors = []
        has_lot = any(r.get("QALS") for r in self.data if isinstance(r, dict))
        if not has_lot and self.record_count > 0:
            errors.append("No QALS found — expected inspection_lot per row")
        if not all(isinstance(r, dict) for r in self.data):
            errors.append("data must be a list of dicts")
        return (len(errors) == 0, errors)


class WMAgentContract(AgentOutputContract if _PYDANTIC_AVAILABLE else object):
    """
    Warehouse Management Agent contract.
    Tables: LAGP (storage bin), LQUA (quants), VEKP (handling unit)
    Required per row: LGNUM or LQUA storage unit
    Domain fields: warehouse_id, storage_location, stock_quantity
    """

    bin_count: int = Field(default=0)
    total_stock_qty: float = Field(default=0.0)

    @classmethod
    def from_agent_result(cls, result: Dict[str, Any]) -> "WMAgentContract":
        data = result.get("data", [])
        bin_count = sum(1 for r in data if isinstance(r, dict) and r.get("LAGP") or r.get("LGNUM"))
        total_qty = sum(r.get("LABST", 0) or 0 for r in data if isinstance(r, dict)
                        if isinstance(r.get("LABST"), (int, float)))

        return cls(
            agent_name=result.get("agent", "wm_agent"),
            run_id=result.get("run_id", ""),
            status=ContractStatus.SUCCESS if result.get("data") else ContractStatus.ERROR,
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql", ""),
            data=data,
            record_count=len(data),
            execution_time_ms=result.get("execution_time_ms", 0),
            error_message=result.get("error"),
            bin_count=bin_count,
            total_stock_qty=round(total_qty, 2),
        )

    def validate_output(self) -> Tuple[bool, List[str]]:
        errors = []
        has_bin = any(
            r.get("LAGP") or r.get("LGNUM")
            for r in self.data if isinstance(r, dict)
        )
        if not has_bin and self.record_count > 0:
            errors.append("No LAGP or LGNUM found — expected storage bin per row")
        if not all(isinstance(r, dict) for r in self.data):
            errors.append("data must be a list of dicts")
        return (len(errors) == 0, errors)


class CROSSAgentContract(AgentOutputContract if _PYDANTIC_AVAILABLE else object):
    """
    Cross-Module Agent contract.
    Tables: dynamically resolved from graph traversal
    Required per row: at least one entity ID field (LIFNR, MATNR, EBELN, VBELN, KUNNR, QALS)
    Domain fields: involved_tables, cross_domain_score
    """

    entity_types_crossed: List[str] = Field(default_factory=list)
    cross_domain_score: float = Field(default=0.0, description="0.0–1.0, higher = more cross-domain")

    @classmethod
    def from_agent_result(cls, result: Dict[str, Any]) -> "CROSSAgentContract":
        data = result.get("data", [])
        entity_fields = ["LIFNR", "MATNR", "EBELN", "VBELN", "KUNNR", "QALS", "BELNR"]
        found_entities = set()
        for r in data:
            if isinstance(r, dict):
                for ef in entity_fields:
                    if r.get(ef):
                        found_entities.add(ef)

        # Cross-domain score: more entity types = higher score
        num_entity_types = len(found_entities)
        cross_score = min(num_entity_types / 3.0, 1.0) if num_entity_types > 0 else 0.0

        return cls(
            agent_name=result.get("agent", "cross_agent"),
            run_id=result.get("run_id", ""),
            status=ContractStatus.SUCCESS if result.get("data") else ContractStatus.ERROR,
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql", ""),
            data=data,
            record_count=len(data),
            execution_time_ms=result.get("execution_time_ms", 0),
            error_message=result.get("error"),
            entity_types_crossed=list(found_entities),
            cross_domain_score=cross_score,
        )

    def validate_output(self) -> Tuple[bool, List[str]]:
        errors = []
        # Cross-agent should have multiple table references
        if len(self.tables_used) < 2 and self.record_count > 0:
            errors.append(
                f"Cross-agent returned data from only {len(self.tables_used)} table(s) — "
                "expected at least 2 different tables for cross-module work"
            )
        if not all(isinstance(r, dict) for r in self.data):
            errors.append("data must be a list of dicts")
        return (len(errors) == 0, errors)


# =============================================================================
# Swarm Output Contract (Synthesis Agent result)
# =============================================================================

class SWARMOutputContract(BaseModel if _PYDANTIC_AVAILABLE else object):
    """
    Contract returned by the Synthesis Agent — the parent output of the swarm.
    Aggregates all domain agent outputs with merge metadata.
    """

    run_id: str
    swarm_routing: str = Field(description="single | parallel | cross_module | negotiation | escalated")
    planner_reasoning: str
    complexity_score: float
    agent_count: int
    synthesis_status: SynthesisStatus = Field(description="merged | partial | failed")
    merged_data: List[Dict[str, Any]] = Field(default_factory=list)
    total_records: int = Field(default=0)
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    domain_coverage: List[str] = Field(default_factory=list)
    agent_outputs: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="agent_name -> contract summary dict"
    )
    execution_time_ms: int = Field(default=0)
    output_schema_version: str = Field(default="1.0")
    validation_passed: Optional[bool] = Field(default=None)

    if _PYDANTIC_AVAILABLE:

        @field_validator("synthesis_status", mode="before")
        @classmethod
        def _coerce_status(cls, v):
            if isinstance(v, str):
                return SynthesisStatus(v)
            return v

        @field_validator("agent_outputs", mode="before")
        @classmethod
        def _coerce_outputs(cls, v):
            if not isinstance(v, dict):
                return {}
            # Ensure all values are dicts
            return {k: v2 for k, v2 in v.items() if isinstance(v2, dict)}

    def is_valid(self) -> bool:
        return self.synthesis_status in (SynthesisStatus.MERGED, SynthesisStatus.PARTIAL)


# =============================================================================
# Contract Registry + Factory
# =============================================================================

# Maps agent_name -> contract class
AGENT_CONTRACT_REGISTRY: Dict[str, Type["AgentOutputContract"]] = {
    "bp_agent": BPAgentContract,
    "mm_agent": MMAgentContract,
    "pur_agent": PURAgentContract,
    "sd_agent": SDAgentContract,
    "qm_agent": QMAgentContract,
    "wm_agent": WMAgentContract,
    "cross_agent": CROSSAgentContract,
}


def get_contract_for_agent(agent_name: str) -> Type["AgentOutputContract"]:
    """Return the contract class for a given agent name."""
    return AGENT_CONTRACT_REGISTRY.get(
        agent_name,
        AgentOutputContract  # fallback to base contract
    )


def build_contract(agent_name: str, agent_result: Dict[str, Any]) -> "AgentOutputContract":
    """
    Factory function — build the appropriate contract from an agent result dict.
    Used by domain agents at the end of their run().
    """
    contract_cls = get_contract_for_agent(agent_name)
    contract = contract_cls.from_agent_result(agent_result)
    # Run validation
    is_valid, errors = contract.validate_output()
    contract.validation_passed = is_valid
    contract.validation_errors = errors
    if not is_valid:
        contract.status = ContractStatus.PARTIAL
    return contract


# =============================================================================
# Contract Validator (called by Synthesis Agent before merge)
# =============================================================================

def validate_contract(contract: AgentOutputContract) -> Tuple[bool, List[str]]:
    """
    Top-level validator — called by SynthesisAgent before merging.

    Returns (is_valid, list_of_errors).
    Validation errors do NOT block synthesis — they flag the output as
    validation_passed=False so the synthesis can log/report the issue.
    """
    errors = []

    # Base checks
    if not isinstance(contract.data, list):
        errors.append(f"data must be a list, got {type(contract.data).__name__}")
        return (False, errors)

    if contract.record_count != len(contract.data):
        errors.append(
            f"record_count ({contract.record_count}) != actual data length ({len(contract.data)})"
        )

    if contract.record_count > 0 and not contract.data:
        errors.append("record_count > 0 but data is empty")

    # Agent-specific validation
    if hasattr(contract, "validate_output"):
        domain_valid, domain_errors = contract.validate_output()
        errors.extend(domain_errors)

    # SQL safety check — no DML/DDL
    sql_upper = contract.executed_sql.upper()
    dangerous_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
    for kw in dangerous_keywords:
        if kw in sql_upper:
            errors.append(f"Dangerous SQL keyword '{kw}' detected in executed_sql — must be SELECT only")

    return (len(errors) == 0, errors)
