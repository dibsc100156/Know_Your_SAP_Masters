# Harness Engineering  --  Design Principles
## Video Summary: "Andrej Karpathy's Math Proves Agent Skills Will Fail. Here's What to Build Instead."
**Channel:** The AI Automators | **Published:** March 21, 2026 | **Views:** 70K+ | **Likes:** 2,329
**URL:** https://youtu.be/I2K81s0OQto

---

## Core Thesis: The Reliability Problem

Karpathy's **"March of Nines"** is the central insight. The math is brutal:

> A 10-step agentic workflow where each step is **90% reliable** will only work **34.9% of the time**.
> That's ~6 failures per 8-hour workday. At 99% per step → 90.4% success rate.

**The conclusion:** Agent skills (prompting techniques) alone cannot close this gap. You cannot prompt your way to production-grade reliability. The solution is **harness engineering**  --  putting AI on **deterministic rails** with validation loops, state management, and programmatic control.

---

## Agent Skills vs Harness Engineering

| Dimension | Agent Skills | Harness Engineering |
|---|---|---|
| **What it controls** | Prompt instructions | Tool selection, routing, execution guards |
| **Reliability mechanism** | Better prompting | Validation loops, phase gates, fallback paths |
| **Failure handling** | Hopeful | Deterministic |
| **Scales with model?** | Yes, but plateaus | Yes, orthogonally |
| **Analogy** | Teaching the model what to do | Building guardrails around the model |
| **Best for** | Simple, single-step tasks | Complex, multi-step, production workflows |

---

## The March of Nines (Karpathy's Math)

```
Per-step reliability    Workflow steps    End-to-end success
90%   (prompt engineering)    10         34.9%   ← 65% of tasks fail
95%                        10         59.9%
99%                        10         90.4%   ← "Five Nines" target
99.9%                       10         99.0%
```

**The insight:** At 90% per step, a 10-step workflow fails 2 out of 3 times. At 99% per step, you cross the 90% threshold. Closing this 9% gap between 90% and 99% is what harness engineering is specifically designed to do.

---

## Stripe's Minions: The Proof of Harness Power

Stripe's **Minions** system (Boris Chen / Stripe Conf 2025) is the canonical example:

- Minions is an AI coding agent that handles **on-call production incidents** autonomously
- Minions has access to a **narrow but deeply integrated tool set**: runbooks, deployment systems, rollback procedures, alerting dashboards, code search
- **1,300 production PRs/week**  --  zero human code review for routine changes
- The narrow but deeply integrated tools (the harness) are what make this possible, not the model

---

## 12 Design Principles for Agentic Harness Engineering

### Principle 1: Define the Agent's Boundary
The agent should know what it owns and what it doesn't. Tools outside the agent's scope should be absent from its context, not denied at runtime.

### Principle 2: Validate Before Every Handoff
Between every phase, run a validator. Pass state forward only when the validator confirms the output is safe for the next phase.

### Principle 3: Name Every Tool Explicitly
Don't let the model guess from a list. The harness tells the model: *"Use TOOL_X for Y."* The model chooses whether, not which.

### Principle 4: Make Failures Loud and Structured
A tool failure should return a structured error `{tool, error_code, message, recovery_hint}` not a string. The harness, not the model, decides what to do with the error.

### Principle 5: Write Tool Descriptions as Contracts
Tool descriptions are not documentation  --  they are the interface contract between the harness and the model. Include: input schema, output schema, error modes, preconditions.

### Principle 6: The Harness Must Be Versioned
When you update a tool's behavior, both the tool and the harness version must increment. A model running against a harness is a deployment. Treat it like one.

### Principle 7: Design for Tool Failure, Not Tool Success
Most agent frameworks test for happy paths. A production harness is defined by how it behaves when 30% of tool calls fail, retry, or return partial data.

### Principle 8: Use Phase Gates to Reset Context
In long-running workflows, context degrades. Phase gates provide natural restart points where the harness can provide a fresh context window without losing state.

### Principle 9: The Model Should Know the Harness Exists
System prompt: *"You are inside a tool-harness system. You have these tools. The harness will validate your outputs. Use tools confidently  --  they are integrated, not called."*

### Principle 10: Make Tool Calling Boring
The most reliable agents call tools with the same predictability as a database query. If your agent is "deciding" whether to call a tool, the harness hasn't been designed clearly enough.

### Principle 11: Benchmark the Harness, Not Just the Model
Test harness reliability by measuring: mean time between failures, recovery success rate, false positive rate of validators. These are boardroom metrics.

### Principle 12: The Model Is Interchangeable; The Harness Is the Moat
OpenAI, Anthropic, Google, DeepSeek  --  the model layer commoditizes fast. The harness layer  --  tool integrations, validated workflows, phase orchestration  --  is what takes years to build. Build the moat.

---

## Phase Architecture: 8-Phase Contract Harness

The validated agentic workflow is structured as **8 sequential phases**, each gated by a contract validator:

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6 ──► Phase 7
 Query      Routing    Discovery   Planning    Assembly   Validation  Execution   Response
            (intent)   (schema)    (tool sel)  (SQL)     (dry-run)   (real DB)   (masked)
```

Each phase transition requires a **PhaseState record** in Redis:
- `phase`: phase name
- `status`: running | completed | failed
- `validator_fired`: bool
- `validator_errors`: List[str]
- `artifacts`: Dict[str, Any]  --  outputs passed to next phase

This is the **Harness Runs Table**  --  a structured audit trail for every query.

---

## Key Quote

> *"The model isn't the bottleneck. The harness is. More tools doesn't mean more capability  --  it means more failure surface."*
>  --  Cyril Imhof, This is the Year, Episode 44

---

## Video 2: Harness Engineering  --  The Skill That Will Define 2026 for Solo Devs
**Channel:** Solo Swift Crafter (Daniel) | **Published:** February 24, 2026 | **Views:** ~29K | **Likes:** 943 | **Duration:** 14:14
**URL:** https://youtu.be/DN2mhf0b02s

---

### Core Thesis: The Model Isn't the Bottleneck  --  The Harness Is

Daniel opens with a sharp provocation: *"What's the best AI model? Claude? GPT? Gemini? That's the wrong question."*

And the data backs him:

> A recent study tested every major frontier model on real professional tasks  --  the best one completed only **24%** of them.

The other 76% failed not because of model capability, but because of tool failures, context overflows, and planning breakdowns.

**Key evidence:**
- **Vercel** stripped 80% of tools from their agent → accuracy jumped from **80% → 100%**
- **Manus** rebuilt their entire framework **5 times in 6 months**  --  same lesson every time
- Every major AI team (OpenAI, Anthropic, Vercel) independently arrived at the same conclusion

**The conclusion:** The model is not the bottleneck. The harness is. More tools does not equal more capability  --  it equals more failure surface.

---

### The Three Failure Modes (and How to Fix Each)

#### Failure Mode 1: Tool Bloat

Every extra tool your agent can call is a new failure pathway. Vercel's case study is the clearest proof:
- Their agent had dozens of tools → accuracy ~80%
- They cut tools by 80% (kept only the highest-confidence ones) → accuracy jumped to **100%**

**Fix:** Audit every tool your agent has access to. Ask: *If this tool fails, does the whole workflow fail?* If yes  --  add a fallback or remove it from the active set for this phase.

#### Failure Mode 2: Context Overflow

Agents accumulate conversation history, tool descriptions, and system instructions across long sessions. Past ~3,000 tokens of chat history, performance degrades exponentially.

**Fix:** Implement **context budgeting**  --  at each phase start, give the agent only:
- The current task description
- Relevant domain knowledge (from a skills/library file, not embedded in the prompt)
- The validated output of the previous phase

Do NOT provide the full conversation history, all available tools, and all system instructions simultaneously.

#### Failure Mode 3: Planning Collapse

Without explicit phase boundaries, agents re-plan mid-execution  --  making contradictory decisions as context shifts. This is invisible until a workflow fails at step 7 of 10.

**Fix:** **Phase-gated execution**  --  the agent must complete and validate one phase before the next unlocks. Each phase has an explicit entry condition, a validator, and an exit condition.

---

### Three Things You Can Try Today (for Solo Devs)

#### 1. Tool Audit  --  Cut Your Agent's Attack Surface

List every tool your agent has access to. For each one, ask:
- Does this tool fail gracefully or hard-fail the whole workflow?
- Is this tool needed for the current phase?
- If I remove it, does the agent still function?

**Rule of thumb:** If a tool is not needed for the current phase, remove it from context entirely. Scoped tool sets > comprehensive tool lists.

#### 2. Phase Boundaries  --  Add Validation Gates

Break your agent's workflow into explicit phases. Between each phase, run a validator that checks:
- Did the agent produce the expected output type?
- Are all required fields present?
- Is the output safe to pass to the next phase?

Only proceed when validation passes. This is the **harness loop**  --  the agent runs inside it, not outside.

**Harness loop structure:**
```
Phase N executes
    → Validator runs (schema check, business rule check, output contract check)
    → pass? → Phase N+1
    → fail? → Self-correction loop (fixed retries)
    →      → Escalate OR fail loudly
```

#### 3. Context Budgeting  --  Give Each Phase a Fresh Context

At each phase start, the agent receives:
- Task description (current goal)
- Domain knowledge (from external files, not embedded in system prompt)
- Validated output of previous phase

**Stop doing:** Providing full conversation history + all tools + all system instructions simultaneously.

---

### What Manus's 5 Rebuilds Taught Everyone

Manus rebuilt their entire framework 5 times in 6 months. Each rebuild was triggered by a new failure mode they hadn't accounted for. The pattern:

> Framework maturity = accumulated failure mode coverage.

Every failure added a new harness gate. The final framework was not more capable than the original  --  it had more failure mode coverage. The harness grew by surviving failures, not by upgrading the model.

**Implication for KYSM:** The Phase 10 Swarm is the 5th iteration of the routing architecture. Each failure mode (schema enumeration, DML injection, cross-module sprawl) has been covered by a specific harness gate (sentinel, validation harness, typed contracts). The next iteration should add typed output contracts enforced at synthesis time.

---

### KYSM Gap Analysis (Updated)

| Principle | Implementation | Status |
|---|---|---|
| Scoped Tool Sets | TOOL_REGISTRY  --  52 tools active per domain | ✅ |
| Phase-Gated Execution | `_update_harness_phase()`  --  each phase tracked before next starts | ✅ |
| Context Budgeting | Graph embedding search surfaces only top-K tables per phase | ✅ |
| Tool Audit | Vercel proof: cut 80% of tools → 100% accuracy | ✅ Design validated |
| Validation Gates | `validate_contract()`  --  domain agents validated before synthesis | ✅ Wired |
| Failure Attribution | `PhaseState.validator_fired` + `validator_errors` in Redis | ✅ |
| Context Freshness | Each domain agent gets isolated run context | 🚧 Domain agent run_id wiring done |
| Typed Contracts at Merge | `validate_contract()` called in `synthesis_agent.synthesize()` before `_merge_results()`  --  failures flag but never block | ✅ Wired (April 13, 2026) |

---

### Key Quotes

> *"The model isn't the bottleneck. The harness is. More tools doesn't mean more capability  --  it means more failure surface."*

> *"Framework maturity = accumulated failure mode coverage. Every failure taught them to add a new harness gate."*

---

### Timestamps

- `0:00`  --  Hook
- `1:15`  --  You Keep Chasing the Best Model
- `4:45`  --  Your Agent Chokes Because You Gave It Too Much
- `8:15`  --  Stop Agonizing Over Models
- `12:00`  --  Outro + Crafter's Lab Deep Dive

---

## Video 3: AI Agent Harness is Here  --  This is the Year, Episode 44
**Channel:** This is the Year (Cyril Imhof) | **Published:** ~April 2026 | **Episode:** 44 | **URL:** https://youtu.be/ZqM5kbB0D4o

---

### Overview

Cyril Imhof's "This is the Year" is a weekly series on AI developments. Episode 44 focuses entirely on **AI Agent Harness Engineering**  --  what it is, why it matters commercially, the paywall gap between frontier models and open-source, and the emerging skills marketplace.

This is a distinctly **commercial and strategic** perspective on harness engineering  --  less about the math (Karpathy) or the solo-dev tactics (Solo Swift Crafter), more about how harnesses create real business value and competitive moats.

---

### What Is a Harness?  --  The Foundational Definition

Imhof opens with a precise definition that serves as the episode's anchor:

> **A harness is a group of tools + instructions on how to use them  --  bundled together as a coherent operational system for an AI agent.**

The evolution tracked:
- **2022-2023:** Single tools  --  one tool, one task. "Tools became a thing to connect agents to the outside world. One or two tools were probably enough."
- **2024:** Tool selection improved  --  models got better at choosing which tool to use. The term shifted to **toolkits** and **tool sets**.
- **2025:** The term converged: **harness**  --  a tool harness. It's a group of tools with explicit instructions on how to deploy them.

**Analogy:** A surgeon's tools are only useful in the context of a surgical harness  --  the operating room, sterile protocols, instrument trays, the assistant's timing. A model given tool descriptions without a harness is like handing a scalpel to someone outside the OR.

**The example given:** OpenClaw  --  which decoded all the "harnesses that coding agents like Copilot already had, but added all the tools people were missing in day-to-day life: access to computer files, calendar, email, WhatsApp, Telegram." The result: "People don't have to open a specific app. They just talk to it through iMessage."

---

### The Core Thesis: Harnesses Are the Real Product

The episode's central argument:

> The large language model by itself is commoditized infrastructure. The harness is the actual product.

This mirrors the "model is interchangeable; harness is the moat" principle from the AI Automators video, but Imhof makes the commercial case with specific evidence:

**Anthropic/Claude Max ($200/month):**
- You can get Claude on AWS Bedrock for a fraction of the cost
- But: "99% of the harness that you get in the cloud app is not available out of the box on Bedrock"
- The $200/month premium is **pure harness value**  --  not model intelligence

**The intelligence vs harness gap in Claude 4.5 → 4.6:**
- The raw capability increase between Opus 4.5 and Opus 4.6 was modest in pure intelligence
- What increased **significantly** was harness capability: tool calling, tool sets, tool arrays, and connectors
- This is precisely why users upgraded from Pro ($20) to Max ($200)  --  not for more raw intelligence, but for better harness
- The result: "Coding agents became incredibly much better because of better harnesses. Excel agents, PowerPoint agents  --  all lot better because of the harness and because of the skills now being injected"

---

### The Paywall Gap: Frontier Model vs Open-Source

Imhof articulates a key commercial dynamic:

| Layer | Frontier Model (Claude Max, GPT-5) | Open-Source (Llama, DeepSeek) |
|---|---|---|
| **Model intelligence** | Available via API/Bedrock | Available at comparable levels |
| **Harness (tools + instructions)** | **Paywalled inside the app** | Not available out of the box |
| **Skills (domain-specific integrations)** | Shipped with the model | Must be built from scratch |
| **Reality** | You pay for the harness, not the model | Model is commoditized; harness is the differentiator |

**Implication:** For builders and businesses  --  the opportunity is **not** to compete on model quality (that's commoditizing fast). The opportunity is to **build the best harnesses and skills** for specific verticals and use cases.

---

### Skill Engineering vs Harness Engineering

Imhof draws a distinction (or rather, a hierarchy) between two complementary concepts:

**Harness Engineering** = the general infrastructure layer
- How tools connect to the agent
- Phase gates, validation loops, error recovery
- Connects the model to the outside world

**Skill Engineering** = domain-specific knowledge and integrations
- Skills are what sit **on top of** a harness
- Examples: "SAP integration skill", "due diligence skill", "legal contract review skill"
- A skill references the harness; the harness doesn't need to know about the skill

**The relationship:** A good harness makes skill engineering 10x faster. A good skill runs on top of a well-built harness.

---

### The Skills Marketplace: What It Is and What It Isn't

Imhof addresses the question: *Will there be a skill marketplace where people buy and sell agentic skills?*

**The nuanced answer:**

**Why marketplaces are hard:**
- Skills are very specific to what you're doing
- "Unless you build a very specific tool, very specific connector for a specific CRM, SAP, or software  --  it ends up being a set of instructions that are very easily replicated"
- "If you can get 95% of a skill for free, you're going to choose the free version"
- Good frontier models are good enough to understand imperfect instructions

**What WILL be paid for:**
1. **Company-internal skills**  --  internal operating procedures, CRM integrations, proprietary workflows. "You wouldn't want to sell your internal rules to the outside world. It's worth developing them internally."
2. **Consulting companies engineering their tacit knowledge**  --  The big opportunity: M&A advisors, legal firms, financial modelers, consulting firms (McKinsey, PWC, Capgemini) have **tacit knowledge** in consultants' heads. They can now "engineer these skills into their clients' agentic systems."
   - Instead of sending a consultant for a week of due diligence → the skill runs inside the client's Claude/Max system
   - This converts **tacit knowledge into replicable, scalable agentic software**
   - "This might be opening a new gateway for them to monetize what they know"

---

### The Knowledge Economy in an Agentic World

Imhof draws a striking parallel:

> In the physical world, you go to a McKinsey consultant for tacit knowledge. In the agentic world, you buy McKinsey's skill to run inside your AI agent.

**The thesis:** Knowledge-intensive companies (consulting, legal, financial advisory, M&A due diligence) have two choices:
1. Engineer their skills and sell them as agentic software  --  new recurring revenue
2. Ignore the shift  --  watch their consulting revenue evaporate as clients use rival skills

The stock market signals this: "We saw all these SaaS titles crash, but also knowledge provisioning companies  --  consulting and intelligence services. The market is pricing in the disruption."

---

### OpenClaw as a Skills Platform

Imhof references OpenClaw as a real-world example of the harness platform model:
- OpenClaw has a platform where users upload prompts and skills
- Skills shared publicly, free to use
- Demonstrates the "free skills ecosystem" for general-purpose harnesses
- Contrasts with specialized enterprise skills that will remain paid/proprietary

---

### SaaS vs Agentic AI: The Paradigm Shift

At the very end, Imhof briefly addresses SaaS in an agentic world:

- Traditional SaaS is software as a service  --  the human uses the software
- Agentic SaaS = AI agents operating inside SaaS systems on behalf of users
- The transition creates both opportunity and disruption:
  - **Opportunity:** Businesses that expose agentic APIs to their SaaS become platforms
  - **Disruption:** Businesses whose only value is intermediating human access to data (not the data itself) will be disintermediated

---

### KYSM Implications from Imhof's Episode

Key takeaways for the KYSM / SAP Masters project:

| Imhof's Insight | KYSM Application |
|---|---|
| The harness is the product; model is commoditized | Our moat is the 5-pillar RAG harness, not the LLM |
| Anthropic hides harness behind $200/month paywall | KYSM's harness (schema RAG + SQL patterns + graph + swarm) is the premium layer |
| Tool calling improvement drove Claude 4.5→4.6 capability gains | Our Phase 10 swarm routing + contract validation = harness improvement without model upgrade |
| Tacit knowledge → skills → agentic software | SAP domain knowledge (DDIC patterns, meta-paths, SQL templates) = our skill library |
| Consulting firms selling skills into clients' agents | Potential enterprise partnership model for KYSM |
| Skills marketplace exists but dominated by free / internal | OpenClaw skills platform validates the free-skills model |
| Phase-gated execution prevents planning collapse | KYSM's 8-phase orchestrator is a phase-gated harness |
| Context overflow degrades agent performance | Graph embedding → top-K table context = context budgeting |
| Narrow but deeply integrated tool sets > many shallow tools | 52 tools across 8 domains = scoped but deep integration |

---

### Key Quotes from Episode 44

> *"The large language model by itself is commoditized infrastructure. The harness is the actual product."*

> *"99% of the harness that you get in the cloud app is not available out of the box on Bedrock. That's why you pay $200/month."*

> *"The increase between Claude 4.5 and 4.6 wasn't in raw intelligence  --  what increased significantly was harness capability: tool calling, tool sets, tool arrays, and connectors."*

> *"In the physical world, you go to McKinsey for tacit knowledge. In the agentic world, you buy McKinsey's skill to run inside your AI agent."*

> *"Unless you build a very specific connector for a specific CRM or SAP system, it's going to end up being a set of instructions that are very easily replicated. If you can get 95% of a skill for free, you're going to choose the free version."*

> *"The ones that can be paid are the ones built by companies, especially internal tooling and internal ways of operating."*

---

### Timestamps (approximate, from transcript)

- `0:00`  --  Episode 44 intro; Cyril not sleeping; pushing heavy on latest developments
- `1:30`  --  Compact episode planned; secrets for great AI agents in production
- `2:00`  --  Skill engineering recap; harness engineering introduction
- `4:00`  --  Definition of harness: group of tools + instructions on how to use them
- `5:30`  --  OpenClaw as the greatest example of harness capability
- `7:00`  --  Frontier model paywall gap: $200/month for the harness, not the model
- `9:00`  --  Claude 4.5 → 4.6: intelligence didn't increase much; harness did
- `11:00`  --  Skills marketplace: free vs paid; internal vs external
- `14:00`  --  Consulting companies engineering tacit knowledge into skills
- `16:00`  --  Knowledge economy disruption; McKinsey in the agentic world
- `18:00`  --  SaaS vs agentic AI; the paradigm shift
- `19:00+`  --  Wrap up; episode 45 teaser; goodbye

---

## References

- **Video 1 (AI Automators / Karpathy):** https://youtu.be/I2K81s0OQto
- **GitHub Repo (PRDs):** https://github.com/theaiautomators/claude-code-agentic-rag-series/tree/main/ep6-agent-harness
- **Skills Bench:** https://www.skillsbench.ai/
- **Stripe Minions:** https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2
- **Episode 5 (Tool Calling & Sandboxes):** https://www.youtube.com/watch?v=R7OCrqyGMeY
- **Episode 4 (Agent Skills):** https://www.youtube.com/watch?v=4Tp6nPZa5is
- **Video 2 (Solo Swift Crafter):** https://youtu.be/DN2mhf0b02s
- **Video 3 (This is the Year E44):** https://youtu.be/ZqM5kbB0D4o
﻿

---

## Video 4: What is Harness Engineering for Long-Running AI Agents (Explained in 10mins)
**Channel:** This is the Year (Cyril Imhof) | **Published:** ~April 2026 | **URL:** https://youtu.be/z10zi0F_1fE

---

### Overview

A focused 10-minute explainer where Cyril Imhof breaks down Anthropic's newly released article on harness design engineering. This is the most practically grounded of the three videos  --  it translates Anthropic's internal engineering work into a builder-friendly explanation of *why* harnesses exist, *what* components they need, and *how* to think about them for long-running AI agents in production business systems.

The central framing: **"An AI agent without a harness is not that useful. It's just a large language model that is super intelligent, but it's not fully embedded in the business context."**

---

### The Core Problem: Why Harnesses Exist

Imhof identifies two fundamental problems that harnesses solve:

#### Problem 1: Context Window Anxiety

The context window of any LLM is finite (e.g., Claude Opus 4.6 has 1 million tokens ≈ 1,500 A4 pages). But as the context fills up:

- Performance degrades
- The model gets "anxious" and tries to wrap up tasks prematurely
- It starts dropping important context

**The solution:** *Context engineering*  --  curating what goes into the context and what is left out. The harness acts as a filter and manager of context, ensuring the model never gets overwhelmed.

#### Problem 2: Self-Evaluation Bias

A single LLM that generates *and* evaluates its own output has a structural problem: it overestimates the quality of its own work. What it produces, it also rates as best-in-class  --  even when mediocre.

**The solution:** *Role separation*  --  split the system into distinct agents with distinct responsibilities:
- A **Generator** agent that produces output
- An **Evaluator** agent that critiques the Generator's output

This is the foundation of the Generator/Evaluator pattern that Anthropic formalized.

---

### The Components of a Harness

Imhof lays out the core components of a production harness  --  every business system an AI agent needs to be useful:

| Component | Purpose |
|---|---|
| **Planning capabilities** | Agent can break down complex tasks into sub-steps |
| **File system access** | Can write outputs, persist state, read prior work |
| **Short-term memory** | Session-level context (current conversation state) |
| **Long-term memory** | Remembers past projects, reusable components |
| **Skills / Tacit knowledge** | Domain-specific human expertise injected as structured resources (e.g., due diligence templates, legal research skills) |
| **Human-in-the-loop** | Context management for cases where human judgment is required |
| **Context compaction** | System to keep context lean and performant as it grows |

**The skills example:** A law firm onboarding a new associate gives them templates, case files, and procedural knowledge. You can do the same for an AI agent  --  give it a *due diligence skill*, a *legal research skill*, a *contract review skill*. These are managed within the harness, not as part of the model.

---

### Anthropic's November 2025 Approach: Generator/Evaluator

Anthropic's earlier harness design (from a November 2025 blog post) was based on Claude 4.5 Q4 and used an **iterative Generator/Evaluator loop**:

```
User Prompt
    ↓
Generator Agent (produces output)
    ↓
Evaluator Agent (grades output against criteria)
    ↓
Feedback Loop → Generator Agent (revises)
    ↓
[Repeats until evaluator passes]
```

This was more sophisticated but required **multiple iterations** between Generator and Evaluator  --  each iteration adding cost and latency. The grading criteria lived in the Evaluator.

---

### The 2026 Update: V2 Harness (Anthropic's Current Design)

With Claude Opus 4.6 (the new optimized model), Anthropic evolved the harness design:

**Key shift:** Fewer iterative loops → more **one-shot** generation

The new architecture (V2):

```
User Prompt (1-2 sentences)
    ↓
[Planner Agent]  --  augments the prompt into a full specification
    (adds requirements engineering, business analysis, best practices)
    ↓
[Generator Agent]  --  builds the full deliverable in one continuous session
    (uses Opus 4.6 + context compaction from Anthropic SDK)
    ↓
[QA / Evaluator Agent]  --  tests the full build
    ↓
Feedback → updates Planner → updates Generator → re-runs
```

**Three distinct agents, each with a specific role:**
1. **Planner**  --  expands sparse user intent into a complete, detailed specification
2. **Generator**  --  executes the build in one shot based on the spec
3. **Evaluator / QA**  --  validates the output, triggers feedback loops

**Real cost data from the episode:**
- Harness V1 (iterative): ~4 hours runtime, ~$125 per full build (on AWS with Anthropic discounts)
- The runtime and cost are significant  --  but acceptable for enterprise-grade full-stack code generation

**Why this matters:** If you're building anything on top of LLMs  --  not just code, but PowerPoints, Word documents, Excel analyses, financial models  --  **coding is the fundamental benchmark**. Master coding agentically, and you can scale down to any other output type. This is exactly why Anthropic focused on coding workflows.

---

### The Key Strategic Insight: Stripping Harnesses as Models Improve

Imhof highlights the most important trend for AI builders:

> *"Every time there is a new model, you probably have to rethink: do we need to keep the harness specifically engineered for Opus 4.5, or can we strip it down and let the model figure it out more?"*

The pattern over the last several months:
- **Older models** needed heavy harness engineering: iterative loops, context compaction, explicit evaluator grading, detailed tool instructions
- **Newer models** (4.6): much of this can be removed  --  the model is more capable at general-purpose reasoning without detailed scaffolding

**The implication for builders:**
- A harness optimized for today's model may be over-engineered for tomorrow's model
- The **harness and the model must be co-optimized**  --  as models improve, strip out the scaffolding that the model no longer needs
- This is not a one-time architecture decision  --  it's an **ongoing engineering discipline**

**But the fundamentals remain:** For any serious production system, the Generator/Evaluator separation (or its Planner/Generator/QA equivalent) is still essential. You don't want a single model doing everything  --  the self-evaluation bias problem doesn't go away with better models.

---

### Practical Framework: What Every Production Harness Needs

Imhof's minimum viable harness for any business AI agent:

```
┌─────────────────────────────────────────────┐
│              USER PROMPT                     │
└─────────────────┬───────────────────────────┘
                  ↓
        ┌─────────────────┐
        │    PLANNER      │ (optional for simple specs)
        │ Expands intent  │
        │ into full spec  │
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
        │   GENERATOR     │ ←── Each agent has its own
        │ Produces output │     scoped tool harness
        │ in one shot     │
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
        │   EVALUATOR /   │
        │   QA AGENT      │ ←── Grades against criteria
        │ Validates build │     Sends feedback to Planner + Generator
        └─────────────────┘
```

**When you can drop the Planner:** If the specification is already detailed (e.g., a formal RFP, a detailed user story), the Planner is unnecessary overhead.

**When the Evaluator is non-negotiable:** Any system where output quality matters. The Evaluator is the harness's quality gate  --  not the Generator.

---

### KYSM / SAP Masters Implications

| Imhof's Framework | KYSM Implementation |
|---|---|
| Planner → Generator → Evaluator | Orchestrator (Planner) → Domain Agents (Generator) → Synthesis Agent (Evaluator/QA) |
| Context compaction | Graph embedding → top-K tables per phase = context budgeting |
| Long-term memory | Qdrant vector store for proven SQL patterns |
| Skills / Tacit knowledge | Meta-path library + SQL pattern library = domain skills |
| Short-term memory | Redis PhaseState per run = session context |
| Role separation (avoids self-evaluation bias) | Domain agents (generate) → synthesis agent (evaluate/merge) = built-in separation |
| Stripping harness as models improve | Node2Vec embeddings reduce need for explicit graph traversal scaffolding |
| Context anxiety prevention | Phase-gated execution = bounded context per phase |
| Human-in-the-loop | Sentinel system = automated HITL for sensitive/cross-module queries |

---

### Key Quotes

> *"An AI agent without a harness is not that useful. It's just a large language model that is super intelligent, but it's not fully embedded in the business context. It needs to generate and effectuate the value."*

> *"The more the context window is filled up, the worse the LLM performs. It gets anxious and tries to wrap up the task prematurely."*

> *"A single model that generates and evaluates its own work overestimates its own output. You need role separation."*

> *"Every time there is a new model, you probably have to rethink: do we still need this specific harness, or can we strip it down and let the model figure it out more?"*

> *"Master coding agentically, and you can scale down to any other output type. That's exactly why Anthropic focused on coding."*

---

### Timestamps (approximate)

- `0:00`  --  Hook: Anthropic's new harness design article
- `1:00`  --  What is harness design: the 6 components
- `2:30`  --  Problem 1: Context window anxiety
- `4:00`  --  Problem 2: Self-evaluation bias → Generator/Evaluator separation
- `5:00`  --  Anthropic's November 2025 approach: iterative Generator/Evaluator loop
- `6:00`  --  V2 Harness: Planner → Generator → Evaluator (one-shot capable)
- `7:30`  --  Real cost data: 4 hours, $125 per full build
- `8:30`  --  The trend: stripping harnesses as models improve
- `9:30`  --  Practical minimum: Generator + Evaluator is non-negotiable
