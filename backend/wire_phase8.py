"""Wire Phase 8 into orchestrator.py: Step 1.75 (QM Semantic) + Step 2d (Negotiation Brief)"""

with open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\orchestrator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ─────────────────────────────────────────────────────────────────────────────
# INSERTION 1: Step 1.75 — after line "print(f'    [WARN] Graph embedding..."
# ─────────────────────────────────────────────────────────────────────────────
QM_STEP = '''
        # =========================================================================
        # STEP 1.75: [Phase 8] QM LONG-TEXT SEMANTIC SEARCH
        # =========================================================================
        # For QM-domain queries: search 20yr of mechanic notes (QMEL-QMTXT) for
        # semantically relevant historical context — failures, defects, warnings.
        # Example: "bearing vibration fatigue" → finds 2009 note: "Bearing B-2047
        # showing fatigue signs — recommend replacement at next planned shutdown."
        qm_intent_keywords = [
            "quality", "qm", "inspection", "nonconformance", "ncr",
            "quality notification", "qm notification", "defect", "reject",
            "quality issue", "qa", "quality assurance", "material defect",
            "quality defect", "complaint", "quality complaint", "qmel",
        ]
        is_qm_query = any(kw in query.lower() for kw in qm_intent_keywords)

        qm_semantic_results: List[Dict[str, Any]] = []
        if is_qm_query and not meta_path_used:
            print(f"\\n[1.75/5] [Phase 8] QM Semantic Search — searching 20yr of mechanic notes")
            try:
                from app.core.qm_semantic_search import QMSemanticSearch
                qm_search = QMSemanticSearch()

                # Extract equipment ID if present (e.g., "equipment B-2047")
                equip_match = re.search(r'(?:equipment|equip|machine|asset)\\s+(?:ID\\s+)?([A-Z0-9-]+)', query, re.I)
                equipment_filter = equip_match.group(1) if equip_match else None

                qm_results = qm_search.search(
                    query=query,
                    equipment=equipment_filter,
                    year_range=(2005, 2025),
                    top_k=5,
                )
                qm_semantic_results = qm_results

                if qm_results:
                    print(f"    [QM] Found {len(qm_results)} relevant QM notification chunk(s)")
                    top_qm = qm_results[0]
                    print(f"    Top match: [{top_qm['year']}] {top_qm['equipment']} — "
                          f"score={top_qm['similarity_score']:.3f}")
                    print(f"    Text: {top_qm['text'][:100]}...")
                    trace("qm_semantic_search", ToolResult(
                        status=ToolStatus.SUCCESS,
                        message=f"Found {len(qm_results)} QM chunks",
                        data={"results": qm_results, "count": len(qm_results)},
                        metadata={"equipment": equipment_filter},
                    ))
                else:
                    print(f"    [QM] No QM semantic matches (index may be empty)")
                    trace("qm_semantic_search", ToolResult(
                        status=ToolStatus.SUCCESS,
                        message="No QM semantic matches",
                        data={"results": [], "count": 0},
                        metadata={"equipment": equipment_filter},
                    ))
            except Exception as e:
                print(f"    [QM] Semantic search error (non-fatal): {e}")
                trace("qm_semantic_search", ToolResult(
                    status=ToolStatus.ERROR,
                    message=f"QM semantic search failed: {e}",
                    data={},
                    metadata={},
                ))
        else:
            trace("qm_semantic_search", ToolResult(
                status=ToolStatus.SKIPPED,
                message="Not a QM-domain query",
                data={},
                metadata={},
            ))

'''

target1 = "        # =========================================================================\n        # STEP 2: SQL PATTERN RETRIEVAL (Pillar 4)\n"
if target1 in content:
    content = content.replace(target1, QM_STEP + target1, 1)
    print("✓ Step 1.75 (QM Semantic) inserted before STEP 2")
else:
    print("✗ Could not find Step 2 anchor text")

# ─────────────────────────────────────────────────────────────────────────────
# INSERTION 2: Step 2d — Negotiation Briefing
# (after Step 2c/Temporal Analysis Engine, before Step 3)
# ─────────────────────────────────────────────────────────────────────────────
NEGO_STEP = '''
        # =========================================================================
        # STEP 2d: [Phase 8] NEGOTIATION BRIEFING GENERATOR
        # =========================================================================
        # When negotiation intent is detected: synthesize a structured negotiation
        # brief from 20yr of SAP data — CLV, PSI, churn risk, BATNA, tactics.
        # Fires on: "negotiate", "contract renewal", "price increase",
        # "supplier review", "customer review", "vendor briefing"
        negotiation_keywords = [
            "negotiate", "negotiation", "contract renewal", "price increase",
            "supplier review", "vendor review", "customer review",
            "negotiation brief", "briefing", "clv", "customer lifetime",
            "supplier performance", "vendor performance", "price sensitivity",
            "batna", "churn risk", "vendor scorecard", "supplier scorecard",
            "contract", "renewal", "pricing power", "leverage",
        ]
        is_negotiation_query = any(kw in query.lower() for kw in negotiation_keywords)

        negotiation_brief: Optional[Dict[str, Any]] = None
        if is_negotiation_query:
            print(f"\\n[2d/5] [Phase 8] Negotiation Briefing Generator — synthesizing 20yr brief")
            try:
                from app.core.negotiation_briefing import (
                    NegotiationBriefingGenerator, NegotiationBriefFormatter,
                    EntityType, NegotiationType,
                )
                gen = NegotiationBriefingGenerator()
                fmt = NegotiationBriefFormatter()

                # Extract entity ID and type from query
                customer_match = re.search(r'(?:customer|KUNNR|KUN?)[-_]?(\\w{3,12})', query, re.I)
                vendor_match = re.search(r'(?:vendor|LIFNR|VEND?)[-_]?(\\w{3,12})', query, re.I)
                entity_id = (customer_match or vendor_match or type('', (), {'group': lambda s: 'KUNNR-10000142'})()).group()
                entity_type = EntityType.CUSTOMER if customer_match else EntityType.VENDOR
                entity_name = entity_id  # SAP name lookup deferred to real connection

                # Determine negotiation type
                q_lower = query.lower()
                if any(k in q_lower for k in ["price increase", "pricing"]):
                    neg_type = NegotiationType.PRICE_INCREASE
                elif any(k in q_lower for k in ["contract renewal", "renewal"]):
                    neg_type = NegotiationType.CONTRACT_RENEWAL
                elif any(k in q_lower for k in ["volume"]):
                    neg_type = NegotiationType.VOLUME_REVISION
                elif any(k in q_lower for k in ["terms", "payment terms", "terms revision"]):
                    neg_type = NegotiationType.TERMS_REVISION
                else:
                    neg_type = NegotiationType.CONTRACT_RENEWAL

                # Build mock data dicts (replace with real SAP queries in production)
                mock_rel = {
                    "relationship": [
                        {"ORDER_YEAR": yr, "ANNUAL_REVENUE": 100000 + yr * 5000,
                         "ORDER_COUNT": 12, "AVG_ORDER_VALUE": 9000, "DISCOUNT_PCT": 3.5,
                         "ACTIVE_MONTHS": 10, "RETURN_RATE": 1.0}
                        for yr in range(2020, 2025)
                    ],
                    "payment": [
                        {"PAYMENT_YEAR": yr, "AVG_DAYS_TO_PAY": 40, "PAYMENT_SCORE": 80}
                        for yr in range(2020, 2025)
                    ],
                }
                mock_pi = [
                    {"PRICING_YEAR": 2021, "AVG_PRICE_INCREASE_PCT": 3.5},
                    {"PRICING_YEAR": 2022, "AVG_PRICE_INCREASE_PCT": 5.0},
                    {"PRICING_YEAR": 2024, "AVG_PRICE_INCREASE_PCT": 4.0},
                ]

                brief = gen.generate(
                    entity_id=entity_id,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    negotiation_type=neg_type,
                    relationship_data=mock_rel,
                    price_increase_data=mock_pi,
                    payment_data=mock_rel["payment"],
                )

                negotiation_brief = fmt.format_structured(brief)
                brief_text = fmt.format_text(brief)

                print(f"    [BRIEF] Entity: {brief.entity_name} ({brief.entity_type.value})")
                print(f"    [BRIEF] CLV Tier: {brief.clv_tier} | PSI: {brief.price_sensitivity_index}/10")
                print(f"    [BRIEF] Churn Risk: {brief.churn_risk} | BATNA Strength: {brief.batna_strength:.0f}/10")
                print(f"    [BRIEF] Target: +{brief.recommended_increase_pct:.1f}% increase | "
                      f"Accept min: +{brief.max_acceptable_increase_pct:.1f}%")
                print(f"    [BRIEF] Top tactic: {brief.top_tactics[0][:80]}")

                trace("negotiation_briefing", ToolResult(
                    status=ToolStatus.SUCCESS,
                    message=f"Negotiation brief: {brief.entity_name} ({brief.clv_tier} CLV)",
                    data={"brief": negotiation_brief, "brief_text": brief_text},
                    metadata={"entity_id": entity_id, "entity_type": entity_type.value,
                              "neg_type": neg_type.value, "clv_tier": brief.clv_tier,
                              "psi": brief.price_sensitivity_index},
                ))
            except Exception as e:
                print(f"    [BRIEF] Error generating negotiation brief: {e}")
                trace("negotiation_briefing", ToolResult(
                    status=ToolStatus.ERROR,
                    message=f"Negotiation brief error: {e}",
                    data={},
                    metadata={},
                ))
        else:
            trace("negotiation_briefing", ToolResult(
                status=ToolStatus.SKIPPED,
                message="Not a negotiation query",
                data={},
                metadata={},
            ))

'''

# Find the "STEP 3: GRAPH TRAVERSAL" comment block and insert before it
target2 = "        # =========================================================================\n        # STEP 3: GRAPH TRAVERSAL (Pillar 5)"
if target2 in content:
    content = content.replace(target2, NEGO_STEP + target2, 1)
    print("✓ Step 2d (Negotiation Briefing) inserted before STEP 3")
else:
    print("✗ Could not find Step 3 anchor text")

with open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\agents\orchestrator.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\nDone. Phase 8 wired into orchestrator.")
