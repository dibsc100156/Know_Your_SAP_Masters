# Harness Engineering: How to Build Software When Humans Steer, Agents Execute

**Speaker:** Ryan Lopopolo (OpenAI)
**Event:** OpenAI Keynote + Q&A with Vibhu Sapra
**Duration:** 46:20
**Views:** 292
**Published:** April 16, 2026
**Source:** https://youtu.be/am_oeAoUhew
**Reference:** https://openai.com/index/harness-engineering/

---

## The Experiment

OpenAI ran a **5-month experiment** building a real software product with **zero manually-written code**. Every line of code — application logic, tests, CI configuration, documentation, observability, and internal tooling — was written by Codex. The result: approximately **1 million lines of code**, ~1,500 pull requests merged, at an estimated **1/10th the time** of traditional development.

**Core philosophy: Humans steer. Agents execute.**

---

## Key Principles & Learnings

### 1. Context Management — "Map, Not Manual"

Giant AGENTS.md files **fail** in predictable ways:
- Context is a scarce resource — a giant instruction file crowds out the task, code, and relevant docs
- Too much guidance becomes non-guidance — when everything is "important," nothing is
- It rots instantly — a monolithic manual becomes a graveyard of stale rules
- Hard to verify — a single blob doesn't lend itself to mechanical checks (coverage, freshness, ownership, cross-links)

**Instead: AGENTS.md = Table of Contents** (~100 lines). The real knowledge lives in a structured `docs/` directory treated as the system of record.

- Knowledge lives **in-repo** — Google Docs, Slack threads, and people's heads are invisible to agents
- Progressive disclosure: agents start small, taught where to look next rather than overwhelmed upfront
- Rules enforced mechanically: linters + CI validate docs are fresh, cross-linked, and structured
- A recurring "doc-gardening" agent scans for stale or obsolete documentation and opens fix-up PRs

> **Design documentation** is catalogued and indexed, including verification status and core beliefs that define agent-first operating principles. **Architecture documentation** provides a top-level map of domains and package layering. **Quality documents** track gaps over time.

---

### 2. Architecture for Agents (Not Just Humans)

Built a **rigid architectural model** — each business domain has fixed layers with strictly validated dependency directions:

```
Types → Config → Repo → Service → Runtime → UI
```

- Cross-cutting concerns (auth, connectors, telemetry, feature flags) enter through a single explicit interface: **Providers**
- Custom Codex-generated linters enforce these rules mechanically
- This is the kind of architecture you'd normally postpone until you have hundreds of engineers — with coding agents, it's an **early prerequisite**

**Enforced invariants:**
- Parse data shapes at the boundary (parse don't validate), but not prescriptive about how
- Structural tests validate layer dependencies
- "Taste invariants": structured logging, naming conventions, file size limits, platform-specific reliability requirements

---

### 3. Observability = Legibility

Made the **app itself legible to Codex**:

- **Ephemeral git worktrees per change** — Codex can launch and drive one instance per change
- **Chrome DevTools Protocol** wired into the agent runtime — skills for DOM snapshots, screenshots, and navigation
- **Full observability stack** exposed via LogQL and PromQL — ephemeral per worktree, torn down after task completion
- Codex can work on a fully isolated version of the app including its logs and metrics

**Examples of tractable prompts now possible:**
- "Ensure service startup completes in under 800ms"
- "No span in these four critical user journeys exceeds two seconds"

Single Codex runs work **up to 6 hours** (often while humans are sleeping).

---

### 4. The Ralph Wiggum Loop (Agent Self-Review)

The PR workflow:
1. Engineer describes a task, runs the agent
2. Codex opens a pull request
3. Codex reviews its own changes locally
4. Requests additional specific agent reviews (local + cloud)
5. Responds to any human or agent given feedback
6. Iterates in a loop until all agent reviewers are satisfied

**Humans may review PRs but aren't required to.** Over time, almost all review effort has been pushed to agent-to-agent handling.

> This is effectively a [Ralph Wiggum Loop](https://ghuntley.com/loop/): "I'm helping!"

---

### 5. The Golden Principles (Garbage Collection for AI Slop)

Initially, humans spent **every Friday (20% of the week)** cleaning up "AI slop" — this didn't scale.

**Instead: encode golden principles directly into the repository:**
1. Prefer shared utility packages over hand-rolled helpers (keep invariants centralized)
2. Don't probe data "YOLO-style" — validate boundaries or rely on typed SDKs
3. Mechanical rules keep codebase legible and consistent for future agent runs

**The garbage collection system:**
- Background Codex tasks scan for deviations on a recurring cadence
- Update quality grades
- Open targeted refactoring PRs (most reviewed in under a minute, auto-merged)
- Technical debt is a **high-interest loan** — better to pay down continuously in small increments than let it compound

---

### 6. Full Agent Autonomy Threshold

The repository recently crossed a meaningful threshold where **given a single prompt, Codex can now**:

1. Validate the current state of the codebase
2. Reproduce a reported bug
3. Record a video demonstrating the failure
4. Implement a fix
5. Validate the fix by driving the application
6. Record a second video demonstrating the resolution
7. Open a pull request
8. Respond to agent and human feedback
9. Detect and remediate build failures
10. **Escalate to a human only when judgment is required**
11. Merge the change

> **Note:** This behavior depends heavily on the specific structure and tooling of this repository and should not be assumed to generalize without similar investment.

---

## The Numbers

| Metric | Value |
|--------|-------|
| Initial commit | Late August 2025 |
| Development period | 5 months |
| Total lines of code | ~1 million |
| Pull requests merged | ~1,500 |
| Initial team size | 3 engineers |
| Final team size | 7 engineers |
| PRs per engineer per day | **3.5** |
| Throughput trend | Increasing as team grew |
| Single Codex run duration | Up to **6 hours** |
| Estimated time savings | **1/10th** of manual development |

---

## OpenAI's Philosophical Framework

> "Building software still demands discipline, but the discipline shows up more in the scaffolding rather than the code. The tooling, abstractions, and feedback loops that keep the codebase coherent are increasingly important."

### What They Don't Yet Know
- How architectural coherence evolves over **years** in a fully agent-generated system
- Where human judgment adds the most leverage and how to encode that judgment so it compounds
- How the system will evolve as models continue to become more capable

---

## Relevance to SAP Masters Architecture

This talk provides **direct philosophical validation** for the SAP Masters multi-agent architecture built in previous sessions:

| SAP Masters Phase | OpenAI Harness Equivalent |
|------------------|--------------------------|
| Phase 10: Multi-Agent Domain Swarm | Parallel agent execution, synthesis of results |
| Phase 13: Inter-Agent Message Bus + Negotiation Protocol | Agent-to-agent review loop, structured conflict resolution |
| Phase 6b: Memory Compounding (Qdrant auto-vectorization) | In-repo knowledge base, pushing context into the system |
| Phase 5.5: Validation Harness (Dry-Run) | Enforce invariants at boundaries, parse don't validate |
| Phase 6c: Proactive Threat Sentinel | Custom linters enforcing golden principles |
| Phase 7: Temporal Analysis Engine | Time-bounded validation and versioned knowledge |
| Phase 9: Confidence Scoring | Progressive disclosure, mechanical verification |

The SAP Masters 5-Pillar RAG architecture (Role-Aware, Agentic, Schema, SQL, Graph) maps to a production implementation of OpenAI's harness engineering principles — applied to the SAP domain.

---

## Speaker Links

- Ryan Lopopolo: [@_lopopolo](https://x.com/_lopopolo) | [LinkedIn](https://www.linkedin.com/in/ryanlopopolo/) | [GitHub](https://github.com/lopopolo)
- Q&A co-host: Vibhu Sapra [@vibhuuuus](https://x.com/vibhuuuus) | [latent.space/harness-eng](https://latent.space/p/harness-eng)
- Original post: [openai.com/index/harness-engineering](https://openai.com/index/harness-engineering/)