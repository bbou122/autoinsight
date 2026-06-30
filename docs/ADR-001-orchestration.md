# ADR-001: Multi-Agent Orchestration Framework

- **Status:** Accepted
- **Date:** 2026-06-30
- **Decision owner:** Braden Bourg

## Context

AutoInsight is a conversational data-analyst agent. A user asks a question in
plain English ("which product categories have the worst review-to-sales ratio?")
and the system must: interpret intent, write and **execute** analysis code against
a live DataFrame, generate a chart, validate the numbers, and reply in the chat.

This requires a *stateful, multi-step* workflow with branching (different question
types take different paths) and a validation gate before any answer reaches the
user. We need to choose an orchestration framework.

## Options considered

| Option | Strengths | Weaknesses |
|---|---|---|
| **LangGraph** | Explicit stateful graph, conditional edges, built-in persistence/checkpointing, easy to add a validation gate as a node, strong observability | Slightly more boilerplate than role-play frameworks |
| **CrewAI** | Fast to stand up role-playing agents, readable | Less control over deterministic control-flow and validation gating; harder to enforce a "verify before answer" step |
| **Raw function calls / no framework** | Zero dependencies, full control | We reinvent state, retries, branching, and observability ourselves |

## Decision

**Use LangGraph.** The deciding factor is the **validation gate**: AutoInsight's
differentiator is that every answer is independently recomputed and checked before
display. LangGraph models this cleanly as a node with a conditional edge (pass →
respond, fail → retry/flag), and its checkpointing gives us conversation memory
for free. CrewAI optimizes for autonomous role-play, which is the wrong shape for
a workflow that must be auditable and deterministic where it counts.

## Consequences

- **Positive:** Clear node boundaries make each step independently testable
  (matches our self-check-every-phase principle); the graph doubles as the
  architecture diagram; checkpointing handles multi-turn memory.
- **Negative:** More upfront wiring than CrewAI.
- **Mitigation / graceful degradation:** The agent ships with a **deterministic
  intent router** so the app is fully functional *without* an LLM API key (handles
  top-N, trend, anomaly, correlation, segment-comparison questions). When a Groq/
  OpenAI key is present, the LLM layer upgrades intent parsing and narrative
  generation. This means the demo never hard-fails on a missing key.

## How this decision was checked

Traced the example prompt *"Show sales trends by region and flag anomalies"*
end-to-end through the proposed graph (see `architecture.mermaid`). Every node has
a defined input and output and the validation gate sits before the response node.
No undefined hand-offs found.
