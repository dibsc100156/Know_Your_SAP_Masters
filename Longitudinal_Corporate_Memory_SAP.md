# Longitudinal Corporate Memory in SAP ERP
## Transforming 20 Years of Data into Predictive Wisdom

**Document Version:** 2.1
**Date:** 2026-04-04
**Phase Status:** Phase 7 Complete ✅ — Phase 8 Active
**System Reference:** `SAP_HANA_LLM_VendorChatbot` — Phase 6 Complete
**Authors:** Know Your SAP Masters Team

---

## What is Longitudinal Corporate Memory?

**Longitudinal Corporate Memory** is the continuous, historical record of everything a company has experienced, decided, and transacted over a long period of time.

In research, a "longitudinal" study tracks the same subjects over decades to see how they evolve. In business, Longitudinal Corporate Memory means tracking the complete lifecycle and behavior of your customers, vendors, assets, and processes across multiple eras, economic cycles, and crises.

The concept matters because **the average large enterprise has 20+ years of SAP data sitting in cold archives** — data that represents genuine accumulated wisdom about how the business actually operates. This data is not being used. The ERP is treated as a system of record, not a system of intelligence.

The breakthrough: when an **Agentic RAG system** (like Know Your SAP Masters) is applied to an SAP database with 20 years of history, that archive stops being a data graveyard and becomes a living, queryable corporate brain.

---

## The Problem: ERP as a "Data Graveyard"

Traditionally, SAP is used as a **System of Record**. It tells you:

- *What is happening right now* — inventory levels, open orders
- *What happened recently* — last quarter's revenue, this month's spend

Because traditional BI tools (SAP BW, Fiori dashboards) process structured data over short time horizons, data from 2005, 2010, or 2015 is largely ignored. It sits in cold storage for compliance and tax audits. It becomes a **data graveyard**.

**The cost of this graveyard:**

| Lost Knowledge | Business Impact |
|--------------|----------------|
| Why a buyer stopped using a vendor in 2012 | New buyers repeat the same mistake |
| Why a machine broke down every 8 years | Preventable failure costs millions |
| Which clients always churn when prices rise >4% | Negotiation leverage lost |
| Why a Z-table was created in 2007 | Clean-core migration paralyzed by unknown dependencies |

When a senior buyer retires, their tacit knowledge about *why* they stopped using a specific vendor retires with them. The ERP just shows that the Purchase Orders stopped. The *reason* is lost.

---

## The Transformation: From Archive to "Active Memory"

When modern AI (Agentic RAG + Graph RAG) is applied to an SAP database dating back to 2005, that data graveyard becomes a living, queryable brain. The SAP database stops being a tool that processes today's invoices and becomes **the most experienced "employee" in the company.**

The key insight: **20 years of SAP data is 20 years of accumulated corporate wisdom**, just waiting for an AI capable of reading it, connecting the dots across time, and speaking it back.

---

## The 4 Dimensions of Longitudinal Corporate Memory

### Dimension 1: The "Time-Series" Memory — Surviving Economic Cycles

Your SAP MM (Materials Management) data from 2005 has *lived* through:

- The **2008 Financial Crisis** — supply chain collapse, vendor defaults
- The **2011 European Debt Crisis** — currency volatility, payment term extensions
- The **2020 COVID-19 Pandemic** — demand volatility, freight chaos
- The **2022 Inflation Surge** — commodity price spikes, margin compression
- Multiple **regional recessions and currency crises**

**What this enables:**

```
QUERY: "Analyze our SAP MM data from 2008 to 2010.
Which raw material categories saw the highest default rates from suppliers
during the recession, and who were the backup vendors we pivoted to?"

LONGITUDINAL RESPONSE:
"The highest vendor default rates in 2008-2010 were in:
  Category: Electronic Components (LUMA, INFY)
  Primary vendors defaulted: 3 of 7 in our approved vendor list
  Average time-to-pivot: 47 days
  Backup vendor activated: AVNET (EMEA warehouse, activated March 2009)
  Lead-time impact: +22 days average on PCBs during pivot period
  Cost premium paid: +18% above pre-crisis pricing
  Recommendation: Maintain dual-sourcing for categories with >2 vendor defaults
  in any 3-year window. Currently under-sourced: Specialty Chemicals (CHEM-X)."
```

**Implementation in Know Your SAP Masters:**

The `TemporalGraphRAG` module (`backend/app/core/graph_store.py`) handles this:

```python
TEMPORAL_REGISTRY = {
    # Range-type: valid-from/to dates
    "EINA": {"type": "RANGE", "from_col": "DATAB", "to_col": "DATBI"},
    "EINE": {"type": "RANGE", "from_col": "DATAB", "to_col": "DATBI"},
    "LFA1": {"type": "RANGE", "from_col": "ERDAT", "to_col": None},

    # Fiscal year type: GJAHR + PERBL
    "COSP": {"type": "FISCAL", "year_col": "GJAHR", "period_col": "PERBL"},
    "COSS": {"type": "FISCAL", "year_col": "GJAHR", "period_col": "PERBL"},
    "BKPF": {"type": "FISCAL", "year_col": "GJAHR", "period_col": "MONAT"},

    # Key-date type: MBEW stock snapshots
    "MBEW": {"type": "KEY_DATE", "date_col": "BWDAT"},
}
```

For the 2008 query, the temporal filter generator produces:
```sql
WHERE EINA.DATAB <= '20080101'
  AND EINA.DATBI >= '20101231'
  AND BKPF.GJAHR BETWEEN '2008' AND '2010'
```

The **Meta-Path Library** (`backend/app/core/meta_path_library.py`) provides the cross-module JOIN paths needed to connect Purchasing → Finance → Vendor Master across a 3-year window:

```python
{
    "name": "procure_to_pay_temporal",
    "description": "P2P cycle across time period — for spend analysis",
    "path_variants": [
        "LFA1 → EKKO → EKPO → MSEG → MKPF → BKPF → BSEG",
        # Key date filters injected by temporal_graph module
    ],
    "temporal_complexity": "HIGH",
    "date_columns": {"EKKO": "AEDAT", "EKPO": "EBELP", "BKPF": "BUDAT", "BSEG": "BUDAT"},
}
```

**Future Enhancement (Phase 8):** Add macroeconomic event tagging — allow queries like "suppliers who defaulted within 90 days of a Fed rate hike cycle."

---

### Dimension 2: The "Asset Medical Record" — SAP PM/QM Across 20 Years

A manufacturing plant has turbines installed in 2006. Over 20 years, thousands of maintenance notifications, breakdown logs, and quality defects have been recorded in SAP PM (Plant Maintenance) and QM (Quality Management).

**The problem with conventional analysis:** Each breakdown is treated as an isolated incident. No one connects a vibration warning in 2026 to a similar text log written by a mechanic in 2009.

**The Longitudinal approach:** The AI treats every machine as a 20-year medical record.

```
QUERY: "A turbine bearing on line 3 is showing elevated vibration readings.
What does our SAP maintenance history say about this component over 20 years?"

LONGITUDINAL RESPONSE:
"Cross-referencing QM (notification QMs), PM (equipment history), and
invoice data (component replacements) from 2006-2026:

  2009: FIRST INCIDENT — bearing vibration warning, technician note:
    'Bearing B-2047 showing fatigue. Recommend replacement at next
    planned shutdown.' — Work order WO-2009-0892, not replaced.

  2012: SECOND INCIDENT — bearing replaced under emergency maintenance.
    Root cause identified: 'Insufficient lubrication interval, bearing
    operating 15°C above design temp.' — Countermeasures logged:
    'Increase lubrication frequency from quarterly to monthly.'

  2017: THIRD INCIDENT — same bearing position. Alignment issue found.
    Corrective action: 'Realigned coupling, replaced seals.'

  2021: FOURTH INCIDENT — bearing replaced electively during shutdown.
    Decision rationale: 'Based on 2012 root cause, replacing preventively
    every 9 years is optimal vs. emergency replacement cost of 4.2x.'

  CURRENT (2026): 'Bearing B-2047 showing vibration 3x baseline.'
    RECOMMENDATION: Replace within 60 days. Based on historical pattern,
    emergency replacement costs $180K vs. planned $42K.
    Historical survival after fourth incident: 2 of 2 turbines replaced
    within 6 months did not fail catastrophically."
```

**SAP Tables Involved:**
- `EQUI` — Equipment master (turbine + bearing as sub-equipment)
- `IFLOT` — Functional location hierarchy
- `IHPA` — Partner data (who reported each notification)
- `QMEL` — Quality notifications (text logs from mechanics)
- `QALS` — Inspection lots (vibration measurement results)
- `AFIH` — Maintenance order
- `VIQMEL` — QM notification long texts (the mechanic's actual notes)

**Implementation in Know Your SAP Masters:**

The `QMAgent` (`backend/app/agents/domain_agents.py`) handles QM-specific queries. Currently has 5 trigger keywords for routing: `quality`, `inspection`, `nonconformance`, `defect`, `certificate`.

**Gap to fill (Phase 8):** The QM agent does not yet use `QMEL-LONGTEXT` (long text fields containing mechanic notes) as a semantic search source. This is a key longitudinal insight layer — the text notes contain the *why* that structured fields don't capture.

**Future Enhancement:** Add `QMEL-LONGTEXT` embeddings to ChromaDB alongside structured fields. This turns 20 years of free-text maintenance logs into a searchable semantic memory.

---

### Dimension 3: The "Relationship Lifecycle" — 20 Years of Customer and Vendor Behavior

You have customers who have been buying from you since 2005. Over 20 years, your SAP database has recorded:

- Every discount they negotiated
- Every time they returned a defective product
- How their order volumes changed when you raised prices
- Which of your competitors they dual-sourced from
- Whether they paid on time or triggered dunning reminders

**The Negotiation Weapon:**

```
QUERY: "We're negotiating a 2026 contract with client ACME Corp.
What does 20 years of our SAP data tell us about their
price sensitivity and loyalty patterns?"

LONGITUDINAL RESPONSE:
"ACME Corp (KUNNR: 10000142) — 21-year relationship since January 2005.

PRICE INCREASE HISTORY:
  2010: +5% proposed → Client rejected → Volume dropped 8% for 2 quarters
         Resolution: +3% accepted, volume restored Q3 2011
  2014: +4% proposed → Client accepted without negotiation
         Context: They had inventory build-up due to their own demand surge
  2018: +6% proposed → Client threatened to dual-source
         Resolution: +3.5% accepted, but we matched competitor's lead time
         (competitor was KUNDAL — they switched for 2 quarters then returned)
  2022: +8% proposed → Accepted immediately
         Context: Global commodity spike — they understood market conditions

PRICE SENSITIVITY INDEX (PSI): 3.4 / 10 — LOW sensitivity
  Implication: They accept increases if accompanied by market context

RETURN RATE ANALYSIS:
  2005-2010: 2.3% return rate (industry avg: 3.1%)
  2011-2015: 4.7% return rate ( SPIKE — new product line introduced)
  2016-2020: 1.9% return rate (improved after quality program)
  2021-2025: 1.2% return rate (best-in-class)

PAYMENT BEHAVIOR:
  Average days-to-pay: 38 days (vs. contract 30 days)
  Dunning triggered: 3 times in 21 years (2009, 2015, 2020)
  All duned periods: recovered within 45 days

RECOMMENDATION FOR 2026 NEGOTIATION:
  Lead with: 'Market conditions require +5%, consistent with 2022 precedent'
  Do NOT: Lead with margin story — they care about supply reliability
  Offer: 7-day early payment discount to reduce dunning risk
  Expected outcome: Accepts +4-5% within 2 negotiation rounds"
```

**SAP Tables Involved:**
- `KNA1` — Customer master (general section)
- `KNVV` — Customer master (sales area) — payment terms per sales org
- `VBAP` / `VBAK` — Sales order history (20 years of order lines)
- `KONV` — Pricing conditions (every discount, every price increase negotiation)
- `LIKP` / `VBRK` — Deliveries and billing (returns data in LIKP-WBSTK)
- `BSID` — Open items (days-to-pay analysis)
- `QMEL` — Quality notifications from customer complaints

**Implementation in Know Your SAP Masters:**

The `SDAgent` handles Sales & Distribution queries. The `BPAgent` handles customer master queries.

The **temporal SQL filter** for a 20-year analysis:
```sql
-- 20-year customer behavior analysis
SELECT KNA1.KUNNR, KNA1.NAME1,
       VBAK.AUART, SUM(VBAP.NETWR) AS total_value,
       KONV.KSCHL, KONV.KBETR AS discount_pct,
       BSID.ZTERM, BSID.XBLNR AS invoice_ref
FROM KNA1
JOIN KNVV ON KNA1.KUNNR = KNVV.KUNNR
JOIN VBAK ON KNA1.KUNNR = VBAK.KUNNR
JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
LEFT JOIN KONV ON VBAK.KNUMV = KONV.KNUMV
LEFT JOIN BSID ON KNA1.KUNNR = BSID.KUNNR
WHERE VBAK.AUDAT >= '20050101'  -- 20 years of history
  AND VBAK.AUDAT <= '20251231'
  AND KNA1.KUNNR = '10000142'
  AND KONV.KSCHL IN ('KB01', 'PR00')  -- discounts and base price
GROUP BY KNA1.KUNNR, KNA1.NAME1, VBAK.AUDAT, VBAK.AUART,
         KONV.KSCHL, KONV.KBETR, BSID.ZTERM, BSID.XBLNR
ORDER BY VBAK.AUDAT
```

**Gap to fill (Phase 8):** The current system generates the SQL above, but the **natural language synthesis** layer doesn't yet produce the narrative negotiation briefing. This requires adding a "briefing generator" prompt to the SDAgent that synthesizes multi-decade data into strategic recommendations.

---

### Dimension 4: The "Why" Behind the Code — SAP Basis/ABAP Legacy Memory

A 20-year-old SAP system is full of custom tables (`Z*` tables), custom ABAP programs, and organizational workarounds created to solve business problems that no longer exist.

**The Clean-Core Migration Problem:**

During an S/4 HANA migration to clean-core, companies must decide:
- Which customizations are safe to delete?
- Which Z-tables contain data that must be migrated?
- Which ABAP programs are still called by active processes?

The answer is buried in:
- Old transport request texts (why was this created?)
- Help-desk tickets from 2012 (what problem did this solve?)
- ABAP code comments from 2007 (what business rule does this encode?)
- ITS (Internet Transaction Server) transaction links
- Legacy interface logs

**The Longitudinal Solution:**

```
QUERY: "We have a Z-table ZVENDOR_RATEADJ created in 2007.
What does our SAP system tell us about whether it's still active
and why it was created?"

LONGITUDINAL RESPONSE:
"ZVENDOR_RATEADJ — STATUS: LIKELY OBSOLETE (confidence: 87%)

CREATION CONTEXT:
  Created: March 14, 2007, by user JSMITH (John Smith, Procurement Dept)
  Transport: DEVK900123 — Transport text: 'Adj for FX rate diff on
  USD contracts — per email from CFO 2007-03-10'
  Related object: ABAP program RPCIPZR0 (exchange rate adjustment report)
  Original business need: Manual FX adjustment for USD-denominated
  vendor contracts before treasury hedging system was implemented in 2011

USAGE ANALYSIS:
  Last written to: December 23, 2011
  Last read by any transaction: March 2012
  Called by programs:
    - RPCIPZR0 (deactivated 2011, replaced by FK01SE/centralized treasury)
    - ZFX_ADJ_REPORT (no reference found since 2012)
  Referenced in user exits: None found
  ITS links: None

DECISION FOR CLEAN-CORE MIGRATION:
  SAFE TO DELETE:
    - ZVENDOR_RATEADJ table (no writes since Dec 2011)
    - ZFX_ADJ_REPORT program (orphan, no references)
  ARCHIVE but DO NOT DELETE:
    - RPCIPZR0 (documented legacy FX process — keep for audit trail)
  RELATED MIGRATION NOTE:
    Treasury hedging system (module TR) was go-live August 2011.
    This Z-table was a bridge solution for 4 years. Safe to retire."

Recommendation: Run deletion check on ZVENDOR_RATEADJ during
pre-migration audit. 87% confidence it has no active references."
```

**Implementation Gap:** This is the most complex dimension and is **not yet implemented** in the current system. It requires:

1. A **custom object scanner** that reads SAP system for Z* objects and their relationships
2. A **transport history reader** that pulls CTS (Change and Transport System) logs from SAP
3. A **program reference analyzer** that traces CALL FUNCTION and INCLUDE statements
4. A **usage history reader** that queries SAP S/4HANA's own usage analysis tables (if available)

This is a Phase 9+ feature.

---

## Implementation Architecture: How the System Works Today

The Know Your SAP Masters system implements a **5-Pillar Composite RAG Architecture** that forms the foundation for Longitudinal Corporate Memory:

```
User Query
    │
    ├─ [Pillar 0: Meta-Path Match] — 14 pre-defined temporal JOIN paths
    │   (procure-to-pay, order-to-cash, vendor_master_basic, etc.)
    │
    ├─ [Pillar 1: Role-Aware Security] — SAPAuthContext
    │   Row-level + column-level access control
    │   MANDT enforcement, company code filters, masked fields
    │
    ├─ [Pillar 2: Schema RAG] — ChromaDB
    │   80+ tables, semantic table discovery
    │   DDIC auto-discovery when RAG misses
    │
    ├─ [Pillar 3: SQL Pattern RAG] — 68 proven patterns
    │   Boosted by memory layer (pattern_success/failures tracking)
    │
    ├─ [Pillar 4: Graph RAG] — NetworkX + Node2Vec
    │   AllPathsExplorer: enumerate all JOIN paths between tables
    │   TemporalGraphRAG: date/fiscal/year filtering across time periods
    │   Graph Embeddings: structural scoring (hub/bridge/authority roles)
    │
    ├─ [Pillar 5: Supervisor + Domain Agents]
    │   7 specialist agents (BP, MM, PUR, SD, QM, WM, CROSS)
    │   Supervisor: SINGLE / PARALLEL / CROSS / FALLBACK routing
    │
    ├─ [Phase 4: Critique + Self-Heal]
    │   7-point SQL validation before execution
    │   10-rule autonomous SQL repair
    │
    ├─ [Phase 5: Memory + Eval]
    │   Persistent memory (query history, pattern rankings, gotchas)
    │   Eval dashboard with weekly trends
    │
    ├─ [Phase 6: Autonomous Loop]
    │   Self-improver: promote/demote patterns automatically
    │   Dialog manager: multi-turn clarification
    │
    └─ [Result] — Natural language answer + SQL + masked data + audit trail
```

---

## Current System: What's Implemented

### 1. Temporal RAG (Pillar 4 Extension)

Three temporal modes implemented in `TemporalGraphRAG`:

```python
# RANGE-type: vendor info records valid in a date range
# Query: "Which vendors were approved between Jan 2008 and Dec 2010?"
WHERE EINA.DATAB <= '20080101'
  AND EINA.DATBI >= '20101231'

# FISCAL-type: CO objects by fiscal year and period
# Query: "Show project costs for fiscal years 2020-2025 by quarter"
WHERE COSP.GJAHR BETWEEN '2020' AND '2025'
  AND COSP.PERBL = '12'  -- Q4

# KEY-DATE-type: material stock position as of a past date
# Query: "What was our stock position on March 15, 2020?"
WHERE MBEW.BWDAT = '20200315'  -- key date stock valuation
```

### 2. Pattern Library: The "Hoard" (68 Patterns)

Every proven SAP SQL pattern is stored in the hoard. The **Longitudinal dimension** here is that older patterns carry temporal validity:

```python
{
    "intent": "vendor_payment_terms_temporal",
    "description": "Vendor payment terms as they evolved over time",
    "tables": ["LFA1", "LFB1", "LFBK"],
    "example_queries": [
        "how did our payment terms with vendor LIFNR change over 10 years",
        "average payment terms by vendor category in 2015 vs 2025",
    ],
    "temporal_relevant": True,
    "fiscal_year_column": "LFB1-FAEDN",  # Due date as of fiscal period
}
```

### 3. Graph Store: The Relationship Memory (80+ Tables)

The NetworkX graph encodes the **structural relationships** between tables — this is the corporate memory of *which data is related to which*:

```python
# Cross-module bridge: vendor ↔ financial accounting ↔ material
"LFA1": {
    "domain": "business_partner",
    "structural_role": "hub",  # High centrality, connects BP ↔ FI ↔ MM
    "cross_module_edges": [
        ("LFA1", "EINA", "vendor_material"),    # Which materials from this vendor
        ("LFA1", "EKKO", "vendor_purchasing"),  # Vendor's POs
        ("LFA1", "BSIK", "vendor_open_items"),  # Vendor's AP line items
        ("LFA1", "LFB1", "vendor_company_code"), # Vendor per company code
    ],
    "temporal_columns": {"ERDAT", "STCDT"},
    "centrality_score": 0.91,  # Node2Vec hub score
}
```

### 4. Persistent Memory Layer: Learning from Every Query

Every query against the system is logged, creating a **meta-memory** about how the system itself has been used over time:

```python
# Query history record (query_history.jsonl)
{
    "timestamp": "2026-04-04T12:00:00Z",
    "query": "vendor default rates 2008 to 2010",
    "role": "CFO_GLOBAL",
    "domain": "purchasing",
    "sql_fingerprint": "a3f9c...",
    "tables_used": ["EINA", "EKKO", "LFA1", "BSIK"],
    "critique_score": 0.85,
    "result": "success",
    "execution_time_ms": 320,
    "temporal_mode": "FISCAL",  # System detected this was a temporal query
    "temporal_filters": ["GJAHR BETWEEN 2008 AND 2010"],
}
```

This meta-memory enables the system to learn:
- Which time ranges are most frequently queried
- Which vendor behaviors follow predictable cycles
- Which patterns fail in crisis periods vs. normal periods

---

## Roadmap: From Current System to Full Longitudinal Corporate Memory

### ✅ Phase 7 Complete: Temporal Depth Expansion (2026-04-04)

All Phase 7 items delivered in a single session. `backend/app/core/temporal_engine.py` — 1,100+ lines.

| Item | Module | Description |
|------|--------|-------------|
| **7.1 FiscalYearEngine** | `temporal_engine.py` | Multi-FY parsing, 4 calendar variants, FY comparison SQL |
| **7.2 TimeSeriesAggregator** | `temporal_engine.py` | MONTHLY/QUARTERLY/YEARLY granularity + rolling 3-period averages + period delta |
| **7.3 SupplierPerformanceIndex** | `temporal_engine.py` | Delivery reliability (EKKO/EKET/MSEG), Quality (QALS UD codes), Price competitiveness (EINA/EINE) |
| **7.4 CustomerLifetimeValueEngine** | `temporal_engine.py` | Revenue (VBAP-NETWR), Discount (KONV KB01/K007), Payment behavior (BSID vs KNVV-ZAHLS), Churn signals |
| **7.5 EconomicCycleTagger** | `temporal_engine.py` | 8 historical events with SQL comparison: 2008 crisis, 2011 Euro crisis, 2015 China, COVID-19, 2021 supply chain, 2022 inflation |
| **7.6 Orchestrator Wiring** | `orchestrator.py` | Step 2c: TemporalEngine fires when temporal/spend/supplier/CLV/crisis keywords detected |

### Phase 8 (Medium Term): Deep Vertical Integration

| Item | Description | Priority |
|------|-------------|---------|
| **8.1 QM Long-Text Semantic Search** | Embed `QMEL-LONGTEXT` and `VIQMEL` in ChromaDB — the mechanic's actual notes | P1 |
| **8.2 ABAP Code Comment Analyzer** | Read ABAP source from SAP system — extract business rule comments | P2 |
| **8.3 Transport History Reader** | Pull CTS logs from SAP — reconstruct *why* customizations were built | P2 |
| **8.4 Z-Table Usage Analyzer** | Automated dependency scan for Z* objects — support clean-core migration | P2 |
| **8.5 Negotiation Briefing Generator** | Synthesize 20-year KONV + VBAP + BSID into structured negotiation briefs | P2 |

### Phase 9 (Long Term): Predictive Corporate Memory

| Item | Description | Priority |
|------|-------------|---------|
| **9.1 Predictive Churn Model** | Predict which customers will reduce orders after a price increase | P2 |
| **9.2 Supplier Risk Scoring** | Composite default probability using EINA validity gaps + BSIK history | P2 |
| **9.3 Maintenance Prediction Engine** | Connect IHPA (who reported) + QMEL (what happened) + EQUI (which equipment) → predict next failure | P1 |
| **9.4 Cash Flow Forecasting** | Use BSID payment history + BSIK dunning triggers → 90-day cash flow projection | P2 |
| **9.5 Benchmark Intelligence** | Compare your metrics against anonymized industry peers (if data sharing agreement exists) | P3 |

---

## Technical Appendix: Key SAP Tables for Longitudinal Analysis

### Financial Transactions (Finance / Controlling)
| Table | Description | Longitudinal Value |
|-------|-------------|------------------|
| `BKPF` | Accounting document header | 20+ years of every financial transaction |
| `BSEG` | Accounting document line items | Vendor/customer payment behavior |
| `COSP` | Cost totals (plan/actual) | Project cost evolution over years |
| `COSS` | Cost line items (plan/actual) | Detailed cost element breakdown |
| `BSIK` | Vendor open items | Days-to-pay, dunning history |
| `BSID` | Customer open items | Collection history, credit risk |
| `ANLC` | Asset depreciation annual | Asset value evolution |

### Purchasing (MM-PUR)
| Table | Description | Longitudinal Value |
|-------|-------------|------------------|
| `EKKO` | PO header + creation date (AEDAT) | Vendor relationship start/end |
| `EKPO` | PO line items + delivery dates | Lead time trends per vendor |
| `EINA` | Info record (valid-from/to: DATAB/DATBI) | Vendor approval history over time |
| `EINE` | Info record (purchasing org level) | Pricing history per vendor/material |
| `MSEG` | Material document lines (BUDAT) | Goods movements — inventory trends |
| `MKPF` | Material document header | Transaction timestamps |

### Sales & Distribution
| Table | Description | Longitudinal Value |
|-------|-------------|------------------|
| `VBAK` | Sales order header (AUDAT = order date) | 20-year order history |
| `VBAP` | Sales order line items (NETWR) | Revenue and volume trends |
| `LIKP` | Delivery (WADAT = goods issue date) | Delivery reliability trends |
| `VBRK` | Billing (FKDAT = billing date) | Revenue recognition over time |
| `KONV` | Pricing conditions (KSCHL = condition type) | Discount negotiation history |
| `KNVV` | Customer master sales area (KDAGF = dunning key) | Payment behavior per customer |

### Plant Maintenance / Quality
| Table | Description | Longitudinal Value |
|-------|-------------|------------------|
| `EQUI` | Equipment master | Machine lifecycle |
| `IFLOT` | Functional locations | Plant hierarchy |
| `QMEL` | Quality notifications (long text in QMTXT) | Mechanic's actual notes — the "why" |
| `QALS` | Inspection lots (UDAT = usage decision date) | Quality trends over time |
| `AFIH` | Maintenance order | Work order history per asset |
| `IHPA` | Partner data (who reported) | Organizational knowledge retention |

---

## The Strategic Imperative

The companies that will dominate their industries in the 2030s are not the ones with the most data. They are the ones that have **learned the most from their data**.

Most enterprises have 15-25 years of SAP data that represents an enormous accumulated asset — the complete record of every business decision made, every supplier relationship, every customer interaction, every asset failure, every price negotiation, every crisis survived.

**The ERP is not a data graveyard. It is a 20-year corporate brain waiting to be awakened.**

The Know Your SAP Masters system is the architecture for awakening that brain. The 5-Pillar RAG system, the TemporalGraphRAG, the longitudinal meta-path library, and the self-improving memory layer are the technical foundation.

Every query the system processes adds to its Longitudinal Corporate Memory. Every pattern that succeeds is promoted. Every failure is buried. The system gets smarter with every interaction.

**The question is no longer whether this is possible. The question is how fast you can deploy it.**

---

*Document maintained by: Know Your SAP Masters System*
*Reference implementation: `SAP_HANA_LLM_VendorChatbot` — Phase 6 Complete*
*Simon Willison alignment: see `docs/WILLISON_VALIDATION.md`*
