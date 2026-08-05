# ADR-0002: Bounded workflows over multi-agent orchestration

- Status: Accepted
- Date: 5 August 2026
- Owners: Ch3rry Pi3 Ltd engineering
- Scope: Recruitment retrieval, matching, extraction, Q&A, ingestion, and
  proposed-action workflows

## Decision

Use explicit, bounded workflows as the default orchestration model. Do not add
autonomous agent loops or a multi-agent design to the current product.

A bounded workflow may be implemented as ordinary typed service functions or,
when durable state and branching justify it, as a LangGraph state machine.
LangGraph is an implementation tool, not a reason to make a workflow agentic.
The smallest design that makes states, permissions, retries, evidence, and stop
conditions explicit should be selected.

The production candidate-shortlist and recruiter-Q&A services remain direct
bounded pipelines. The existing LangGraph foundation graph remains a plumbing
proof and should not replace working services until a real adoption gate is met.

## Context and evidence

The current business workflows are already naturally bounded:

```text
validate input
  -> retrieve bounded evidence
  -> run an optional model step
  -> validate grounding/citations
  -> assemble a typed response
  -> stop
```

Stage-level observability now correlates those stages with request, run, and
parent-run identifiers plus workflow/prompt/model versions, latency, token
usage, cached tokens, and estimated cost. The automated quality layer validates
grounding, schema stability, sensitive-data handling, and defined RAG failure
conditions. The resilience suite proves bounded provider refresh, model
fallback, restart, and degraded-service behaviour.

There is no current requirement for agents to negotiate, share independent
memory, own different permissions, or choose among open-ended goals. Giving
multiple model personas the same evidence and tools would duplicate calls
without creating a genuine system boundary.

## Alternatives considered

### Unconstrained autonomous agent

Rejected. Open-ended planning and tool use would weaken deterministic stop
conditions, cost budgets, groundedness guarantees, and action permissions.

### Multi-agent roles for retrieval, ranking, checking, and writing

Rejected for now. Those are stages with typed inputs and outputs, not separate
actors. A single controlled workflow can execute and evaluate them more simply.

### Convert every multi-step service to LangGraph

Rejected. The current direct services are readable, tested, observable, and do
not need persisted checkpoints. Framework conversion without a state-management
need would add ceremony rather than capability.

### Never use LangGraph or multiple agents

Rejected as an absolute rule. Durable approvals, resumable long-running work,
or genuinely separate authority boundaries may later justify them. This ADR
defines gates for that decision.

## Bounded workflow contract

Every model-backed or tool-using workflow must define:

- a typed input and output contract;
- explicit states or stages and allowed transitions;
- the evidence each stage may read;
- a fixed tool allow-list with least-privilege access;
- per-stage timeout, retry, model-call, token, and cost budgets;
- deterministic success, failure, review, and cancellation terminals;
- idempotency rules for writes and restartable work;
- human approval before externally visible or destructive actions;
- content-free trajectory metadata using the existing observability layer; and
- regression cases for every branch, retry, and terminal outcome.

Current retry ceilings remain narrow:

- JobAdder, Dropbox, and Outlook may refresh credentials once after `401` and
  retry once;
- model compatibility, output-length, and quality-gate fallbacks may run only
  in their explicitly configured paths;
- no generic cross-provider LLM failover is enabled; and
- no workflow may create an unbounded plan/retry/reflection loop.

Read-only answers may complete automatically after validation. Draft-producing
work must be labelled as draft. External messages, record mutation, deletion,
commercial decisions, or other high-impact actions require an explicit API
contract, durable idempotency, audit metadata, and the configured human
approval boundary.

## LangGraph adoption gate

Use LangGraph for a production workflow only when at least one of these needs is
demonstrated:

- execution must pause and resume across requests or process lifetimes;
- a human approval checkpoint must persist before work continues;
- the workflow has at least three meaningful conditional branches whose state
  is otherwise duplicated across callers;
- long-running work needs durable checkpoints, cancellation, or recovery; or
- multiple tools share state across steps and ordinary composition has produced
  a measured reliability or maintenance problem.

Before adoption, the implementation must also have:

- a versioned typed state schema and migration/compatibility policy;
- named terminal states and a finite maximum transition count;
- explicit retry, timeout, model-call, token, and cost ceilings;
- a privacy-reviewed checkpoint store and retention period if state persists;
- idempotent side-effect boundaries;
- transition, stop-condition, recovery, and trajectory tests; and
- a comparison showing the graph solves the stated problem more clearly or
  reliably than the direct service baseline.

## Multi-agent adoption gate

A multi-agent experiment may be proposed only if all of the following are true:

- at least two roles have genuinely non-overlapping tools, data ownership, or
  approval authority;
- the separation cannot be represented as ordinary stages in one typed state
  machine;
- a single bounded workflow baseline exists on the same versioned evaluation
  set;
- each agent has an independent tool allow-list, model-call ceiling, token/cost
  budget, and deterministic stop condition;
- inter-agent messages use typed schemas and do not transfer unrestricted
  candidate or contact content;
- total transitions and hand-offs have a finite hard limit;
- partial failure, cancellation, replay, and audit behaviour are defined; and
- the experiment demonstrates either at least a five-percentage-point quality
  improvement or at least a 20% p95 latency/cost improvement without reducing
  groundedness, stability, or sensitive-data safety.

Different prompts, job titles, or model personas using the same permissions do
not satisfy this gate.

## Consequences

- Current shortlist, Q&A, extraction, and integration flows remain simple and
  directly testable.
- Workflow failures have finite blast radius, cost, and duration.
- Observability records stages and versions without storing sensitive content.
- LangGraph remains available for future durable state machines, but trajectory
  evaluation is added only with a real graph.
- Multi-agent complexity is deferred until a measurable authority or performance
  boundary exists.
- New workflow proposals must state their stop conditions and budgets before
  implementation.

## Related evidence

- [LangGraph foundation](../langgraph_foundation.md)
- [Automated AI quality checks](../evaluation/automated_ai_quality_checks.md)
- [Stage-level observability](../stage_level_observability.md)
- [Resilience and load testing](../resilience_and_load_testing.md)
- [LLM operational budgets](../llm_operational_budgets.md)
- [North-star architecture](../north_star_architecture.md)

