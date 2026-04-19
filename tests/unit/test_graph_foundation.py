"""
Unit tests for the foundation LangGraph workflow.

These tests verify the smallest graph in the backend before we build real
recruitment intelligence workflows.

They focus on:

- the foundation graph node
- the compiled LangGraph workflow
- state preservation
- state updates
- predictable graph output

The important question is:

    "Can the backend run a basic LangGraph workflow and get a predictable state
    back?"

This is different from future GraphRAG tests.

Future GraphRAG tests may check:

- retrieval
- evidence assembly
- candidate/job matching
- action proposals
- human approval checkpoints
- structured LLM outputs

These tests do not do any of that yet.

This unit test checks the smaller foundation pieces directly:

    FoundationGraphState
        -> build_output_message(...)
        -> {"output_message": ...}

and:

    FoundationGraphState
        -> foundation_graph.invoke(...)
        -> updated FoundationGraphState

The expected output shape is:

    {
        "input_message": "Hello from a test",
        "output_message": "Foundation graph received: Hello from a test"
    }

In plain language:

- send a tiny state into the graph
- let one node update the output message
- confirm the final state is what we expect
"""

from backend.graphs.foundation import (
    FOUNDATION_NODE_NAME,
    build_output_message,
    create_foundation_graph,
    foundation_graph,
)
from backend.graphs.state import FoundationGraphState


def make_foundation_state(
    *,
    input_message: str = "Hello from a test",
    output_message: str = "",
) -> FoundationGraphState:
    """
    Build a small valid foundation graph state for tests.

    Parameters
    ----------
    input_message : str
        Message supplied to the graph.

        This is the value the graph node will read.

    output_message : str
        Current output message.

        This usually starts as an empty string because the graph has not written
        its output yet.

    Returns
    -------
    FoundationGraphState
        Typed state dictionary suitable for the foundation graph.

    Notes
    -----
    - This helper keeps the test setup consistent.
    - The state mirrors the shape defined in `backend.graphs.state`.
    - The graph should preserve `input_message`.
    - The graph should update `output_message`.

    Example
    -------
    The default state is:

        {
            "input_message": "Hello from a test",
            "output_message": ""
        }

    In plain language:

    - create the input dictionary the graph expects
    """

    return {
        "input_message": input_message,
        "output_message": output_message,
    }


def test_foundation_node_name_is_stable() -> None:
    """
    Verify that the foundation node name is stable.

    Notes
    -----
    - The node name is used when wiring graph edges.
    - If this string changes accidentally, graph wiring and tests become harder
      to reason about.
    - Keeping it as a constant makes the graph structure explicit.

    In plain language:

    - the graph has one node
    - this test checks that the node has the expected name
    """

    assert FOUNDATION_NODE_NAME == "build_output_message"


def test_build_output_message_returns_partial_state_update() -> None:
    """
    Verify that the node returns only the field it wants to update.

    The node receives a full state:

        {
            "input_message": "Hello from a test",
            "output_message": ""
        }

    It should return a partial update:

        {
            "output_message": "Foundation graph received: Hello from a test"
        }

    Notes
    -----
    - LangGraph nodes usually return partial state updates.
    - The node does not need to return `input_message`.
    - LangGraph handles merging the returned update into the existing state.

    In plain language:

    - the node reads the input
    - the node returns the new output
    """

    state = make_foundation_state()

    update = build_output_message(state)

    assert update == {
        "output_message": "Foundation graph received: Hello from a test",
    }


def test_build_output_message_uses_current_input_message() -> None:
    """
    Verify that the node uses the input message supplied in the state.

    Notes
    -----
    - The output should not be hard-coded to one test value.
    - If the input changes, the output should reflect that input.
    - This proves the node actually reads from the state.

    Example
    -------
    If the input is:

        "Different input"

    the output should be:

        "Foundation graph received: Different input"

    In plain language:

    - change the input
    - check the output changes too
    """

    state = make_foundation_state(input_message="Different input")

    update = build_output_message(state)

    assert update == {
        "output_message": "Foundation graph received: Different input",
    }


def test_create_foundation_graph_returns_runnable_graph() -> None:
    """
    Verify that the foundation graph factory returns a runnable graph.

    Notes
    -----
    - `StateGraph` builders cannot be invoked directly.
    - `.compile()` creates the runnable graph.
    - A compiled LangGraph object should expose `.invoke(...)`.

    In plain language:

    - build the graph
    - check it can be invoked
    """

    graph = create_foundation_graph()

    # The compiled graph should expose `invoke`.
    #   - This is the method tests and future backend code use to run the graph.
    assert callable(graph.invoke)


def test_create_foundation_graph_invokes_successfully() -> None:
    """
    Verify that a freshly created foundation graph runs successfully.

    Notes
    -----
    - This uses a new graph from `create_foundation_graph()`.
    - That proves the factory function works.
    - A separate test checks the module-level `foundation_graph`.

    Expected output
    ---------------
    The graph should return:

        {
            "input_message": "Hello from a test",
            "output_message": "Foundation graph received: Hello from a test"
        }

    In plain language:

    - create a fresh graph
    - send in a state
    - check the graph returns the updated state
    """

    graph = create_foundation_graph()

    result = graph.invoke(make_foundation_state())

    assert result == {
        "input_message": "Hello from a test",
        "output_message": "Foundation graph received: Hello from a test",
    }


def test_module_level_foundation_graph_invokes_successfully() -> None:
    """
    Verify that the reusable module-level foundation graph runs successfully.

    Notes
    -----
    - `foundation_graph` is compiled at module import time.
    - This is acceptable for the tiny foundation graph because it has no external
      clients, secrets, database connections, or expensive setup.
    - This test proves the exported graph object is ready to use.

    In plain language:

    - use the graph object imported from the module
    - run it
    - check the output
    """

    result = foundation_graph.invoke(make_foundation_state())

    assert result == {
        "input_message": "Hello from a test",
        "output_message": "Foundation graph received: Hello from a test",
    }


def test_foundation_graph_preserves_input_message() -> None:
    """
    Verify that the graph does not overwrite the input message.

    Notes
    -----
    - The node only returns `output_message`.
    - LangGraph should keep the original `input_message` in the state.
    - This proves the graph update is additive rather than destructive.

    In plain language:

    - input goes in
    - output is added
    - the original input is still there
    """

    result = foundation_graph.invoke(
        make_foundation_state(input_message="Preserve this input")
    )

    assert result["input_message"] == "Preserve this input"


def test_foundation_graph_updates_output_message() -> None:
    """
    Verify that the graph replaces the existing output message.

    Notes
    -----
    - The input state may contain an old `output_message`.
    - The node returns a new `output_message`.
    - LangGraph should merge the new value into the final state.

    Example
    -------
    Starting state:

        {
            "input_message": "Fresh input",
            "output_message": "old output"
        }

    Final state:

        {
            "input_message": "Fresh input",
            "output_message": "Foundation graph received: Fresh input"
        }

    In plain language:

    - old output goes in
    - new output comes out
    """

    result = foundation_graph.invoke(
        make_foundation_state(
            input_message="Fresh input",
            output_message="old output",
        )
    )

    assert result == {
        "input_message": "Fresh input",
        "output_message": "Foundation graph received: Fresh input",
    }