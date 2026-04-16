# Inter-Agent Message Bus & Negotiation Protocol
## Phase 13: Agentic Communication Fabric — ✅ IMPLEMENTED (April 15, 2026)

---

## Status (April 16, 2026)

Phase 13 is **IMPLEMENTED** as of April 15, 2026. Three of the four planned components are live.
`agent_inbox.py` remains **🚧 Pending** — the Redis sorted-set inbox pattern was replaced by
streaming `get_inbox()` and `get_conversation()` methods inside `message_bus.py` for v1.

---

## 1. Problem Statement

**Originally:** Domain agents operated in **isolation**:
- The Planner dispatched tasks to agents
- Agents executed independently and returned results
- The Synthesis Agent merged results at the end
- **Agents never talked to each other mid-execution**

This prevented:
- Agents from **asking each other questions** during execution
- **Conflict resolution** when two agents returned contradictory data
- **Collaborative reasoning** where one agent's partial answer informed another's
- **Task delegation** where a specialist agent defers to a peer

**Solved by Phase 13:** All four gaps are now addressed via the Redis-backed Message Bus.

---

## 2. Architecture

### 2.1 Message Bus (`message_bus.py`) — ✅ IMPLEMENTED

A **Redis pub/sub + Streams** backed message bus enabling agents to exchange structured
messages in real-time.

**Message Schema (`AgentMessage` dataclass):**
```python
@dataclass
class AgentMessage:
    msg_id:       str           # UUID
    sender:       str           # agent name (e.g. "pur_agent")
    receiver:     Optional[str] # None = broadcast
    msg_type:     MessageType   # QUERY | RESPONSE | ASSERTION | CHALLENGE | NEGOTIATE | COMMIT
    content:      Dict[str, Any]
    conversation: str           # conversation ID for threading
    priority:     int           # 0=low, 1=normal, 2=high, 3=urgent
    ttl_seconds:  int           # message expiry
    timestamp:    str           # ISO-8601
    reply_to:     Optional[str] # msg_id this is in response to
```

**Message Types:**
- `QUERY` — "Can you answer this for me?" (ask another agent)
- `RESPONSE` — Reply to a QUERY
- `ASSERTION` — "I assert X is true based on my data"
- `CHALLENGE` — "I dispute X — my data shows Y"
- `NEGOTIATE` — Proposal to resolve a conflict
- `COMMIT` — Final agreement reached

**Bus Operations:**
- `publish(sender, receiver, msg_type, content)` — send a direct message
- `broadcast(sender, msg_type, content)` — send to all agents
- `subscribe(agent_name)` — listen for messages addressed to this agent
- `reply(msg, content)` — respond to a specific message
- `get_messages(agent_name, since=None)` — poll for messages
- `get_inbox(agent_name, limit=50)` — stream-based inbox retrieval
- `get_conversation(conv_id)` — retrieve full conversation thread
- `register_negotiation(neg_id, topic, participants)` — register active negotiation
- `agent_status(agent_name)` — check if agent is alive

**Implementation:** Redis Streams (persistence + consumer groups) + pub/sub (real-time delivery).
Streams provide durability for谈判 records; pub/sub delivers real-time QUERY/RESPONSE delivery.

### 2.2 Negotiation Protocol (`negotiation_protocol.py`) — ✅ IMPLEMENTED

A **structured 4-phase conflict resolution** protocol when agents have data conflicts.

**4-Phase Negotiation:**
```
Phase 1: ASSERTION  — Each agent states its position
Phase 2: CHALLENGE  — Agents challenge each other's assertions
Phase 3: NEGOTIATE  — Propose resolution (e.g. merge, prefer higher-confidence, defer to authority)
Phase 4: COMMIT     — Agree on final answer
```

**Negotiation States:**
```
PROPOSING → COUNTERING → ACCEPTING → COMMITTED
         ↘ REJECTING → ENDING
```

**Resolution Strategies:**
- `AUTHORITY` — Trust the agent with highest domain authority for this topic
- `CONFIDENCE` — Choose the answer with highest confidence score
- `MERGE` — Combine both answers if fields are complementary
- `AVERAGE` — Numeric values averaged (verified: EKKO 125K vs LFB1 98.5K → 111,750 EUR)
- `MOST_RECENT` — Choose the most recent data
- `PREFER_SOURCE` — Defer to authoritative SAP source table (EKKO/BSEG = 10, LFA1/KNA1 = 7)

**SOURCE_AUTHORITY Rankings (partial):**
| Table | Authority | Table | Authority |
|---|---|---|---|
| EKKO | 10 | BSEG | 10 |
| LFA1 | 7 | KNA1 | 7 |
| MARA | 7 | VBAK | 7 |
| MBEW | 6 | MSEG | 6 |

### 2.3 Message Dispatcher + Agent Registry (`message_dispatcher.py`) — ✅ IMPLEMENTED

Integration layer that intercepts agent calls and routes through the message bus.

**AgentRegistry** defines 7 domain agents:
```python
AGENT_REGISTRY = {
    "bp_agent":   AgentConfig(subscriptions=["vendor","customer","credit"],  authority=7),
    "mm_agent":   AgentConfig(subscriptions=["material","stock","valuation"], authority=7),
    "pur_agent":  AgentConfig(subscriptions=["purchase order","contract"],   authority=8),
    "sd_agent":   AgentConfig(subscriptions=["sales order","delivery"],      authority=7),
    "qm_agent":   AgentConfig(subscriptions=["quality","inspection"],        authority=7),
    "wm_agent":   AgentConfig(subscriptions=["warehouse","storage bin"],      authority=6),
    "cross_agent":AgentConfig(subscriptions=["*"],                             authority=10),
}
```

**Core methods:**
- `query_agent(from_agent, to_agent, question, timeout=10)` — synchronous REQUEST/RESPONSE
- `detect_and_negotiate(agent_results)` — auto-detect field conflicts, trigger Negotiation Protocol
- `execute_with_bus(task, agent_name)` — async inbox listener per agent
- `route_via_negotiation(conflicts)` — 4-phase negotiation execution

### 2.4 Agent Inbox (`agent_inbox.py`) — 🚧 PENDING

Originally designed as a separate file using Redis sorted sets. For v1, inbox functionality
was absorbed into `message_bus.py` via `get_inbox()` and `get_conversation()` methods on the
`MessageBus` class. The separate `agent_inbox.py` file was not created.

**Pending work:**
- Extract inbox logic into a dedicated `agent_inbox.py` for cleaner separation of concerns
- Redis sorted-set backing: `inbox:{agent_name}` (score = timestamp)
- `inbox:{agent_name}:conversations` — active conversation threads
- `inbox:{agent_name}:negotiations` — ongoing negotiations
- Per-agent polling loop with exponential backoff

---

## 3. Example Flows

### Flow 1: Cross-Agent Query
```
User: "What is the net value of purchase order 4500001234?"
  → Planner routes to PURAgent
  → PURAgent queries CROSSAgent: "Can you confirm the vendor for PO 4500001234?"
  → CROSSAgent responds: LFA1.NAME1 = "Acme Corp"
  → PURAgent includes vendor name in answer
```

### Flow 2: Data Conflict Negotiation
```
User: "Show me vendor Acme's total open PO value"
  → Planner routes to PURAgent + BPAgent in parallel
  → PURAgent returns: net_value = 125,000 EUR
  → BPAgent returns: net_value = 125,000 EUR
  → SynthesisAgent detects consistent — no negotiation needed

OR:

  → PURAgent returns: net_value = 125,000 EUR
  → BPAgent returns: net_value = 98,500 EUR  (conflicts!)
  → Negotiation initiated between PURAgent and BPAgent
  → Phase 1: PURAgent asserts 125K, BPAgent asserts 98.5K
  → Phase 2: BPAgent challenges — "My LFB1 condition type says 98.5K"
  → PURAgent reviews — "Ah, 125K includes a pending scheduling agreement"
  → Phase 3: Both propose merging — 125K + 98.5K / 2 = 111,750 EUR
  → Phase 4: COMMIT — {avg_value: 111,750, note: "averaged from conflicting sources"}
```

---

## 4. Files

| File | Description | Status |
|------|-------------|--------|
| `app/core/message_bus.py` | `MessageBus`, `AgentMessage`, `MessageType`, Redis pub/sub + streams | ✅ **IMPLEMENTED — Apr 15** |
| `app/core/negotiation_protocol.py` | `Negotiation`, `NegotiationEngine`, 6 `ResolutionStrategy` | ✅ **IMPLEMENTED — Apr 15** |
| `app/agents/swarm/message_dispatcher.py` | `MessageDispatcher`, `AGENT_REGISTRY`, `query_agent()`, `detect_and_negotiate()` | ✅ **IMPLEMENTED — Apr 15** |
| `app/core/agent_inbox.py` | Per-agent inbox backed by Redis sorted sets | 🚧 **Pending** — absorbed into `message_bus.py` for v1 |

---

## 5. Backward Compatibility

- Message Bus is **opt-in** — agents can still run in pure isolated mode
- If Redis is unavailable, bus silently degrades to no-op
- Existing agent API unchanged — only the execution layer is augmented
- `use_message_bus=True` flag on `planner.execute()` enables the protocol (future)
