# LangGraph Foundation

This document records the first LangGraph foundation work in the backend.

It is a status and explanation document, not a product workflow specification.

In plain language:

- LangGraph is now installed and importable.
- The backend has a tiny graph state definition.
- The backend has a tiny compiled graph.
- The graph can be invoked from tests.
- This proves the workflow plumbing works.
- It does not yet perform recruitment intelligence.

## What Exists Now

Current files:

```text
backend/graphs/state.py
backend/graphs/foundation.py
tests/unit/test_graph_foundation.py
```

These files prove the smallest useful LangGraph pattern:

```text
typed state
    -> node function
    -> graph builder
    -> compiled graph
    -> invoked graph
    -> final state
```

## Current Graph Shape

The current graph is deliberately tiny:

```text
START
    -> build_output_message
    -> END
```

It has one node:

```text
build_output_message
```

That node:

- reads `input_message`
- creates a new `output_message`
- returns only the state field it wants to update

## Current State Shape

The current state is:

```python
class FoundationGraphState(TypedDict):
    input_message: str
    output_message: str
```

In plain language:

- `input_message` is the value supplied to the graph run
- `output_message` is the value written by the graph node

An example starting state is:

```python
{
    "input_message": "Hello from a test",
    "output_message": "",
}
```

The final state is:

```python
{
    "input_message": "Hello from a test",
    "output_message": "Foundation graph received: Hello from a test",
}
```

## What This Proves

This foundation proves:

- LangGraph can be imported by the backend.
- A typed graph state can be defined.
- A node can read from state.
- A node can return a partial state update.
- LangGraph can merge the update into the current state.
- A graph can be compiled.
- A graph can be invoked in tests.
- Tests can protect this behaviour from accidental breakage.

## What This Does Not Do Yet

This graph does not:

- call an LLM
- call LangChain prompts
- retrieve documents
- query Supabase
- parse CVs
- ingest source records
- match candidates to jobs
- rank evidence
- propose actions
- use persistent memory
- use graph checkpointing
- use real client data

That is intentional.

The purpose is to prove the framework before building business workflows.

## Conceptual Model

The basic LangGraph concepts are:

```text
State
    what the workflow knows while it runs

Node
    one function that reads state and returns updates

Edge
    the route from one node to another

StateGraph
    the graph blueprint

compile()
    turns the blueprint into a runnable workflow

invoke(...)
    runs the workflow with one starting state

Final state
    the state after all graph nodes have run
```

For the current graph:

```text
FoundationGraphState
    -> build_output_message(...)
    -> START -> build_output_message -> END
    -> create_foundation_graph()
    -> foundation_graph
    -> foundation_graph.invoke(...)
    -> updated state
```

## State Versus History Versus Memory

The current graph uses simple state only.

```text
State
    working data for one graph run

History
    ordered record of what happened step by step

Memory
    information saved across graph runs
```

The current foundation graph has:

```text
state: yes
history: no
memory: no
```

Future recruitment workflows may need all three:

- state for current candidate/job context
- history for retrieved evidence and graph steps
- memory for stored feedback, prior matches, and long-term source records

## Why We Are Not Building Real GraphRAG Yet

Real GraphRAG workflows depend on source data.

At the moment:

- Make.com can securely call the backend.
- Source-system access is not available yet.
- Real sample payloads have not been collected yet.
- The first source-record schema is not known yet.

Because of that, it would be premature to build:

- candidate/job matching graphs
- retrieval graphs
- evidence assembly graphs
- action proposal graphs

Those would encode assumptions before we know the real data shape.

## How This Will Evolve

Once source-system discovery produces safe sample payloads, the graph layer can
grow into real workflows.

Possible future graph:

```text
START
    -> load_candidate_context
    -> load_job_context
    -> retrieve_evidence
    -> compare_candidate_to_job
    -> build_recommendation
    -> END
```

Possible future state:

```python
{
    "candidate_id": "...",
    "job_id": "...",
    "candidate_context": [],
    "job_context": [],
    "retrieved_evidence": [],
    "match_score": None,
    "recommendation": "",
}
```

Each node should add useful fields rather than overwrite valuable context.

Example:

```text
load_candidate_context
    -> writes candidate_context

load_job_context
    -> writes job_context

retrieve_evidence
    -> writes retrieved_evidence

compare_candidate_to_job
    -> writes match_score

build_recommendation
    -> writes recommendation
```

## Current Development Status

Done:

- LangGraph dependency added.
- Foundation graph state added.
- Foundation graph added.
- Foundation graph tests added.
- Graph tests pass.

Not done yet:

- real retrieval graph
- real matching graph
- persistent graph memory/checkpointing
- LangChain model abstraction
- LLM prompts
- source-record-driven graph inputs
- Supabase-backed graph context

Recommended next project step:

- add a small `backend/llm/` foundation for model/provider configuration
- avoid real LLM calls until provider choices and secrets are clearer
- wait for source-system discovery before building recruitment-specific graphs

