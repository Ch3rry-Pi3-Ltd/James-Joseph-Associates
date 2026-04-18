"""
Shared LangGraph state definitions for the intelligence backend.

This module defines the small typed state objects that LangGraph workflows pass
from one node to the next.

It gives the rest of the repository a stable way to talk about:

- what a graph receives as input
- what a graph adds while it runs
- what a graph returns as output
- how future workflow state should be typed and documented

Keeping graph state in its own module makes the project easier to extend because:

- `backend.graphs.foundation` can focus on the first minimal graph
- future matching graphs can reuse the same state patterns
- tests can verify graph state shape separately from real recruitment data
- LangGraph node functions can stay small and predictable

In plain language:

- this module answers the question:

    "What information moves through a LangGraph workflow?"

- it does not call an LLM
- it does not retrieve documents
- it does not query Supabase
- it does not know about candidates, jobs, companies, or CVs yet
- it only defines the typed container that graph nodes will read and update

Notes
-----
- LangGraph workflows usually pass a shared state object between nodes.
- Each node reads some state fields and returns updates for one or more fields.
- The graph combines those updates into the state as execution moves forward.
- Starting with a tiny state keeps the first graph testable without needing real
  source-system data.
- Later, this module can grow to include states for:

    - source-record ingestion
    - document parsing
    - candidate/job matching
    - evidence assembly
    - action proposal
    - human approval

- For now, the foundation graph only needs:

    - an input message
    - an output message

Example
-------
A minimal graph state might start as:

    {
        "input_message": "Hello",
        "output_message": ""
    }

A graph node can then return:

    {
        "output_message": "Foundation graph received: Hello"
    }

After the node runs, the graph state contains both the original input and the
new output.

More explicitly, the state starts as:

    {
        "input_message": "Hello",
        "output_message": ""
    }

The node returns only the field it wants to update:

    {
        "output_message": "Foundation graph received: Hello"
    }

LangGraph merges that update into the existing state, so the final state becomes:

    {
        "input_message": "Hello",
        "output_message": "Foundation graph received: Hello"
    }

In plain language:

    input state
        -> graph node reads it
        -> graph node returns updates
        -> updated state comes out
"""

from typing import TypedDict

class FoundationGraphState(TypedDict):
    """
    State passed through the first minimal LangGraph workflow.

    This state is intentionally small. It exists to prove that LangGraph is wired
    into the backend correctly before we build real recruitment workflows.

    Attributes
    ----------
    input_message : str
        Message supplied to the graph.

        In the first graph, this is just a plain string used to prove data can
        enter a graph and be read by a node.

    output_message : str
        Message produced by the graph.

        In the first graph, this will be written by a simple node function.
        Later, real graphs may produce structured outputs such as match results,
        evidence summaries, or proposed workflow actions.

    Notes
    -----
    - This is not a candidate-matching state.
    - This is not a retrieval state.
    - This is not an ingestion state.
    - It is a foundation state used only to prove the graph plumbing works.
    - The name `FoundationGraphState` is deliberately generic so it does not
      pretend to model the recruitment domain yet.
    
    Why TypedDict?
    --------------
    LangGraph commonly works with dictionary-like state.

    `TypedDict` lets us keep that dictionary style while still documenting the
    expected keys and value types.

    That gives us:

    - simple runtime behaviour
    - clearer editor hints
    - easier tests
    - less guesswork when writing graph nodes

    Example
    -------
    A valid input state for the foundation graph is:

        state: FoundationGraphState = {
            "input_message": "Hello from a test",
            "output_message": "",
        }

    A graph node can read:

        state["input_message"]

    and return an update:

        {
            "output_message": "Foundation graph received: Hello from a test"
        }

    The graph then merges the update into the existing state.

    The final output state becomes:

        {
            "input_message": "Hello from a test",
            "output_message": "Foundation graph received: Hello from a test",
        }

    The important detail is that the state definition here does not decide how
    the output is produced.

    The node logic decides that by returning an update dictionary.

    For example, a node could return:

        {
            "output_message": f"Foundation graph received: {state['input_message']}"
        }

    In that case:

    - the state type defines which keys are allowed
    - the node decides which values to write
    - LangGraph merges the node's returned values back into the state

    In plain language:

    - `input_message` is what goes in
    - `output_message` is what the graph writes back
    """

    # The first graph input
    #   - This is deliberately plain text.
    #   - We are testing graph wiring, not recruitment logic yet.
    input_message: str

    # The first graph output
    #   - The foundation graph will fill this in.
    #   - Future graphs will use richer fields, but starting small keeps the
    #     first LangGraph integration easy to understand and test.
    output_message: str

__all__ = ["FoundationGraphState"]
