# Inter-Agent Message Bus & Negotiation Protocol
## Design — Phase 13: Agentic Communication Fabric

---

## 1. Problem Statement

Currently, domain agents operate in **isolation**:
- The Planner dispatches tasks to agents
- Agents execute independently and return results
- The Synthesis Agent merges results at the end
- **Agents never talk to each other mid-execution**

This prevents:
- Agents from **asking each other questions** during execution
- **Conflict resolution** when two agents return contradictory data
- **Collaborative reasoning** where one agent's partial answer informs another's
- **Task delegation** where a specialist agent defers to a peer

---

## 2. Architecture

### 2.1 Message Bus (`message_bus.py`)

A **Redis pub/sub** backed message bus enabling agents to exchange structured messages in real-time.

**Message Schema:**
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
- `publish(sender, receiver, msg_type, content)` — send a message
- `broadcast(sender, msg_type, content)` — send to all agents
- `subscribe(agent_name)` — listen for messages addressed to this agent
- `reply(msg, content)` — respond to a specific message
- `get_messages(agent_name, since=None)` — poll for messages

**Implementation:** Redis Streams + pub/sub. Streams provide persistence and consumer groups. Pub/sub provides real-time delivery.

### 2.2 Negotiation Protocol (`negotiation_protocol.py`)

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

**Negotiation Record:**
```python
@dataclass
class Negotiation:
    neg_id: str
    topic: str                    # What is being negotiated (e.g. "vendor_LIFNR_001_net_value")
    participants: List[str]        # Agent names involved
    phase: NegotiationPhase
    assertions: List[Assertion]     # Phase 1: Each agent's claim
    challenges: List[Challenge]    # Phase 2: Challenges to assertions
    proposals: List[Proposal]    # Phase 3: Resolution proposals
    resolution: Optional[Dict]    # Phase 4: Final agreed answer
    started_at: str
    decided_at: Optional[str]
```

**Resolution Strategies:**
- `AUTHORITY` — Trust the agent with highest domain authority for this topic
- `CONFIDENCE` — Choose the answer with highest confidence score
- `MergerGE` — Combine both answers if fields are complementary
- `DEFER` — Escalate to human (not implemented in v1)
- `TIMESTAMP` — Choose the most recent data

### 2.3 Agent Inbox (`agent_inbox.py`)

Each agent has a **personal inbox** backed by Redis sorted sets:
- `inbox:{agent_name}` — messages addressed to this agent, scored by timestamp
- `inbox:{agent_name}:conversations` — active conversation threads
- `inbox:{agent_name}:negotiations` — ongoing negotiations

Agents **poll their inbox** during execution. If they receive a message:
- `QUERY` → Answer based on their expertise and reply
- `CHALLENGE` → Re-evaluate their answer and respond
- `NEGOTIATE` → Enter negotiation state machine

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

## 4. Files to Create

| File | Description |
|------|-------------|
| `app/core/message_bus.py` | `MessageBus`, `AgentMessage`, `MessageType` |
| `app/core/negotiation_protocol.py` | `Negotiation`, `NegotiationEngine`, `ResolutionStrategy` |
| `app/core/agent_inbox.py` | Per-agent inbox backed by Redis sorted sets |
| `app/agents/swarm/message_dispatcher.py` | Integration layer: intercepts agent calls and routes through bus |

---

## 5. Backward Compatibility

- Message Bus is **opt-in** — agents can still run in pure isolated mode
- If Redis is unavailable, bus silently degrades to no-op
- Existing agent API unchanged — only the execution layer is augmented
- `use_message_bus=True` flag on `planner.execute()` enables the protocol
