# ============================================================================
# HELPER — Phase L4: Real-Time Operations Monitoring Panel
# ============================================================================

def render_monitoring_panel():
    """
    Phase L4: Real-Time Operations Monitoring Panel.
    Polls /api/v1/eval/monitoring/metrics and /health every refresh cycle.
    Shows system health, throughput, latency, success rates, self-heal,
    CIBA, Sentinel, and Swarm metrics in a compact dashboard layout.
    """
    import requests
    st.markdown("---")
    st.markdown("### 📊 Real-Time Operations Dashboard")

    mon_r = None
    try:
        mon_r = requests.get(f"{API_BASE}/api/v1/eval/monitoring/metrics", timeout=3)
        mon_r.raise_for_status()
        mon = mon_r.json()
    except Exception:
        st.caption("⚠️ Monitoring endpoint unreachable")
        return

    health_r = None
    try:
        health_r = requests.get(f"{API_BASE}/api/v1/eval/monitoring/health", timeout=3)
        health_r.raise_for_status()
        health = health_r.json()
    except Exception:
        health = {}

    uptime = mon.get("uptime_seconds", 0)
    h, rem = divmod(int(uptime), 3600)
    m, s = divmod(rem, 60)
    uptime_str = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"

    # ── Health badge ─────────────────────────────────────────────────────────
    status = health.get("status", "UNKNOWN")
    hs = health.get("health_score", 0.0)
    if status == "GREEN":
        badge = "🟢 GREEN"
    elif status == "YELLOW":
        badge = "🟡 YELLOW"
    else:
        badge = "🔴 RED"

    col_h, col_q, col_u = st.columns([1, 1, 1])
    with col_h:
        st.metric("System Health", badge, f"{hs:.2f}")
    with col_q:
        qiw = mon.get("queries_in_window", 0)
        tot = mon.get("total_queries", 0)
        st.metric("Queries (window/total)", f"{qiw} / {tot}")
    with col_u:
        sr = mon.get("success_rates", {})
        st.metric("Uptime", uptime_str, f"succ={sr.get('success_rate', 0.0):.1%}")

    # ── Throughput + Latency ─────────────────────────────────────────────────
    tp = mon.get("throughput", {})
    lat = mon.get("latency", {})
    col_tp, col_lt = st.columns(2)
    with col_tp:
        st.markdown(
            f"**Throughput:** {tp.get('qpm', 0):.1f} qpm | {tp.get('qph', 0):.1f} qph")
    with col_lt:
        st.markdown(
            f"**Latency:** avg={lat.get('avg_ms', 0):.0f}ms  p50={lat.get('p50_ms', 0):.0f}ms  "
            f"p95={lat.get('p95_ms', 0):.0f}ms  p99={lat.get('p99_ms', 0):.0f}ms")

    # ── Success / Error rates ─────────────────────────────────────────────────
    sr = mon.get("success_rates", {})
    col1, col2, col3, col4, col5, col6 = st.columns([1, 1, 1, 1, 1, 1])
    with col1:
        st.metric("✅ Success", sr.get("success", 0))
    with col2:
        st.metric("⬜ Empty", sr.get("empty", 0))
    with col3:
        st.metric("❌ Error", sr.get("error", 0))
    with col4:
        st.metric("⏳ CIBA Pending", sr.get("ciba_pending", 0))
    with col5:
        st.metric("🚫 CIBA Denied", sr.get("ciba_denied", 0))
    with col6:
        st.metric("Success Rate", f"{sr.get('success_rate', 0):.1%}")

    # ── Self-Heal + Semantic Validation ───────────────────────────────────────
    sh = mon.get("self_heal", {})
    sv = mon.get("semantic_validation", {})
    col_sh, col_sv = st.columns(2)
    with col_sh:
        st.markdown(
            f"**Self-Heal:** {sh.get('heal_rate_pct', '0.0%')} rate | "
            f"{sh.get('total_heals', 0)} heals")
        top_codes = sh.get("top_heal_codes", [])
        if top_codes:
            code_str = " | ".join(f"{c['code']}={c['count']}" for c in top_codes[:4])
            st.caption(f"  Top codes: {code_str}")
    with col_sv:
        v_count = sv.get("validated_count", 0)
        st.markdown(
            f"**Semantic Trust:** {v_count} validated | "
            f"high={sv.get('high_count', 0)} | "
            f"med={sv.get('medium_count', 0)} | "
            f"low={sv.get('low_count', 0)}")

    # ── Voting Executor + CIBA ────────────────────────────────────────────────
    vt = mon.get("voting", {})
    cb = mon.get("ciba", {})
    col_vt, col_cb = st.columns(2)
    with col_vt:
        triggered_pct = vt.get("triggered_pct", 0) * 100
        consensus_pct = vt.get("consensus_rate", 0) * 100
        st.markdown(
            f"**Voting:** {triggered_pct:.1f}% triggered | "
            f"consensus={consensus_pct:.1f}% | "
            f"boost={vt.get('avg_confidence_boost', 0):.3f}")
    with col_cb:
        backend = cb.get("backend", "unknown")
        pending = cb.get("pending_count", 0)
        approved = cb.get("approved_auto", 0)
        denied = cb.get("denied_auto", 0)
        st.markdown(
            f"**CIBA:** backend={backend} | "
            f"pending={pending} | approved={approved} | denied={denied}")

    # ── Sentinel + Swarm ─────────────────────────────────────────────────────
    sent = mon.get("sentinel", {})
    sw = mon.get("swarm", {})
    col_sent, col_sw = st.columns(2)
    with col_sent:
        dr = sent.get("detection_rate", 0) * 100
        by_sev = sent.get("by_severity", {})
        st.markdown(
            f"**Sentinel:** detection={dr:.1f}% | "
            f"total={sent.get('total_detected', 0)}")
        if by_sev:
            sev_str = " | ".join(f"{k}={v}" for k, v in by_sev.items())
            st.caption(f"  {sev_str}")
    with col_sw:
        sw_rate = sw.get("swarm_rate", 0) * 100
        st.markdown(
            f"**Swarm:** rate={sw_rate:.1f}% | "
            f"mono={sw.get('mono_queries', 0)} | "
            f"swarm={sw.get('swarm_queries', 0)} | "
            f"avg_agents={sw.get('avg_agents_per_query', 0):.1f}")

    # ── Domain Breakdown ──────────────────────────────────────────────────────
    domains = mon.get("domains", {})
    if domains:
        with st.expander("📂 Domain Breakdown"):
            for d, info in list(domains.items())[:10]:
                st.caption(
                    f"  **{d}**: {info['count']} queries | "
                    f"avg={info.get('avg_ms', 0):.0f}ms")

    # ── Role Breakdown ───────────────────────────────────────────────────────
    roles = mon.get("roles", {})
    if roles:
        with st.expander("👤 Role Breakdown"):
            for r, info in list(roles.items())[:8]:
                st.caption(
                    f"  **{r}**: {info['count']} queries | "
                    f"errors={info['errors']} | "
                    f"error_rate={info.get('error_rate', 0):.1%}")

    st.caption(
        f"⏱ Generated at {mon.get('generated_at', '')} | "
        f"window={mon.get('window_seconds', 3600)}s")
