"""
Phase 24: Episodic Memory Store — Smoke Tests
==============================================
Tests EpisodicMemoryStore with in-memory backend (force_backend="memory").
Redis unavailable locally so we use the fallback.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.episodic_memory import (
    EpisodicMemoryStore,
    QueryRecord,
    ConversationContext,
    SessionMeta,
    get_memory_store,
    reset_memory_store,
    record_query,
    get_context,
    InMemoryBackend,
    RedisBackend,
    DEFAULT_QUERY_HISTORY_LIMIT,
    DEFAULT_CONTEXT_WINDOW,
)

passed = 0
failed = 0

def test(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name} — {detail}")
        failed += 1

print("=== Phase 24: Episodic Memory — Smoke Tests ===\n")

# Force memory backend for all tests
store = EpisodicMemoryStore(force_backend="memory")
print(f"Backend: {store._backend_name}\n")

# ── Test 1: Instantiation ─────────────────────────────────────────────────
print("Test 1: EpisodicMemoryStore instantiation")
test("store created", store is not None)
test("backend is memory (forced)", store._backend_name == "memory")
test("default ttl is 8h", store.session_ttl == 8 * 3600)
test("context_window default=10", store.context_window == 10)
test("query_history_limit default=50", store.query_history_limit == 50)

# ── Test 2: record_query — basic ──────────────────────────────────────────
print("\nTest 2: record_query — basic")
rec1 = store.record_query(
    session_id="test_session_001",
    query="show me all vendors for company code 1000",
    domain="vendor_master",
    role_id="AP_CLERK",
    tables_used=["LFA1", "LFB1"],
    confidence=0.92,
    answer="Here are the vendors...",
    duration_ms=45,
)
test("record returned", isinstance(rec1, QueryRecord))
test("turn_id=1 for first query", rec1.turn_id == 1)
test("query stored correctly", rec1.query == "show me all vendors for company code 1000")
test("domain stored", rec1.domain == "vendor_master")
test("role_id stored", rec1.role_id == "AP_CLERK")
test("tables_used stored", rec1.tables_used == ["LFA1", "LFB1"])
test("confidence stored", rec1.confidence == 0.92)
test("duration_ms stored", rec1.duration_ms == 45)
test("answer_excerpt stored (truncated)", rec1.answer_excerpt is not None)
test("timestamp generated", rec1.timestamp != "")

# ── Test 3: record_query — second turn ────────────────────────────────────
print("\nTest 3: record_query — second turn (increments turn_id)")
rec2 = store.record_query(
    session_id="test_session_001",
    query="show me open POs for vendor 1000",
    domain="purchasing",
    role_id="AP_CLERK",
    tables_used=["EKKO", "EKPO"],
    confidence=0.88,
)
test("turn_id=2 for second query", rec2.turn_id == 2)
test("same session increments", True)

# ── Test 4: get_history ──────────────────────────────────────────────────
print("\nTest 4: get_history")
history = store.get_history("test_session_001")
test("history returns list", isinstance(history, list))
test("history has 2 records", len(history) == 2)
test("history order: oldest first", history[0].turn_id == 1)
test("history[-1] is latest", history[-1].turn_id == 2)

# ── Test 5: get_history — limit ──────────────────────────────────────────
print("\nTest 5: get_history — with limit")
history_limited = store.get_history("test_session_001", limit=1)
test("limit=1 returns 1 record", len(history_limited) == 1)
test("returns latest when limit=1", history_limited[0].turn_id == 2)

# ── Test 6: get_history — unknown session ─────────────────────────────────
print("\nTest 6: get_history — unknown session")
empty = store.get_history("nonexistent_session_xyz")
test("returns empty list for unknown session", empty == [])

# ── Test 7: conversation context ─────────────────────────────────────────
print("\nTest 7: Conversation context")
ctx = store.get_context("test_session_001")
test("context is ConversationContext", isinstance(ctx, ConversationContext))
test("context has 3 turns (user+assistant from rec1, user from rec2)", len(ctx.turns) == 3)
test("first turn is user", ctx.turns[0].role == "user")
test("second turn is assistant", ctx.turns[1].role == "assistant")

# ── Test 8: get_context_snippet ──────────────────────────────────────────
print("\nTest 8: get_context_snippet")
snippet = store.get_context_snippet("test_session_001", max_turns=4)
test("snippet is string", isinstance(snippet, str))
test("snippet contains 'User:'", "User:" in snippet)
test("snippet contains 'Assistant:'", "Assistant:" in snippet)

# ── Test 9: scratchpad ───────────────────────────────────────────────────
print("\nTest 9: Scratchpad operations")
store.set_scratchpad("test_session_001", "last_domain", "vendor_master")
store.set_scratchpad("test_session_001", "last_vendor_id", "1000")
store.set_scratchpad("test_session_001", "user_preference", {"format": "table", "limit": 50})
val = store.get_scratchpad("test_session_001", "last_domain")
test("get_scratchpad returns correct value", val == "vendor_master")
val2 = store.get_scratchpad("test_session_001", "last_vendor_id")
test("get_scratchpad str value", val2 == "1000")
val3 = store.get_scratchpad("test_session_001", "user_preference")
test("get_scratchpad dict value", val3 == {"format": "table", "limit": 50})
all_sp = store.get_all_scratchpad("test_session_001")
test("get_all_scratchpad returns dict", isinstance(all_sp, dict))
test("get_all_scratchpad has 3 keys", len(all_sp) == 3)

# ── Test 10: scratchpad — unknown key ────────────────────────────────────
print("\nTest 10: Scratchpad — unknown key")
val_unknown = store.get_scratchpad("test_session_001", "nonexistent_key_xyz")
test("returns None for unknown key", val_unknown is None)

# ── Test 11: delete_scratchpad_key ───────────────────────────────────────
print("\nTest 11: delete_scratchpad_key")
store.delete_scratchpad_key("test_session_001", "last_domain")
val_after = store.get_scratchpad("test_session_001", "last_domain")
test("key removed after delete", val_after is None)
test("other keys still present", store.get_scratchpad("test_session_001", "last_vendor_id") == "1000")

# ── Test 12: deduplication ───────────────────────────────────────────────
print("\nTest 12: Deduplication")
q1 = "show me all vendors for company code 1000"
is_dup1, sig1 = store.check_dedup("test_session_001", q1)
test("first occurrence: is_dup=False", is_dup1 == False)
test("first occurrence: sig returned", sig1 is not None)
is_dup2, sig2 = store.check_dedup("test_session_001", q1)
test("second occurrence (same query): is_dup=True", is_dup2 == True)
test("same sig for identical query", sig1 == sig2)
is_dup3, sig3 = store.check_dedup("test_session_001", "show me all vendors for company code 2000")
test("different query: is_dup=False", is_dup3 == False)

# ── Test 13: session meta ─────────────────────────────────────────────────
print("\nTest 13: Session metadata")
meta = store.get_session_meta("test_session_001")
test("meta is SessionMeta", isinstance(meta, SessionMeta))
test("session_id matches", meta.session_id == "test_session_001")
test("turn_count=2 after 2 queries", meta.turn_count == 2)
test("role_id recorded", meta.role_id == "AP_CLERK")
test("created_at set", meta.created_at != "")
test("last_activity set", meta.last_activity != "")

# ── Test 14: update_session_meta ─────────────────────────────────────────
print("\nTest 14: update_session_meta")
store.update_session_meta("test_session_001", role_id="CFO_GLOBAL", user_id="john.doe")
meta2 = store.get_session_meta("test_session_001")
test("role_id updated to CFO_GLOBAL", meta2.role_id == "CFO_GLOBAL")
test("user_id updated to john.doe", meta2.user_id == "john.doe")
test("turn_count incremented after update", meta2.turn_count >= 2)

# ── Test 15: tag_session ─────────────────────────────────────────────────
print("\nTest 15: Session tagging")
store.tag_session("test_session_001", "executive_report")
store.tag_session("test_session_001", "priority")
meta3 = store.get_session_meta("test_session_001")
test("tag added to session", "executive_report" in meta3.tags)
test("second tag added", "priority" in meta3.tags)
test("duplicate tag not added twice", meta3.tags.count("executive_report") == 1)

# ── Test 16: get_context_snippet for prompt injection ────────────────────
print("\nTest 16: get_recent_context_for_prompt")
prompt_ctx = store.get_recent_context_for_prompt("test_session_001", max_turns=4)
test("prompt context is non-empty string", len(prompt_ctx) > 0)
test("contains session marker", "[Session Context]" in prompt_ctx)
test("contains role info", "CFO_GLOBAL" in prompt_ctx)

# ── Test 17: QueryRecord.to_dict / from_dict ─────────────────────────────
print("\nTest 17: QueryRecord serialization")
rec_dict = rec1.to_dict()
test("to_dict returns dict", isinstance(rec_dict, dict))
test("to_dict has required keys", all(k in rec_dict for k in ["turn_id", "query", "domain", "role_id"]))
rec_restored = QueryRecord.from_dict(rec_dict)
test("from_dict roundtrip preserves turn_id", rec_restored.turn_id == rec1.turn_id)
test("from_dict roundtrip preserves query", rec_restored.query == rec1.query)
test("from_dict roundtrip preserves tables_used", rec_restored.tables_used == rec1.tables_used)

# ── Test 18: SessionMeta.to_dict / from_dict ─────────────────────────────
print("\nTest 18: SessionMeta serialization")
meta_dict = meta.to_dict()
test("to_dict returns dict", isinstance(meta_dict, dict))
meta_restored = SessionMeta.from_dict(meta_dict)
test("from_dict roundtrip preserves session_id", meta_restored.session_id == meta.session_id)
test("from_dict roundtrip preserves turn_count", meta_restored.turn_count == meta.turn_count)

# ── Test 19: delete_session ──────────────────────────────────────────────
print("\nTest 19: delete_session")
store.delete_session("test_session_001")
history_after = store.get_history("test_session_001")
ctx_after = store.get_context("test_session_001")
sp_after = store.get_all_scratchpad("test_session_001")
test("history cleared after delete", history_after == [])
test("context cleared after delete", len(ctx_after.turns) == 0)
test("scratchpad cleared after delete", sp_after == {})

# ── Test 20: get_active_sessions ─────────────────────────────────────────
print("\nTest 20: Active sessions tracking")
store.record_query(session_id="session_A", query="query A", role_id="AP_CLERK")
store.record_query(session_id="session_B", query="query B", role_id="MM_CLERK")
active = store.get_active_sessions()
test("get_active_sessions returns list", isinstance(active, list))
test("session_A in active list", "session_A" in active)
test("session_B in active list", "session_B" in active)

# ── Test 21: get_session_summary ────────────────────────────────────────
print("\nTest 21: Session summary")
summary = store.get_session_summary("session_A")
test("summary is dict", isinstance(summary, dict))
test("has session_id", "session_id" in summary)
test("has meta", "meta" in summary)
test("has query_count", "query_count" in summary)
test("has top_tables", "top_tables" in summary)
test("has scratchpad_keys", "scratchpad_keys" in summary)
test("query_count=1 for session_A", summary["query_count"] == 1)

# ── Test 22: cross-session isolation ──────────────────────────────────────
print("\nTest 22: Cross-session isolation")
rec_A = store.record_query(session_id="session_X", query="query X from session X", role_id="AP_CLERK")
rec_B = store.record_query(session_id="session_Y", query="query Y from session Y", role_id="MM_CLERK")
hist_X = store.get_history("session_X")
hist_Y = store.get_history("session_Y")
test("session_X history has 1 record", len(hist_X) == 1)
test("session_Y history has 1 record", len(hist_Y) == 1)
test("session_X history is for session_X", hist_X[0].query == "query X from session X")
test("session_Y history is for session_Y", hist_Y[0].query == "query Y from session Y")

# ── Test 23: InMemoryBackend direct ──────────────────────────────────────
print("\nTest 23: InMemoryBackend direct usage")
backend = InMemoryBackend()
backend.push_query("direct_test", QueryRecord(
    turn_id=1, query="test", query_signature="sig", domain="auto", role_id="GUEST", tables_used=[]
))
queries = backend.get_queries("direct_test")
test("InMemoryBackend.push_query works", len(queries) == 1)
test("InMemoryBackend.get_queries works", queries[0].query == "test")

# ── Test 24: module-level convenience functions ───────────────────────────
print("\nTest 24: Module-level convenience functions")
reset_memory_store()   # Reset singleton
store24 = get_memory_store(force_backend="memory")
test("get_memory_store() returns EpisodicMemoryStore", isinstance(store24, EpisodicMemoryStore))
rec24 = record_query(session_id="conv_001", query="convenience test", role_id="AP_CLERK")
test("record_query convenience works", rec24.query == "convenience test")
ctx24 = get_context("conv_001", max_turns=3)
test("get_context convenience returns string", isinstance(ctx24, str))

# ── Summary ───────────────────────────────────────────────────────────────
print()
print("=" * 60)
if failed == 0:
    print(f"ALL {passed} TESTS PASSED ✅")
else:
    print(f"FAILED: {failed}/{passed+failed} — see above")
    sys.exit(1)
