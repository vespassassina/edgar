"""The Streamable HTTP transport: every JSON-RPC message is a POST, and the answer
comes back as JSON or as a short SSE stream [TOOL-7].

Legacy HTTP+SSE (the two-endpoint transport) is not supported: one way in is
enough, and the spec's own current one is it.
"""

# request  POST the message, accepting either shape of answer
#          · application/json  the answer is the body
#          · text/event-stream the answer is the event carrying this message's id;
#            anything the server sends before it is a notification and is skipped
# The session id the server hands out on `initialize`, and the protocol version it
# agrees to, go back on every later request.

from __future__ import annotations

import json
from typing import Any


class Http:
    def __init__(self, url: str, headers: dict[str, str], timeout_s: float) -> None:
        self.url, self.headers, self.timeout_s = url, headers, timeout_s
        self.client: Any = None
        self.session: str | None = None

    async def open(self) -> None:
        import httpx  # only a session that uses a remote server pays for it (NFR-1)

        self.client = httpx.AsyncClient(timeout=self.timeout_s)

    async def request(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if self.client is None:
            raise ConnectionError("the server is not connected")
        sent = dict(self.headers)
        sent["Accept"] = "application/json, text/event-stream"
        sent["Content-Type"] = "application/json"
        if self.session:
            sent["Mcp-Session-Id"] = self.session
        async with self.client.stream("POST", self.url, json=message, headers=sent) as response:
            self.session = response.headers.get("mcp-session-id") or self.session
            if response.status_code >= 400:
                raise ConnectionError(f"HTTP {response.status_code} from {self.url}")
            if "id" not in message:
                return None
            kind = response.headers.get("content-type", "")
            if kind.startswith("text/event-stream"):
                reply = await self._event(response, message["id"])
            else:
                reply = json.loads(await response.aread())
        agreed = reply.get("result", {}).get("protocolVersion") if isinstance(reply, dict) else None
        if agreed:  # every request after the handshake names the version agreed on
            self.headers["MCP-Protocol-Version"] = str(agreed)
        return dict(reply)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    def abandon(self) -> None:
        # Its sockets belong to an event loop that has ended: let go of them.
        self.client = None

    async def _event(self, response: Any, wanted: Any) -> dict[str, Any]:
        # SSE: `data:` lines pile up until a blank line ends the event.
        data: list[str] = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                data.append(line[5:].strip())
            elif not line.strip() and data:
                event, data = json.loads("\n".join(data)), []
                if event.get("id") == wanted and "method" not in event:
                    return dict(event)
        raise ConnectionError("the stream ended before the answer arrived")
