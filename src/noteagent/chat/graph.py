"""The chat execution graph.

``START -> compact -> model -> (tools -> compact -> model)* -> finalize -> END``.
Persisted through LangGraph's checkpointer, so a turn resumes instead of restarting
and the user message is written by the turn preparation, never by a node.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from noteagent.chat.nodes import (
    GraphRuntime,
    compact_node,
    finalize_node,
    model_node,
    route_after_model,
    route_after_tools,
    tools_node,
)
from noteagent.conversations.records import GraphState


def build_chat_graph(runtime: GraphRuntime, checkpointer: BaseCheckpointSaver):
    """Compile the graph for one runtime against one checkpointer.

    Nodes are bound through single-argument closures: LangGraph injects its own
    ``Runtime`` into any node that declares a second parameter.
    """

    def bind(node):
        async def run(state: GraphState):
            return await node(state, runtime)

        return run

    builder = StateGraph(GraphState)
    builder.add_node("compact", bind(compact_node))
    builder.add_node("model", bind(model_node))
    builder.add_node("tools", bind(tools_node))
    builder.add_node("finalize", bind(finalize_node))

    builder.add_edge(START, "compact")
    builder.add_edge("compact", "model")
    builder.add_conditional_edges(
        "model", route_after_model, {"tools": "tools", "finalize": "finalize"}
    )
    builder.add_conditional_edges(
        "tools",
        lambda state: route_after_tools(state, runtime.budget),
        {"compact": "compact", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


async def stream_graph(
    graph, inputs: dict[str, Any], config: dict[str, Any]
) -> AsyncIterator[dict[str, Any]]:
    """Yield the SSE events the nodes emit while the graph runs to completion.

    ``updates`` are consumed as well so the caller's run completes only after the
    checkpointer has actually persisted the node's state.
    """
    async for mode, payload in graph.astream(
        inputs, config=config, stream_mode=["custom", "updates"]
    ):
        if mode == "custom":
            yield payload
