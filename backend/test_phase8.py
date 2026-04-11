"""Smoke test for Phase 8 modules"""
from app.core.negotiation_briefing import (
    NegotiationBriefingGenerator,
    NegotiationBriefFormatter,
    NegotiationSQLGenerator,
    NegotiationBrief,
    NegotiationBriefingSynthesizer,
    EntityType,
    NegotiationType,
)
from app.core.qm_semantic_search import QMSemanticSearch, QMTextExtractor

print("=== NEGOTIATION BRIEFING ===")
gen = NegotiationSQLGenerator()
print("SQL Generator imported OK")

sql = NegotiationSQLGenerator.relationship_summary_sql("KUNNR-10000142", EntityType.CUSTOMER)
print(f"Relationship SQL: {sql[:100]}...")

sql2 = NegotiationSQLGenerator.payment_behavior_sql("KUNNR-10000142", EntityType.CUSTOMER)
print(f"Payment SQL: {sql2[:100]}...")

sql3 = NegotiationSQLGenerator.price_increase_history_sql("KUNNR-10000142", EntityType.CUSTOMER)
print(f"Price Increase SQL: {sql3[:100]}...")

print("\n=== NEGOTIATION BRIEFING SYNTHESIZER ===")
syn = NegotiationBriefingSynthesizer()
mock_rel = {
    "relationship": [
        {"ORDER_YEAR": 2020, "ANNUAL_REVENUE": 150000, "ORDER_COUNT": 12, "AVG_ORDER_VALUE": 12500, "DISCOUNT_PCT": 3.5, "ACTIVE_MONTHS": 10, "RETURN_RATE": 1.2},
        {"ORDER_YEAR": 2021, "ANNUAL_REVENUE": 165000, "ORDER_COUNT": 14, "AVG_ORDER_VALUE": 11786, "DISCOUNT_PCT": 4.0, "ACTIVE_MONTHS": 11, "RETURN_RATE": 1.0},
        {"ORDER_YEAR": 2022, "ANNUAL_REVENUE": 142000, "ORDER_COUNT": 11, "AVG_ORDER_VALUE": 12909, "DISCOUNT_PCT": 5.2, "ACTIVE_MONTHS": 9, "RETURN_RATE": 2.1},
        {"ORDER_YEAR": 2023, "ANNUAL_REVENUE": 178000, "ORDER_COUNT": 15, "AVG_ORDER_VALUE": 11867, "DISCOUNT_PCT": 3.8, "ACTIVE_MONTHS": 12, "RETURN_RATE": 0.8},
        {"ORDER_YEAR": 2024, "ANNUAL_REVENUE": 195000, "ORDER_COUNT": 16, "AVG_ORDER_VALUE": 12188, "DISCOUNT_PCT": 4.2, "ACTIVE_MONTHS": 12, "RETURN_RATE": 1.1},
    ],
    "payment": [
        {"PAYMENT_YEAR": 2020, "AVG_DAYS_TO_PAY": 42, "PAYMENT_SCORE": 76},
        {"PAYMENT_YEAR": 2021, "AVG_DAYS_TO_PAY": 38, "PAYMENT_SCORE": 82},
        {"PAYMENT_YEAR": 2022, "AVG_DAYS_TO_PAY": 45, "PAYMENT_SCORE": 71},
        {"PAYMENT_YEAR": 2023, "AVG_DAYS_TO_PAY": 35, "PAYMENT_SCORE": 85},
        {"PAYMENT_YEAR": 2024, "AVG_DAYS_TO_PAY": 40, "PAYMENT_SCORE": 79},
    ],
}

brief = syn.synthesize(
    entity_id="KUNNR-10000142",
    entity_name="ACME Corp",
    entity_type=EntityType.CUSTOMER,
    negotiation_type=NegotiationType.PRICE_INCREASE,
    relationship_data=mock_rel,
    price_increase_data=[
        {"PRICING_YEAR": 2021, "AVG_PRICE_INCREASE_PCT": 3.5},
        {"PRICING_YEAR": 2022, "AVG_PRICE_INCREASE_PCT": 5.2},
        {"PRICING_YEAR": 2024, "AVG_PRICE_INCREASE_PCT": 4.0},
    ],
    payment_data=mock_rel["payment"],
)

print(f"Brief generated: entity={brief.entity_name}, PSI={brief.price_sensitivity_index}")
print(f"Sensitivity tier: {brief.sensitivity_tier.value}")
print(f"CLV tier: {brief.clv_tier}")
print(f"Recommended increase: +{brief.recommended_increase_pct:.1f}%")
print(f"Churn risk: {brief.churn_risk}")
print(f"Top tactic: {brief.top_tactics[0]}")
print(f"Bottom line: {brief.bottom_line[:80]}...")

print("\n=== BRIEF FORMATTER ===")
fmt = NegotiationBriefFormatter()
text = fmt.format_text(brief)
print(text[:500])

print("\n=== QM SEMANTIC SEARCH ===")
qm = QMSemanticSearch()
print(f"QM search initialized — stats: {qm.stats}")

extractor = QMTextExtractor()
mock_notifs = extractor.generate_mock_notifications(count=50, year_start=2020, year_end=2024)
print(f"Generated {len(mock_notifs)} mock QM notifications")
print(f"First notification: {mock_notifs[0].notification_no} | {mock_notifs[0].equipment} | {mock_notifs[0].year}")

chunks = extractor.chunk_text(mock_notifs[0].long_text)
print(f"Chunked into {len(chunks)} text chunks")

index_result = qm.index_notifications(
    notifications=mock_notifs,
    count=50,
    year_start=2020,
    year_end=2024,
    verbose=False,
)
print(f"Index result: {index_result}")

results = qm.search(query="bearing vibration fatigue", top_k=5)
print(f"Semantic search results: {len(results)} hits")
if results:
    r = results[0]
    print(f"  Top result: [{r['year']}] {r['equipment']} — {r['text'][:80]}...")

context = qm.get_failure_context(equipment="B-2047", before_year=2026, years_back=3)
print(f"\nFailure context: {context.get('summary', 'No results')[:100]}")

print("\n=== ALL PHASE 8 TESTS PASSED ===")
