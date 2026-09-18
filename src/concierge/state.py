"""Graph state schema for the concierge agent."""

from __future__ import annotations

from langgraph.graph import MessagesState


class ConciergeState(MessagesState):
    """Messages plus a small counter for tracing observability.

    `retrieval_calls` increments each time the agent calls search_banking_docs.
    A high value on a single trace is a useful signal for Engine to cluster
    on as a "agent looped on retrieval" anomaly.
    """

    retrieval_calls: int
