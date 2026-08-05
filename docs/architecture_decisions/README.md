# Architecture decision records

These records capture technical choices that affect implementation complexity,
evaluation, security, and operating cost. They are decisions for the current
evidence and can be superseded when their explicit reconsideration gates are
met.

| ADR | Status | Decision |
| --- | --- | --- |
| [ADR-0001](0001-rag-over-fine-tuning.md) | Accepted | Use grounded RAG over task-specific fine-tuning for current recruitment intelligence workflows |
| [ADR-0002](0002-bounded-workflows-over-multi-agent.md) | Accepted | Use bounded workflows over autonomous or multi-agent orchestration |
| [ADR-0003](0003-managed-inference-until-self-hosting-gate.md) | Accepted | Keep managed inference until the executable self-hosting benchmark gate is met |

Recruiter-labelled relevance and final usefulness remain external validation
questions. These ADRs decide how engineering should proceed until that evidence
exists; they do not substitute for recruiter UAT.
