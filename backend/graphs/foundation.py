"""
Foundation LangGraph workflow for the intelligence backend.

This module defines the first tiny LanGraph workflow in the project.

It gives the rest of the repository a stable way to prove that:

- LangGraph can be imported
- graph state can be typed
- a graph node can read state
- a graph node can return a state update
- LangGraph can merge that update into the existing state
- the graph can be compiled and invoked from tests

Keeping this foundation graph separate from real recruitment workflows makes the
project easier to extend because:

- `backend.graphs.state` can focus on shared state definitions
- this module can focus on graph wiring
- future graph modules can copy this pattern
- tests can verify LangGraph integration before real source data exists

In plain language:

- this module answers the question:

    "Can our backend run a basic LangGraph workflow?"

- it does not call an LLM
- it does not use LangChain prompts
- it does not retrieve documents
- it does not query Supabase
- it does not process real candidate, company, job, or CV data
- it only proves the graph execution pattern works

Notes
-----
- LangGraph nodes usually receive the current graph state.
- A node returns a dictionary containing the fields it wants to update.
- The returned dictionary is a partial state update.
- LangGraph merges that partial update into the existing state.
- This first graph has one node:

    build_output_message

- The graph flow is:

    START
        -> build_output_message
        -> END

Example
-------
The graph can be invoked with:

    result = foundation_graph.invoke(
        {
            "input_message": "Hello from a test,"
            "output_message": "",
        }
    )

The node reads:

    state["input_message"]

and returns:

    {
        "output_message": "Foundation graph received: Hello from a test"
    }

LangGraph then merges that update into the existing state.

The final result is:

    {
        "input_message": "Hello from a test",
        "output_message": "Foundation graph received: Hello from a test"
    }

In plain language:

    input state
        -> node reads `input_message`
        -> node returns a new `output_message`
        -> graph returns the updated state
"""

from typing import Final

from langgraph.graph import END, START, StateGraph

from backend.graphs.state import FoundationGraphState

FOUNDATION_NODE_NAME: Final[str] = "build_output_message"

def build_output_message(state: FoundationGraphState) -> dict[str, str]:
    """
    Build the foundation graph output message.

    Parameters
    ----------
    state : FoundationGraphState
        Current graph state.

        For this first graph, the state contains:

        - `input_message`
        - `output_message`

    Returns
    -------
    dict[str, str]
        Partial state update containing the new `output_message`

    Notes
    -----
    - This is a LangGraph node function.
    - A node function reads the current state.
    - A node function returns only the fields it wants to update.
    - It does not need to return the full state.
    - LangGraph handles merging the returned fields into the existing state.

    Important detail
    ----------------
    This function does not mutate the input state directly.

    It does not do this:

        state["output_message"] = "..."

    Instead, it returns this:

        {
            "output_message": "..."
        }

    LangGraph then applies that update to the state.

    Example
    -------
    If the node receives:

        {
            "input_message": "Hello from a test",
            "output_message": ""
        }

    it returns:

        {
            "output_message": "Foundation graph received: Hello from a test"
        }

    The graph output then becomes:

        {
            "input_message": "Hello from a test",
            "output_message": "Foundation graph received: Hello from a test"
        }

    In plain language:

    - read the input message
    - build a predictable output message
    - return only the field that should change
    """

    # Read the input from the graph state
    #   - This is the value supplied when the graph is invoked.
    #   - Later graphs might add richer fields such as candidate IDs, job IDs,
    #     retrieval evidence, or approval decisions.
    input_message = state["input_message"]

    # Build a predictable response
    #   - This is deliberately simple.
    #   - The purpose is to prove graph execution, not LLM behaviour.
    output_message = f"Foundation graph received: {input_message}"

    # Return a partial state update
    #   - LangGraph merges this into the existing state.
    #   - We only return `output_message` because `input_message` does not need
    #     to change.
    return {
        "output_message": output_message,
    }

def create_foundation_graph():
    """
    Create and compile the foundation LangGraph workflow.

    Returns
    -------
    CompiledStateGraph
        Executable LangGraph workflow.

        The compiled graph can be invoked with:

            graph.invoke(state)

    Notes
    -----
    - `StateGraph` is the graph builder.
    - The builder is not the executable graph yet.
    - `.compile()` turns the builder into a runnable graph.
    - Tests should use the compiled graph, not the uncompiled builder.

    Graph flow
    ----------
    The graph has one real node:

        build_output_message

    The edges are :

        START -> build_output_message
        build_output_message -> END

    That means:

    1. Start graph execution.
    2. Run `build_output_message`
    3. Stop graph execution.

    Why a factory function?
    -----------------------
    A factory function keeps graph construction reusable.

    Tests can call:

        graph = create_foundation_graph()

    Future route handlers or services can do the same if needed.

    In plain language:

    - create the graph builder
    - add the node
    - connect start and end
    - compile the graph so it can run
    """

    # Create a graph builder using our typed state
    #   - `FoundationGraphState` tells LangGraph which state keys exist.
    #   - For now, that means `input_message` and `output_message`.
    graph_builder = StateGraph(
        state_schema=FoundationGraphState,
    )

    # Register the node function
    #   - The string name is how edges refer to this node.
    #   - The function is what actually runs when the graph reaches the node
    graph_builder.add_node(
        node=FOUNDATION_NODE_NAME,
        action=build_output_message,
    )

    # Connect the graph start to the node
    #   - This tells LangGraph what should run first.
    graph_builder.add_edge(
        start_key=START,
        end_key=FOUNDATION_NODE_NAME,
    )

    # Connect the node to the graph end
    #   - This tells LangGraph to stop after the node has returned its update.
    graph_builder.add_edge(
        start_key=FOUNDATION_NODE_NAME,
        end_key=END,
    )

    # Compile the graph
    #   - The builder defines the structure.
    #   - The compiled graph is the runnable object used by tests and future code.
    return graph_builder.compile()

# Compile one reusable foundation graph at module import time
#   - This is fine for this tiny graph because it has no external clients,
#     database connections, API keys, or expensive setup.
#   - If future graph needs expensive resouces, prefer lazy construction or
#     dependency injection instead.
foundation_graph = create_foundation_graph()

__all__ = [
    "FOUNDATION_NODE_NAME",
    "build_output_message",
    "create_foundation_graph",
    "foundation_graph"
]