"""
Know Your SAP Masters — Modernized Frontend v2
===============================================
Full 8-phase orchestration visibility:
  - Multi-signal confidence score with per-signal breakdown
  - Phase 7 temporal analysis (SPI, CLV, FY, Economic Cycle)
  - Phase 8 panels (QM Semantic, Negotiation Intelligence)
  - Pillar activation map
  - Routing path + pattern name
  - Enhanced tool trace with step numbers
  - Self-heal, critique, masked fields — all prominent

Run:  streamlit run frontend/app.py
Requires: backend running on localhost:8000
"""

import streamlit as st
import requests
import pandas as pd
import time

from monitoring_panel import render_monitoring_panel

API_BASE = "http://localhost:8000"
API_URL = f"{API_BASE}/api/v1/chat/master-data"

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="Know Your SAP Masters",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# CUSTOM CSS
# ============================================================================

st.markdown("""
<style>
    /* ── Role badges ── */
    .role-AP_CLERK              { background:#d4edda; color:#155724; padding:4px 10px; border-radius:6px; font-weight:600; }
    .role-PROCUREMENT_MANAGER_EU{ background:#cce5ff; color:#004085; padding:4px 10px; border-radius:6px; font-weight:600; }
    .role-CFO_GLOBAL            { background:#fff3cd; color:#856404; padding:4px 10px; border-radius:6px; font-weight:600; }
    .role-HR_ADMIN              { background:#f8d7da; color:#721c24; padding:4px 10px; border-radius:6px; font-weight:600; }

    /* ── Confidence grade ── */
    .conf-high   { background:#d4edda; color:#155724; padding:8px 18px; border-radius:20px; font-weight:700; font-size:1.1em; display:inline-block; }
    .conf-medium { background:#fff3cd; color:#856404; padding:8px 18px; border-radius:20px; font-weight:700; font-size:1.1em; display:inline-block; }
    .conf-low    { background:#f8d7da; color:#721c24; padding:8px 18px; border-radius:20px; font-weight:700; font-size:1.1em; display:inline-block; }

    /* ── Routing path badges ── */
    .route-fast      { background:#d4edda; color:#155724; padding:3px 10px; border-radius:10px; font-weight:600; }
    .route-cross     { background:#cce5ff; color:#004085; padding:3px 10px; border-radius:10px; font-weight:600; }
    .route-standard  { background:#f8f9fa; color:#495057; padding:3px 10px; border-radius:10px; font-weight:600; border:1px solid #dee2e6; }

    /* ── Negotiation card ── */
    .neg-card { background:#0d1b2a; color:#e0e1dd; border-radius:12px; padding:20px; border:1px solid #1b3a4b; }

    /* ── Tool trace ── */
    .tt-row { padding:5px 0 5px 12px; border-left:3px solid #dee2e6; margin:2px 0; font-size:0.85em; }
    .tt-ok  { border-left-color:#2a9d8f; }
    .tt-skip{ border-left-color:#e9c46a; }
    .tt-err { border-left-color:#e76f51; }
    .tt-ph  { color:#888; font-size:0.9em; }

    /* ── Pillar activation ── */
    .pillar-active   { background:#d4edda; color:#155724; padding:3px 8px; border-radius:8px; font-weight:600; font-size:0.85em; }
    .pillar-inactive { background:#f8f9fa; color:#adb5bd; padding:3px 8px; border-radius:8px; font-size:0.85em; }
    .pillar-label    { font-size:0.75em; color:#888; margin-top:2px; }

    /* ── Self-heal ── */
    .heal-banner { background:#fff3cd; border:1px solid #ffc107; border-radius:8px; padding:10px 16px; color:#856404; }

    /* ── Temporal ── */
    .temp-active { background:#ede7f6; color:#4527a0; padding:3px 10px; border-radius:12px; font-size:0.85em; font-weight:600; }
    .temp-none   { background:#f8f9fa; color:#adb5bd; padding:3px 10px; border-radius:12px; font-size:0.85em; }

    /* ── QM ── */
    .qm-chip { background:#e8f5e9; color:#2e7d32; padding:3px 10px; border-radius:12px; font-size:0.85em; font-weight:600; }

    /* ── Critique ── */
    .crit-pass { background:#d4edda; border-radius:8px; padding:10px; }
    .crit-fail { background:#f8d7da; border-radius:8px; padding:10px; }

    /* ── Phase 7 SPI ── */
    .spi-card { background:#0d1b2a; color:#e0e1dd; border-radius:10px; padding:16px; border:1px solid #1b3a4b; }
    .spi-grade { font-size:1.6em; font-weight:800; }
    .spi-delivery { color:#2a9d8f; }
    .spi-quality  { color:#e9c46a; }
    .spi-price    { color:#ef476f; }

    /* ── Confidence signals table ── */
    .sig-table { width:100%; border-collapse:collapse; font-size:0.85em; }
    .sig-table th { text-align:left; padding:4px 8px; background:#f8f9fa; border-bottom:2px solid #dee2e6; }
    .sig-table td { padding:4px 8px; border-bottom:1px solid #f1f3f4; }
    .sig-bar-bg { background:#e9ecef; border-radius:4px; height:8px; width:100%; }
    .sig-bar-fill { border-radius:4px; height:8px; }

    /* ── Footer ── */
    .exec-footer { color:#aaa; font-size:0.8em; text-align:right; margin-top:4px; }

    /* ── Pattern badge ── */
    .pattern-badge { background:#fce4ec; color:#880e4f; padding:3px 10px; border-radius:8px; font-weight:600; font-family:monospace; }

    /* ── Swarm badge ── */
    .swarm-badge { background:#e8f5e9; color:#1b5e20; padding:3px 10px; border-radius:10px; font-weight:700; font-size:0.9em; border:1px solid #2e7d32; }

    /* ── Section headers ── */
    .section-hdr { font-size:0.75em; color:#888; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown("### 🔐 Security Context")
    st.caption("Simulates SAP Authorization Objects — row-level scope + column masking.")

    role = st.selectbox(
        "User Persona",
        ["AP_CLERK", "PROCUREMENT_MANAGER_EU", "CFO_GLOBAL", "HR_ADMIN"],
        help="AP Clerk is restricted from HR/Valuation. CFO sees all. HR Admin sees HR only."
    )

    role_meta = {
        "AP_CLERK":               ("Accounts Payable Clerk — US Operations", ["1000", "1010"]),
        "PROCUREMENT_MANAGER_EU": ("Procurement Manager — Europe", ["2000", "2010"]),
        "CFO_GLOBAL":             ("Global Chief Financial Officer", ["* ALL *"]),
        "HR_ADMIN":               ("Human Resources Administrator", ["* ALL *"]),
    }
    role_desc, role_bukrs = role_meta[role]
    st.markdown(f"**{role}**")
    st.caption(f"_{role_desc}_")
    st.markdown(f"🏢 `{', '.join(role_bukrs)}`")

    st.divider()

    domain = st.selectbox(
        "Routing Domain",
        [
            "auto",
            "business_partner",
            "material_master",
            "purchasing",
            "sales_distribution",
            "warehouse_management",
            "quality_management",
            "financial_accounting",
            "project_system",
            "transportation",
            "customer_service",
            "ehs",
            "variant_configuration",
            "real_estate",
            "gts",
            "is_oil",
            "is_retail",
            "is_utilities",
            "is_health",
            "taxation_india",
            "cross_module",
        ],
        index=0,
        help="Leave on 'auto' for 8-phase Graph RAG routing."
    )

    st.divider()

    if st.button("🗑 Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        import uuid
        st.session_state.session_id = f"st-{uuid.uuid4().hex[:12]}"
        st.rerun()

    st.divider()
    st.caption(f"**Backend:** `{API_BASE}`")
    st.caption("**8 Phases:** Security → Orchestrator → Schema RAG → SQL Pattern → Graph RAG → Temporal Engine → QM Semantic → Negotiation")

# ============================================================================

# ============================================================================

# ============================================================================
# HELPER — Trajectory Log Panel
# ============================================================================

def render_trajectory_log(traj_log: list):
    """Render the recorded reasoning span log as an expandable timeline."""
    if not traj_log:
        return

    st.markdown("#### 🧠 Trajectory Log")
    for i, event in enumerate(traj_log):
        step = event.get("step", "?")
        decision = event.get("decision", "?")
        reasoning = event.get("reasoning", "?")
        meta = event.get("metadata", {})
        ts = event.get("timestamp", "")

        icon = "🔀" if "planner" in step else "⚙️"
        with st.expander(f"{icon} [{i+1}] {step} → {decision}"):
            st.caption(f"__{ts}__" if ts else "")
            st.markdown(f"**Reasoning:** {reasoning}")
            if meta:
                st.json(meta)

# HELPER — Quality Metrics Panel
# ============================================================================

def render_quality_metrics_panel(metrics: dict):
    """Render the Quality Metrics computed from HarnessRuns execution traces."""
    if not metrics:
        return
        
    correctness = metrics.get("correctness_score", 0.0)
    adherence = metrics.get("trajectory_adherence", 0.0)
    
    st.markdown("#### 🛡️ Run Quality Metrics")
    c1, c2 = st.columns(2)
    
    with c1:
        st.metric("Correctness Score", f"{correctness:.2f}")
        st.progress(correctness)
        st.caption("Derived from confidence, penalizing sentinel blocks and failed phases.")
        
    with c2:
        st.metric("Trajectory Adherence", f"{adherence:.2f}")
        st.progress(adherence)
        st.caption("Measures phase sequence stability (penalizes backtracking/healing).")

# HELPER — Confidence Score Panel
# ============================================================================

def render_confidence_panel(cs: dict):
    """Render the full multi-signal confidence breakdown."""
    if not cs:
        return

    composite = cs.get("composite", 0)
    grade = cs.get("grade", "—")
    signals = cs.get("signals", {})
    row_count = cs.get("row_count", 0)
    exec_ms = cs.get("execution_time_ms", 0)
    critique_raw = cs.get("critique_raw", 0)

    # Grade badge
    cls = f"conf-{grade.lower()}"
    grade_icon = "🟢" if grade == "HIGH" else "🟡" if grade == "MEDIUM" else "🔴"

    st.markdown("---")
    st.markdown("#### 📊 Confidence Score")

    # ── Composite + grade ───────────────────────────────────────────────────
    col_grad, col_meta = st.columns([1, 2])

    with col_grad:
        st.markdown(f"<span class='{cls}'>{grade_icon} {grade} ({composite:.0%})</span>", unsafe_allow_html=True)
        st.markdown("**Composite Score**")
        # ASCII gauge
        filled = int(composite * 10)
        bar = "█" * filled + "░" * (10 - filled)
        st.markdown(f"`[{bar}]` {composite:.1%}")

    with col_meta:
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric("Row Count", f"{row_count}")
        with kpi2:
            st.metric("Critique", f"{critique_raw}/7")
        with kpi3:
            st.metric("Exec Time", f"{exec_ms}ms")

    # ── Per-signal breakdown table ──────────────────────────────────────────
    st.markdown("**Signal Breakdown**")

    sig_rows = []
    for key, sig in signals.items():
        weight = sig.get("weight", 0)
        score = sig.get("score", 0)
        label = sig.get("label", key)
        detail = sig.get("detail", "")
        bar_pct = int(score * 100)
        bar_color = "#2a9d8f" if score >= 0.8 else "#e9c46a" if score >= 0.6 else "#e76f51"

        sig_rows.append({
            "Signal": label,
            "Weight": f"{weight:.0%}",
            "Score": f"{score:.0%}",
            "Contribution": f"{sig.get('weighted', 0):.0%}",
            "Bar": bar_pct,
            "Bar Color": bar_color,
            "Detail": detail,
        })

    df_sig = pd.DataFrame(sig_rows)

    # Render as HTML table with inline bar
    bar_html = """
    <table class="sig-table">
    <tr>
        <th>Signal</th><th>Wt</th><th>Scr</th><th>×Wt</th><th style="width:40%">Score Bar</th><th>Detail</th>
    </tr>
    """
    for _, r in df_sig.iterrows():
        bar_block = f"""
        <div class="sig-bar-bg">
            <div class="sig-bar-fill" style="width:{r['Bar']}%; background:{r['Bar Color']};"></div>
        </div>"""
        bar_html += f"<tr><td><b>{r['Signal']}</b></td><td>{r['Weight']}</td><td>{r['Score']}</td><td>{r['Contribution']}</td><td>{bar_block}</td><td style='color:#888;font-size:0.8em'>{r['Detail']}</td></tr>"
    bar_html += "</table>"
    st.markdown(bar_html, unsafe_allow_html=True)


# ============================================================================
# HELPER — Pillar Activation Map
# ============================================================================

def render_pillar_map(tool_trace: list, routing_path: str, temporal_mode: str,
                       qm_count: int, negotiation_brief: dict):
    """Render which of the 8 phases fired for this query."""
    st.markdown("**Pillar Activation Map**")

    # Determine which pillars fired
    pillar_names = [
        ("P1", "Security\nValidate/Mask"),
        ("P2", "Orchestrator"),
        ("P3", "Schema RAG"),
        ("P4", "SQL Pattern"),
        ("P5", "Graph RAG"),
        ("P7", "Temporal\nEngine"),
        ("P8a", "QM\nSemantic"),
        ("P8b", "Negot.\nBrief"),
    ]

    active_tools = {t.get("tool", "") for t in (tool_trace or [])}

    def is_active(p_num: str, indicators: list) -> bool:
        return any(ind.lower() in " ".join(active_tools).lower() or
                   any(ind.lower() in t.lower() for t in active_tools)
                   for ind in indicators)

    p1_active = any(t in active_tools for t in ["sql_validate", "result_mask"])
    p3_active = "schema_lookup" in active_tools or "schema_rag" in [t.get("tool","") for t in tool_trace or []]
    p4_active = "sql_pattern_lookup" in active_tools or "sql_retrieve" in active_tools
    p5_active = any(t in active_tools for t in ["graph_traverse", "all_paths_explore",
                                                  "graph_enhanced_schema", "temporal_graph_search"])
    p7_active = temporal_mode and temporal_mode != "none"
    p8a_active = qm_count and qm_count > 0
    p8b_active = negotiation_brief is not None

    active_map = [p1_active, True, p3_active, p4_active, p5_active, p7_active, p8a_active, p8b_active]

    cols = st.columns(8)
    for idx, (col, (p_num, p_label), active) in enumerate(zip(cols, pillar_names, active_map)):
        with col:
            cls = "pillar-active" if active else "pillar-inactive"
            icon = "✅" if active else "○"
            st.markdown(f"<div class='{cls}'>{icon} <b>{p_num}</b><div class='pillar-label'>{p_label}</div></div>",
                       unsafe_allow_html=True)


# ============================================================================
# HELPER — Phase 7 Temporal Analysis
# ============================================================================

def render_phase7_panel(temporal: dict):
    """Render Phase 7 temporal engine analysis (SPI, CLV, FY, Economic Cycle)."""
    if not temporal:
        return

    phase7 = temporal.get("phase7_analysis", {})
    mode = temporal.get("mode", "none")
    filters = temporal.get("filters", [])

    if mode == "none" and (not phase7 or phase7.get("type") == "none"):
        return

    st.markdown("---")
    st.markdown("#### 📅 Phase 7: Temporal Analysis")

    # Mode chip
    mode_chip = f"<span class='temp-active'>{mode.upper()}</span>" if mode != "none" else "<span class='temp-none'>NONE</span>"
    st.markdown(f"**Mode:** {mode_chip}", unsafe_allow_html=True)

    # Filters
    if filters:
        chips = " &nbsp; ".join([f"<span class='temp-active'>{f}</span>" for f in filters])
        st.markdown(f"**Filters applied:** {chips}", unsafe_allow_html=True)

    # Phase 7 analysis content
    p7_type = phase7.get("type", "none")
    if p7_type == "none":
        return

    st.markdown(f"**Analysis type:** `{p7_type}`")

    if p7_type == "supplier_performance":
        # SPI: delivery rate, quality rate, price index, composite
        spi = phase7
        vendor_id = spi.get("vendor_id", "?")
        st.markdown(f"**Vendor:** `{vendor_id}`")
        # Composite from SPI
        # Note: in mock mode these won't have real values
        st.json(spi)

    elif p7_type == "clv":
        clv = phase7
        cust_id = clv.get("customer_id", "?")
        st.markdown(f"**Customer:** `{cust_id}`")
        st.json(clv)

    elif p7_type == "fiscal_year":
        fy_range = phase7.get("fy_range", {})
        granularity = phase7.get("granularity", "?")
        st.markdown(f"**FY Range:** `{fy_range.get('label', fy_range)}` | **Granularity:** `{granularity}`")
        st.json(phase7)

    elif p7_type == "economic_cycle":
        events = phase7.get("events_found", [])
        st.markdown(f"**Macro events detected:** {len(events)}")
        for ev in events[:5]:
            st.markdown(f"- **{ev.get('name','?')}** ({ev.get('period','?')})")

    else:
        # Generic — just show the dict
        st.json(phase7)


# ============================================================================
# HELPER — Negotiation Card (dark card)
# ============================================================================

def render_negotiation_card(brief: dict):
    if not brief:
        return

    tier = brief.get("clv_tier", "—")
    psi = brief.get("price_sensitivity_index", 0)
    churn = brief.get("churn_risk", "—")
    tactics = brief.get("top_tactics", [])
    batna = brief.get("batna", "—")
    batna_str = brief.get("batna_strength", 0)
    bottom = brief.get("bottom_line", "")
    rec_inc = brief.get("recommended_increase_pct", 0)
    max_inc = brief.get("max_acceptable_increase_pct", 0)
    rev_20yr = brief.get("total_revenue_20yr", 0)
    rev_5yr = brief.get("revenue_trend_5yr", 0)
    pay_score = brief.get("payment_reliability_score", 0)
    churn_ev = brief.get("churn_evidence", [])
    entity = brief.get("entity_name", brief.get("entity_id", "?"))

    st.markdown("---")
    st.markdown("#### 🎯 Negotiation Intelligence")

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("CLV Tier", tier)
    k2.metric("PSI", f"{psi:.1f}/10")
    k3.metric("Payment", f"{pay_score:.0f}/100")
    k4.metric("Churn", churn)

    k5, k6 = st.columns(2)
    k5.markdown(f"**20yr Revenue:** `${rev_20yr:,.0f}`")
    k6.markdown(f"**5yr CAGR:** `{'+' if rev_5yr > 0 else ''}{rev_5yr:.1f}%`")

    k7, k8 = st.columns(2)
    k7.markdown(f"**✅ Recommend:** `{rec_inc:+.1f}%`")
    k8.markdown(f"**🔒 Accept min:** `{max_inc:+.1f}%`")

    if tactics:
        st.markdown("**Top Tactics:**")
        st.markdown(" &nbsp; ".join([f"`{t}`" for t in tactics[:4]]), unsafe_allow_html=True)

    st.markdown(f"**BATNA:** {batna} _(strength: {batna_str:.0f}/10)_")
    if bottom:
        st.info(f"💡 *{bottom}*")

    if churn_ev:
        with st.expander("⚠️ Churn Risk Evidence"):
            for e in churn_ev:
                st.markdown(f"- {e}")


# ============================================================================
# HELPER — QM Semantic Panel
# ============================================================================

def render_graph_scores_panel(graph_scores: list):
    if not graph_scores:
        return

    st.markdown("---")
    st.markdown("#### 🕸️ Graph Embedding Structural Discovery (Phase 5½)")
    st.caption("Node2Vec graph embeddings fusion. Surfaces tables acting as cross-module hubs.")

    for row in graph_scores[:5]:
        tbl = row.get("table", "?")
        mod = row.get("domain", "?")
        role = row.get("structural_role", "?")
        bridge = row.get("is_cross_module_bridge", False)
        comp = row.get("composite_score", 0.0)
        struct = row.get("structural_score", 0.0)
        text = row.get("text_score", 0.0)
        
        bridge_badge = "<span style='background-color:#ffebee;color:#c62828;padding:2px 6px;border-radius:10px;font-size:0.75rem;margin-left:5px;'>Cross-Module Bridge</span>" if bridge else ""
        
        st.markdown(
            f"**`{tbl}`** [{mod}] — {role.replace('_', ' ').title()} {bridge_badge}<br>"
            f"<span style='font-size:0.85rem;color:#555;'>Score: **{comp:.3f}** (Struct: {struct:.3f} | Text: {text:.3f})</span>",
            unsafe_allow_html=True
        )


def render_qm_panel(qm: dict):
    if not qm or qm.get("count", 0) == 0:
        return

    results = qm.get("results", [])
    st.markdown("---")
    st.markdown("#### 🔬 QM Semantic Search Results")

    for r in results[:5]:
        score = r.get("score", 0)
        doc_nr = r.get("doc_nr", r.get("qm_notification", "?"))
        short = r.get("short_text", r.get("description", ""))[:180]
        st.markdown(
            f"<span class='qm-chip'>score={score:.3f}</span> "
            f"**`{doc_nr}`**: {short}",
            unsafe_allow_html=True
        )


# ============================================================================
# HELPER — Critique Panel
# ============================================================================

def render_critique_panel(crit: dict):
    if not crit:
        return

    score = crit.get("score", 0)
    passed = crit.get("passed", False)
    issues = crit.get("issues", [])
    suggestions = crit.get("suggestions", [])

    cls = "crit-pass" if passed else "crit-fail"
    verdict = "✅ PASS" if passed else "❌ FAIL"

    st.markdown(f"<div class='{cls}'>{verdict} — SQL Critique: <b>{score}/7 gates</b></div>", unsafe_allow_html=True)

    if issues:
        with st.expander("⚠️ Issues"):
            for issue in issues:
                st.markdown(f"- {issue}")

    if suggestions:
        with st.expander("💡 Suggestions"):
            for s in suggestions:
                st.markdown(f"- {s}")


# ============================================================================
# HELPER — Tool Trace
# ============================================================================

def render_tool_trace(trace: list):
    if not trace:
        return

    st.markdown("**⚙️ Agent Routing Trace**")
    for idx, step in enumerate(trace, 1):
        tool = step.get("tool", "?")
        status = step.get("status", "ok")
        dur = step.get("duration_ms", 0)
        phase = step.get("phase", "")
        msg = step.get("message", "")
        data = step.get("data", {})

        if status in ("skipped", "SKIPPED"):
            cls, icon = "tt-skip", "⏭"
        elif status in ("error", "ERROR"):
            cls, icon = "tt-err", "❌"
        else:
            cls, icon = "tt-ok", "✅"

        # Compact single-line summary
        summary = f"{idx}. {icon} `{tool}`"
        if phase:
            summary += f" <span class='tt-ph'>[P{phase}]</span>"
        if msg:
            summary += f" — {msg[:60]}"
        if dur:
            summary += f" <span class='tt-ph'>({dur}ms)</span>"

        st.markdown(f"<div class='tt-row {cls}'>{summary}</div>", unsafe_allow_html=True)


# ============================================================================
# HELPER — Self-Heal Banner
# ============================================================================

def render_self_heal(heal: dict):
    if not heal or not heal.get("applied"):
        return
    st.markdown(
        f"<div class='heal-banner'>🔧 <b>Autonomous Self-Heal fired</b> — "
        f"Code: `{heal.get('code','?')}` | Reason: {heal.get('reason','?')}</div>",
        unsafe_allow_html=True
    )


# ============================================================================
# HELPER — Full Answer Renderer
# ============================================================================

def render_answer(msg: dict):
    payload = msg["content"]

    conf = payload.get("confidence_score")
    exec_ms = payload.get("execution_time_ms", 0)
    role_applied = payload.get("role_applied", "?")
    routing_path = payload.get("routing_path", "?")
    pattern_name = payload.get("pattern_name", "?")

    # ── Row 1: Role + Routing + Exec Time ───────────────────────────────────
    r1c1, r1c2, r1c3, r1c4 = st.columns([1, 1, 1, 1])

    with r1c1:
        st.markdown(f"**Role:** <span class='role-{role_applied}'>{role_applied}</span>", unsafe_allow_html=True)

    with r1c2:
        if routing_path:
            r_cls = f"route-{routing_path.replace('_', '')}"
            r_icon = "⚡" if routing_path == "fast_path" else "🔗" if routing_path == "cross_module" else "📋"
            st.markdown(f"<span class='{r_cls}'>{r_icon} {routing_path.replace('_', ' ').title()}</span>", unsafe_allow_html=True)

    # ── Swarm Metadata (shown when swarm is active) ────────────────────────────
    swarm_routing = payload.get("swarm_routing")
    if swarm_routing and swarm_routing not in ("monolithic", "swarm_delegated", ""):
        domain_coverage = payload.get("domain_coverage", [])
        complexity = payload.get("complexity_score", 0)
        agent_summary = payload.get("agent_summary") or {}
        agent_count = len(agent_summary)
        success_agents = [k for k, v in agent_summary.items() if isinstance(v, dict) and v.get("status") == "success"]
        with r1c3:
            st.markdown(f"<span class='swarm-badge'>🤖 SWARM [{swarm_routing.upper()}] — {agent_count} agent(s): {', '.join(success_agents)}</span>", unsafe_allow_html=True)

    with r1c3:
        if pattern_name and pattern_name != "?":
            st.markdown(f"**Pattern:** <span class='pattern-badge'>{pattern_name}</span>", unsafe_allow_html=True)

    with r1c4:
        if exec_ms:
            st.markdown(f"<div class='exec-footer'>⏱ {exec_ms}ms</div>", unsafe_allow_html=True)

    st.markdown(payload.get("answer", ""))

    # ── Self-heal ───────────────────────────────────────────────────────────
    render_self_heal(payload.get("self_heal"))

    # ── Confidence Score ─────────────────────────────────────────────────────
    if conf:
        render_confidence_panel(conf)

    # ── Quality Metrics (Phase 12) ───────────────────────────────────────────
    q_metrics = payload.get("quality_metrics")
    if q_metrics:
        render_quality_metrics_panel(q_metrics)

    # ── Trajectory Log ───────────────────────────────────────────────────────
    traj = payload.get("trajectory_log")
    if traj:
        render_trajectory_log(traj)

    # ── Pillar Map ──────────────────────────────────────────────────────────
    with st.expander("🗺️ Pillar Activation Map"):
        render_pillar_map(
            tool_trace=payload.get("tool_trace"),
            routing_path=routing_path,
            temporal_mode=payload.get("temporal", {}).get("mode", "none") if payload.get("temporal") else "none",
            qm_count=payload.get("qm_semantic", {}).get("count", 0) if payload.get("qm_semantic") else 0,
            negotiation_brief=payload.get("negotiation_brief"),
        )

    # ── Phase 7 Temporal Analysis ────────────────────────────────────────────
    if payload.get("temporal"):
        render_phase7_panel(payload["temporal"])

    # ── Data Table ───────────────────────────────────────────────────────────
    data = payload.get("data")
    if data:
        st.markdown(f"**📊 Results — {len(data)} record(s)**")
        st.dataframe(pd.DataFrame(data), use_container_width=True)
    elif data == []:
        st.info("No records found for this query.")

    # ── Negotiation Card ─────────────────────────────────────────────────────
    render_negotiation_card(payload.get("negotiation_brief"))

    # ── QM Semantic ─────────────────────────────────────────────────────────
    render_graph_scores_panel(payload.get('graph_scores'))
    render_qm_panel(payload.get('qm_semantic'))


    # ── Swarm Summary (shown when swarm executed) ─────────────────────────────
    swarm_routing = payload.get("swarm_routing")
    if swarm_routing and swarm_routing not in ("monolithic", "swarm_delegated"):
        with st.expander("🤖 Swarm Execution Summary"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Routing:** `{swarm_routing}`")
                st.markdown(f"**Complexity:** `{(payload.get('complexity_score') or 0):.2f}`")
                st.markdown(f"**Planner:** {payload.get('planner_reasoning', '')}")
            with col2:
                agent_summary = payload.get("agent_summary") or {}
                for agent_name, agent_data in agent_summary.items():
                    if isinstance(agent_data, dict):
                        status_icon = "✅" if agent_data.get("status") == "success" else "❌"
                        st.markdown(f"{status_icon} **{agent_name}** — {agent_data.get('record_count', 0)} records in {agent_data.get('execution_time_ms', 0)}ms")
            conflicts = payload.get("conflicts") or []
            if conflicts:
                st.warning(f"⚠️ **{len(conflicts)} value conflict(s)** detected and resolved across agents")

            # [Harness] Validation Summary
            vs = payload.get("validation_summary") or {}
            if vs:
                validated = vs.get("agents_validated", 0)
                passed = vs.get("agents_passed", 0)
                failed = vs.get("agents_failed", 0)
                if validated > 0:
                    vs_color = "🟢" if failed == 0 else "🟡" if failed < validated else "🔴"
                    st.markdown(f"**Contract Validation:** {vs_color} {passed}/{validated} agents passed")
                    for agent, info in vs.get("per_agent", {}).items():
                        vp = info.get("validation_passed", False)
                        icon = "✅" if vp else "❌"
                        errs = info.get("validation_errors", [])
                        err_str = f" — {errs[0]}" if errs else ""
                        st.markdown(f"&nbsp;&nbsp;&nbsp;{icon} **{agent}**: {'PASS' if vp else 'FAIL'}{err_str}")
    # ── Sentinel Verdict ──────────────────────────────────────────────────────
    sentinel = payload.get("sentinel")
    sentinel_stats = payload.get("sentinel_stats") or {}
    if sentinel:
        verdict = sentinel.get("verdict", "?")
        flags = sentinel.get("flags", [])
        tightness = sentinel.get("session_tightness", 0)
        if verdict == "CLEAN":
            st.markdown("🛡️ **Security Sentinel:** `CLEAN` — no anomalies detected")
        elif verdict == "WARNING":
            st.warning(f"🛡️ **Security Sentinel:** `WARNING` — {len(flags)} flag(s): {', '.join(flags[:3])}")
        elif verdict == "BLOCKED":
            st.error(f"🛡️ **Security Sentinel:** `BLOCKED` — query blocked: {', '.join(flags)}")
        if sentinel_stats:
            with st.expander("📊 Sentinel Detection Stats"):
                cols = st.columns(len(sentinel_stats))
                for ci, (engine, count) in enumerate(sentinel_stats.items()):
                    with cols[ci]:
                        icon = "🔴" if count > 0 else "🟢"
                        st.metric(engine.replace("_", " ").title(), f"{icon} {count}")

    # ── Masked Fields ───────────────────────────────────────────────────────
    masked = payload.get("masked_fields", [])
    if masked:
        st.error(f"🔒 **Security Redactions Applied:** `{', '.join(masked)}`")

    # ── Critique ─────────────────────────────────────────────────────────────
    render_critique_panel(payload.get("critique"))

    # ── SQL + Technical expander ─────────────────────────────────────────────
    with st.expander("🔍 Technical Payload"):
        if payload.get("sql_generated"):
            st.markdown("**Generated SQL:**")
            st.code(payload["sql_generated"], language="sql")

        tables = payload.get("tables_used") or []
        if tables:
            st.markdown(f"**Schema RAG Access:** `{', '.join(tables)}`")

        run_id = payload.get("run_id")
        if run_id:
            st.markdown(f"**Run ID:** `{run_id}`")

        render_tool_trace(payload.get("tool_trace"))


# ============================================================================
# MAIN PAGE
# ============================================================================

st.title("Know Your SAP Masters")
st.caption("Enterprise Master Data Orchestrator — 8-Phase Agentic RAG | v2")

# Backend health check
try:
    r = requests.get(f"{API_BASE}/docs", timeout=2)
    backend_ok = r.status_code == 200
except Exception:
    backend_ok = False

if backend_ok:
    st.success("✅ Backend connected — 8-phase orchestrator active")
    try:
        alert_r = requests.get(f"{API_BASE}/api/v1/eval/alerts", timeout=2)
        if alert_r.status_code == 200:
            alerts_data = alert_r.json()
            if alerts_data.get("count", 0) > 0:
                st.warning(f"⚠️ **Eval Alerts ({alerts_data['count']}):** Quality thresholds breached.")
                for alert in alerts_data.get("alerts", []):
                    st.error(f"[{alert['level']}] {alert['message']}")
    except Exception:
        pass
else:
    st.error("🔴 Backend unreachable — is FastAPI running on port 8000?")

# ── Phase L4: Real-Time Operations Monitoring ──────────────────────────────────
try:
    render_monitoring_panel()
except Exception as e:
    st.caption(f"⚠️ Monitoring unavailable: {e}")

st.divider()

# ── Chat History ──────────────────────────────────────────────────────────

import uuid

if "session_id" not in st.session_state:
    st.session_state.session_id = f"st-{uuid.uuid4().hex[:12]}"

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_answer(msg)

# ── Input ─────────────────────────────────────────────────────────────────

ph = "Ask about Vendors, Materials, Finances, Quality Inspections, or Negotiation scenarios..."
if prompt := st.chat_input(ph):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"Authenticating {role} → routing through 8-phase orchestrator..."):
            try:
                payload = {
                    "query": prompt,
                    "domain": domain,
                    "user_role": role,
                    "use_swarm": True,  # Multi-Agent Domain Swarm for parallel domain execution
                }
                headers = {
                    "X-Session-ID": st.session_state.session_id,
                    "Content-Type": "application/json"
                }
                t0 = time.time()
                response = requests.post(API_URL, json=payload, headers=headers, timeout=90)
                elapsed_ms = int((time.time() - t0) * 1000)

                if response.status_code == 200:
                    data = response.json()
                    data["_client_ms"] = elapsed_ms
                    st.session_state.messages.append({"role": "assistant", "content": data})
                    render_answer({"content": data})

                elif response.status_code == 422:
                    st.error("❌ Validation error — check query and domain.")
                    st.json(response.json())
                else:
                    st.error(f"🔴 Backend error ({response.status_code}): {response.text}")

            except requests.exceptions.ConnectionError:
                st.error("🔴 Cannot reach backend. Is FastAPI running on port 8000?")
            except requests.exceptions.Timeout:
                st.error("🔴 Request timed out after 90s. Try a simpler query.")
            except Exception as e:
                st.error(f"🔴 Unexpected error: {str(e)}")
