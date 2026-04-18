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

This is different grom future GraphRAG tests.

Future GraphRAG tests may check:

- retrieval
- evidence assembly
- candidate/job matching
- action proposals
- human approval checkpoints
- strucutred LLM outputs

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