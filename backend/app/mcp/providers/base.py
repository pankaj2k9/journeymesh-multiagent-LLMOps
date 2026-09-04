"""The adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RemoteCall:
    """One MCP tool invocation, in the remote server's own vocabulary."""

    tool: str
    arguments: dict[str, Any]


class ToolAdapter(Protocol):
    """Translates one JourneyMesh tool onto one MCP server's tools."""

    def to_remote(self, tool: str, arguments: dict[str, Any]) -> RemoteCall | None:
        """The remote call for this tool, or None if there is no faithful one.

        Returning None is a supported answer, not a failure: the client falls
        back to the in-process adapter and records that it did.
        """
        ...

    def from_remote(
        self, tool: str, payload: dict[str, Any], arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Reshape the server's response into what the agent expects.

        Returning None means the response could not be understood, which is
        also a fallback rather than an error - a half-parsed provider payload
        is exactly the kind of thing that becomes a wrong price.
        """
        ...
