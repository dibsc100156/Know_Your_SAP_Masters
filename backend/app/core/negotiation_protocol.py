"""
negotiation_protocol.py — Agent-to-Agent Negotiation Engine
=============================================================
Structured 4-phase conflict resolution when two or more domain agents
return contradictory information for the same query entity.

Phase 1: ASSERTION  — Each agent states its claim
Phase 2: CHALLENGE  — Agents challenge each other's claims
Phase 3: NEGOTIATE  — Propose and evaluate resolution strategies
Phase 4: COMMIT     — Final agreement recorded

Usage:
    from app.core.negotiation_protocol import NegotiationEngine, Negotiation, NegotiationPhase

    engine = NegotiationEngine()
    neg_id = engine.initiate(
        topic="vendor_LIFNR_0001_net_value",
        participants=["pur_agent", "bp_agent"],
        initial_assertions={
            "pur_agent": {"net_value": 125000, "currency": "EUR", "source": "EKKO"},
            "bp_agent":  {"net_value": 98500,  "currency": "EUR", "source": "LFB1"},
        }
    )
    # Run all phases
    result = engine.run_to_completion(neg_id)
"""

from __future__ import annotations

import json
import uuid
import time
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict

from app.core.message_bus import message_bus, AgentMessage, MessageType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NegotiationPhase(str, Enum):
    INIT         = "INIT"          # Negotiation created, waiting for assertions
    ASSERTING    = "ASSERTING"     # Phase 1: agents making assertions
    CHALLENGING  = "CHALLENGING"   # Phase 2: agents challenging
    NEGOTIATING  = "NEGOTIATING"   # Phase 3: proposals being made
    COMMITTED    = "COMMITTED"     # Phase 4: agreement reached
    REJECTED     = "REJECTED"      # Negotiation ended without agreement
    EXPIRED      = "EXPIRED"       # Took too long, auto-resolved

class ResolutionStrategy(str, Enum):
    AUTHORITY    = "AUTHORITY"     # Trust the agent with highest domain authority
    CONFIDENCE   = "CONFIDENCE"    # Choose the answer with highest confidence
    MERGE        = "MERGE"         # Combine both answers (field-level)
    AVERAGE      = "AVERAGE"       # Average numeric disagreements
    DEFER        = "DEFER"         # Cannot resolve, escalate
    MOST_RECENT  = "MOST_RECENT"   # Prefer the most recently updated record
    PREFER_SOURCE = "PREFER_SOURCE" # Prefer the authoritative source table (EKKO > LFB1 > LFA1)

# ---------------------------------------------------------------------------
# Assertion & Challenge Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Assertion:
    agent: str
    claim: Dict[str, Any]           # e.g. {"net_value": 125000, "currency": "EUR"}
    confidence: float = 0.8
    source_table: str = ""          # e.g. "EKKO", "LFB1", "BSIK"
    justification: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Assertion":
        return cls(**d)


@dataclass
class Challenge:
    challenger: str
    target_agent: str
    target_field: str               # e.g. "net_value"
    disputed_value: Any              # What the challenger disputes
    counter_value: Any               # What the challenger believes is correct
    evidence: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Challenge":
        return cls(**d)


@dataclass
class Proposal:
    proposer: str
    strategy: str                    # ResolutionStrategy value
    resolved_fields: Dict[str, Any] # e.g. {"net_value": 111750, "resolution_note": "averaged"}
    reasoning: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Proposal":
        return cls(**d)


# ---------------------------------------------------------------------------
# Negotiation Dataclass
# ---------------------------------------------------------------------------

@dataclass
class Negotiation:
    neg_id: str
    topic: str                      # What is being negotiated (entity+field, e.g. "LIFNR_0001_net_value")
    participants: List[str]         # Agent names involved
    phase: str = NegotiationPhase.INIT.value
    
    assertions: List[Dict[str, Any]] = field(default_factory=list)  # Assertion dicts
    challenges: List[Dict[str, Any]] = field(default_factory=list)  # Challenge dicts
    proposals: List[Dict[str, Any]] = field(default_factory=list)   # Proposal dicts
    
    resolution: Optional[Dict[str, Any]] = None  # Final agreed answer
    resolution_strategy: Optional[str] = None      # How it was resolved
    
    started_at: str = ""
    decided_at: Optional[str] = None
    expires_at: str = ""          # ISO-8601 auto-expiry

    # Authority ranking for AUTHORITY strategy
    authority_ranking: Dict[str, int] = field(default_factory=lambda: {
        "pur_agent": 5,   # purchasing agent trusts its own EKKO/LFA1 most
        "bp_agent":  4,   # BP agent uses LFB1/LFA1
        "mm_agent":  3,
        "sd_agent":  3,
        "qm_agent":  2,
        "wm_agent":  2,
        "cross_agent": 1, # cross_agent is mediator, lowest authority
    })

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.utcnow().isoformat() + "Z"
        if not self.expires_at:
            expires = datetime.utcnow().timestamp() + 30  # 30 second default TTL
            self.expires_at = datetime.fromtimestamp(expires).isoformat() + "Z"

    def is_expired(self) -> bool:
        try:
            expiry = datetime.fromisoformat(self.expires_at.rstrip("Z"))
            return datetime.utcnow() > expiry
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Negotiation":
        return cls(**d)


# ---------------------------------------------------------------------------
# Negotiation Engine
# ---------------------------------------------------------------------------

class NegotiationEngine:
    """
    Structured 4-phase conflict resolution between domain agents.
    
    Supports both:
    - SYNCHRONOUS: Run all phases in-memory (for simple cases)
    - ASYNCHRONOUS: Use message bus to exchange messages between agents (for real multi-agent)
    """

    # Authority ranking for SAP domain tables (higher = more authoritative)
    SOURCE_AUTHORITY = {
        # Purchasing
        "EKKO":  10, "EKPO":  9, "EINA":  8, "EINE":  8, "LFA1":  7, "LFB1":  7, "LFBK":  6,
        # Finance
        "BSEG":  10, "BKPF":  9, "BSIK":  8, "BSAK":  8,
        # Sales
        "VBAK":  9, "VBAP":  9, "LIKP":  8, "VBRK":  8,
        # Business Partner
        "BUT000": 7, "ADRC":  6,
        # Material
        "MARA":  8, "MARD":  7, "MBEW":  7,
    }

    def __init__(self, bus=None):
        self._bus = bus or message_bus
        self._negotiations: Dict[str, Negotiation] = {}
        self._handlers: List[Callable] = []

    # -------------------------------------------------------------------------
    # Initiate
    # -------------------------------------------------------------------------

    def initiate(
        self,
        topic: str,
        participants: List[str],
        initial_assertions: Optional[Dict[str, Dict[str, Any]]] = None,
        authority_ranking: Optional[Dict[str, int]] = None,
    ) -> str:
        """
        Start a new negotiation between agents.
        
        Args:
            topic: What is being negotiated (e.g. "LIFNR_0001_net_value")
            participants: List of agent names
            initial_assertions: {agent: {field: value}} initial claims
            
        Returns:
            neg_id: string negotiation identifier
        """
        neg_id = str(uuid.uuid4())
        
        assertions = []
        if initial_assertions:
            for agent, claim in initial_assertions.items():
                source = claim.pop("_source_table", "")
                conf = claim.pop("_confidence", 0.8)
                just = claim.pop("_justification", "")
                assertions.append(Assertion(
                    agent=agent,
                    claim=claim,
                    confidence=conf,
                    source_table=source,
                    justification=just,
                ).to_dict())

        neg = Negotiation(
            neg_id=neg_id,
            topic=topic,
            participants=participants,
            phase=NegotiationPhase.INIT.value,
            assertions=assertions,
        )
        
        if authority_ranking:
            neg.authority_ranking = authority_ranking

        self._negotiations[neg_id] = neg
        
        # Register in message bus
        self._bus.register_negotiation(neg_id, participants, topic)
        
        logger.info(f"[NEG] Initiated negotiation {neg_id[:8]} on '{topic}' between {participants}")
        return neg_id

    # -------------------------------------------------------------------------
    # Phase 1: Assert
    # -------------------------------------------------------------------------

    def submit_assertion(
        self,
        neg_id: str,
        agent: str,
        claim: Dict[str, Any],
        confidence: float = 0.8,
        source_table: str = "",
        justification: str = "",
    ) -> bool:
        """
        Agent submits its assertion for a negotiation.
        """
        neg = self._negotiations.get(neg_id)
        if not neg:
            logger.warning(f"[NEG] {neg_id[:8]}: Unknown negotiation")
            return False

        if agent not in neg.participants:
            logger.warning(f"[NEG] {neg_id[:8]}: {agent} not a participant")
            return False

        # Replace existing assertion from same agent
        neg.assertions = [a for a in neg.assertions if a.get("agent") != agent]
        neg.assertions.append(Assertion(
            agent=agent,
            claim=claim,
            confidence=confidence,
            source_table=source_table,
            justification=justification,
        ).to_dict())

        neg.phase = NegotiationPhase.ASSERTING.value
        
        # Broadcast assertion to other participants
        self._bus.publish(
            sender=agent,
            msg_type=MessageType.ASSERTION,
            content={"neg_id": neg_id, "topic": neg.topic, "claim": claim},
            conversation=neg_id,
        )

        logger.info(f"[NEG] {neg_id[:8]}: {agent} asserted {list(claim.keys())}")
        return True

    def all_assertions_received(self, neg_id: str) -> bool:
        """Check if all participants have submitted assertions."""
        neg = self._negotiations.get(neg_id)
        if not neg:
            return False
        asserted_agents = {a["agent"] for a in neg.assertions}
        return all(p in asserted_agents for p in neg.participants)

    # -------------------------------------------------------------------------
    # Phase 2: Challenge
    # -------------------------------------------------------------------------

    def submit_challenge(
        self,
        neg_id: str,
        challenger: str,
        target_agent: str,
        disputed_field: str,
        counter_value: Any,
        evidence: str = "",
    ) -> bool:
        """
        Agent challenges another agent's assertion on a specific field.
        """
        neg = self._negotiations.get(neg_id)
        if not neg:
            return False

        challenge = Challenge(
            challenger=challenger,
            target_agent=target_agent,
            target_field=disputed_field,
            disputed_value=self._get_agent_claim(neg, target_agent, disputed_field),
            counter_value=counter_value,
            evidence=evidence,
        ).to_dict()

        neg.challenges.append(challenge)
        neg.phase = NegotiationPhase.CHALLENGING.value

        # Notify target agent
        self._bus.publish(
            sender=challenger,
            receiver=target_agent,
            msg_type=MessageType.CHALLENGE,
            content={"neg_id": neg_id, "challenge": challenge},
            conversation=neg_id,
            priority=2,
        )

        logger.info(f"[NEG] {neg_id[:8]}: {challenger} challenged {target_agent}.{disputed_field}")
        return True

    def _get_agent_claim(self, neg: Negotiation, agent: str, field: str) -> Any:
        for a in neg.assertions:
            if a.get("agent") == agent:
                return a.get("claim", {}).get(field)
        return None

    # -------------------------------------------------------------------------
    # Phase 3: Propose
    # -------------------------------------------------------------------------

    def submit_proposal(
        self,
        neg_id: str,
        proposer: str,
        strategy: ResolutionStrategy,
        resolved_fields: Dict[str, Any],
        reasoning: str = "",
    ) -> bool:
        """
        Agent proposes a resolution strategy.
        """
        neg = self._negotiations.get(neg_id)
        if not neg:
            return False

        proposal = Proposal(
            proposer=proposer,
            strategy=strategy.value if isinstance(strategy, ResolutionStrategy) else strategy,
            resolved_fields=resolved_fields,
            reasoning=reasoning,
        ).to_dict()

        neg.proposals.append(proposal)
        neg.phase = NegotiationPhase.NEGOTIATING.value

        # Broadcast proposal
        self._bus.publish(
            sender=proposer,
            msg_type=MessageType.NEGOTIATE,
            content={"neg_id": neg_id, "proposal": proposal},
            conversation=neg_id,
        )

        logger.info(f"[NEG] {neg_id[:8]}: {proposer} proposed {strategy.value}")
        return True

    # -------------------------------------------------------------------------
    # Phase 4: Commit
    # -------------------------------------------------------------------------

    def commit(
        self,
        neg_id: str,
        resolution: Dict[str, Any],
        strategy: ResolutionStrategy,
    ) -> Dict[str, Any]:
        """
        Finalize a negotiation with the agreed resolution.
        """
        neg = self._negotiations.get(neg_id)
        if not neg:
            return {"error": "negotiation not found"}

        neg.resolution = resolution
        neg.resolution_strategy = strategy.value if isinstance(strategy, ResolutionStrategy) else strategy
        neg.phase = NegotiationPhase.COMMITTED.value
        neg.decided_at = datetime.utcnow().isoformat() + "Z"

        # Remove from message bus registry
        self._bus.resolve_negotiation(neg_id)

        # Broadcast COMMIT to all participants
        self._bus.broadcast(
            sender="negotiation_engine",
            msg_type=MessageType.COMMIT,
            content={
                "neg_id": neg_id,
                "topic": neg.topic,
                "resolution": resolution,
                "strategy": neg.resolution_strategy,
                "duration_ms": (
                    datetime.fromisoformat(neg.decided_at.rstrip("Z"))
                    - datetime.fromisoformat(neg.started_at.rstrip("Z"))
                ).total_seconds() * 1000,
            },
            conversation=neg_id,
        )

        logger.info(f"[NEG] {neg_id[:8]}: COMMITTED using {strategy.value} → {resolution}")
        return resolution

    # -------------------------------------------------------------------------
    # Auto-Resolution (Synchronous Helper)
    # -------------------------------------------------------------------------

    def auto_resolve(
        self,
        neg_id: str,
        strategy: ResolutionStrategy = ResolutionStrategy.AVERAGE,
    ) -> Dict[str, Any]:
        """
        Automatically resolve a negotiation without agent exchange.
        Useful when assertions are already known.
        """
        neg = self._negotiations.get(neg_id)
        if not neg:
            return {"error": "negotiation not found"}

        if len(neg.assertions) < 2:
            # Only one assertion — just use it
            return self.commit(neg_id, neg.assertions[0]["claim"], ResolutionStrategy.AUTHORITY)

        return self.commit(neg_id, self._compute_resolution(neg, strategy), strategy)

    def _compute_resolution(self, neg: Negotiation, strategy: ResolutionStrategy) -> Dict[str, Any]:
        """Compute the resolved answer using the given strategy."""
        all_fields: Set[str] = set()
        for a in neg.assertions:
            all_fields.update(a["claim"].keys())

        resolved = {}
        notes = []

        for field in all_fields:
            values = {}
            sources = {}
            confidences = {}
            
            for a in neg.assertions:
                val = a["claim"].get(field)
                if val is not None:
                    agent = a["agent"]
                    values[agent] = val
                    sources[agent] = a.get("source_table", "")
                    confidences[agent] = a.get("confidence", 0.8)

            if len(values) == 1:
                # Only one value — no conflict
                resolved[field] = list(values.values())[0]
                continue

            # Multiple conflicting values
            strategy_key = strategy.value if isinstance(strategy, ResolutionStrategy) else strategy

            if strategy_key == ResolutionStrategy.AVERAGE.value:
                nums = [v for v in values.values() if isinstance(v, (int, float))]
                if nums:
                    avg = sum(nums) / len(nums)
                    resolved[field] = round(avg, 2)
                    notes.append(f"{field}: averaged from {len(nums)} sources")
                else:
                    resolved[field] = list(values.values())[0]

            elif strategy_key == ResolutionStrategy.AUTHORITY.value:
                best_agent = max(values, key=lambda a: neg.authority_ranking.get(a, 0))
                resolved[field] = values[best_agent]
                notes.append(f"{field}: authority={best_agent}")

            elif strategy_key == ResolutionStrategy.CONFIDENCE.value:
                best_agent = max(values, key=lambda a: confidences.get(a, 0))
                resolved[field] = values[best_agent]
                notes.append(f"{field}: confidence={confidences[best_agent]:.2f}")

            elif strategy_key == ResolutionStrategy.MOST_RECENT.value:
                # Pick the assertion with newest data
                best = max(neg.assertions, key=lambda a: a.get("timestamp", ""))
                resolved[field] = best["claim"].get(field, values[list(values.keys())[0]])
                notes.append(f"{field}: most_recent={best['agent']}")

            elif strategy_key == ResolutionStrategy.PREFER_SOURCE.value:
                # Prefer the higher-authority source table
                best_agent = max(values, key=lambda a: self.SOURCE_AUTHORITY.get(sources.get(a, ""), 0))
                resolved[field] = values[best_agent]
                notes.append(f"{field}: source={sources[best_agent]}")

            else:
                # Default: use first assertion
                first_agent = list(values.keys())[0]
                resolved[field] = values[first_agent]
                notes.append(f"{field}: default={first_agent}")

        resolved["_resolution_note"] = "; ".join(notes)
        resolved["_strategy_used"] = strategy.value if isinstance(strategy, ResolutionStrategy) else strategy
        return resolved

    # -------------------------------------------------------------------------
    # Run to Completion (Synchronous)
    # -------------------------------------------------------------------------

    def run_to_completion(
        self,
        neg_id: str,
        strategy: ResolutionStrategy = ResolutionStrategy.AVERAGE,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Run all 4 phases to completion synchronously.
        For asynchronous multi-agent, use the message bus instead.
        """
        neg = self._negotiations.get(neg_id)
        if not neg:
            return {"error": "negotiation not found"}

        deadline = time.time() + timeout_seconds

        # Phase 1: Wait for all assertions (max timeout)
        while not self.all_assertions_received(neg_id):
            if time.time() > deadline:
                return self.auto_resolve(neg_id, strategy)
            time.sleep(0.1)

        neg.phase = NegotiationPhase.CHALLENGING.value

        # Phase 2: Detect and register challenges (check for field conflicts)
        self._auto_detect_challenges(neg)

        neg.phase = NegotiationPhase.NEGOTIATING.value

        # Phase 3: Auto-generate proposal using selected strategy
        self._auto_propose(neg, strategy)

        # Phase 4: Commit
        return self.auto_resolve(neg_id, strategy)

    def _auto_detect_challenges(self, neg: Negotiation) -> None:
        """Auto-detect field-level conflicts as challenges."""
        all_fields: Set[str] = set()
        for a in neg.assertions:
            all_fields.update(a["claim"].keys())

        for field in all_fields:
            values = {}
            for a in neg.assertions:
                val = a["claim"].get(field)
                if val is not None:
                    values[a["agent"]] = val

            if len(values) > 1:
                # There's a conflict — generate challenges from all non-first agents
                base_agent = list(values.keys())[0]
                base_value = values[base_agent]
                for agent, value in list(values.items())[1:]:
                    if value != base_value:
                        neg.challenges.append(Challenge(
                            challenger=agent,
                            target_agent=base_agent,
                            target_field=field,
                            disputed_value=base_value,
                            counter_value=value,
                            evidence=f"auto-detected conflict: {value} vs {base_value}",
                        ).to_dict())

    def _auto_propose(self, neg: Negotiation, strategy: ResolutionStrategy) -> None:
        """Auto-generate a proposal for each participant."""
        for participant in neg.participants:
            proposal = Proposal(
                proposer=participant,
                strategy=strategy.value if isinstance(strategy, ResolutionStrategy) else strategy,
                resolved_fields=self._compute_resolution(neg, strategy),
                reasoning=f"Auto-proposed using {strategy.value} strategy",
            ).to_dict()
            neg.proposals.append(proposal)

    # -------------------------------------------------------------------------
    # Getters
    # -------------------------------------------------------------------------

    def get(self, neg_id: str) -> Optional[Negotiation]:
        return self._negotiations.get(neg_id)

    def list_active(self) -> List[Negotiation]:
        return [
            n for n in self._negotiations.values()
            if n.phase not in (NegotiationPhase.COMMITTED.value, NegotiationPhase.REJECTED.value, NegotiationPhase.EXPIRED.value)
        ]
