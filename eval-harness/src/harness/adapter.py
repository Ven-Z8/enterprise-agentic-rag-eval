"""The adapter interface — the one seam between "any agent" and the harness.

An adapter wraps some agent system (raw API loop, a framework, a hosted endpoint)
and exposes a single method: given a test-case input, run the agent and return a
fully-populated Trace. The harness never touches the agent directly; it only ever
sees Traces. That's what makes "plug in any agent" true.

Two concrete adapters are planned (Phase 1): a raw-API adapter and one popular
framework adapter. New backends implement this Protocol — no base class to inherit,
just match the shape.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from harness.traces.trace import Trace


@runtime_checkable
class AgentAdapter(Protocol):
    name: str  # identifies the agent+version in reports, e.g. "raw-api@claude-opus-4-8"

    def run(self, input: str) -> Trace:
        """Run the agent on one input and return its full trajectory as a Trace.

        Implementations must populate final_output and citations; steps/usage/latency
        are best-effort but strongly encouraged (metrics degrade gracefully without them).
        Must not raise on agent-level failures — capture them in the Trace (e.g. a
        response step with error content) so a crash counts as a scored failure, not a
        harness abort.
        """
        ...
