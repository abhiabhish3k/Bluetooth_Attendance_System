"""
WebSocket connection manager.

Maintains per-channel sets of active WebSocket connections and provides
a thread-safe broadcast helper.  Import the singleton ``ws_manager``
wherever you need to push events.
"""

import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage active WebSocket connections grouped by named channels."""

    def __init__(self) -> None:
        # channel → set of connected WebSocket objects
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(channel, set()).add(ws)
        logger.info(
            "WS client connected to channel '%s' (total: %d)",
            channel,
            len(self._connections[channel]),
        )

    def disconnect(self, channel: str, ws: WebSocket) -> None:
        self._connections.get(channel, set()).discard(ws)
        logger.info(
            "WS client disconnected from channel '%s' (total: %d)",
            channel,
            len(self._connections.get(channel, set())),
        )

    def has_subscribers(self, channel: str) -> bool:
        """Return True if at least one client is subscribed to *channel*."""
        return bool(self._connections.get(channel))

    async def broadcast(self, channel: str, data: dict) -> None:
        """Serialise *data* to JSON and send it to every client on *channel*.

        Silently drops dead connections instead of raising.
        """
        conns = self._connections.get(channel)
        if not conns:
            return

        msg = json.dumps(data, default=str)
        dead: Set[WebSocket] = set()

        for ws in list(conns):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(channel, ws)

    async def broadcast_all(self, data: dict) -> None:
        """Broadcast *data* to every connected client on every channel."""
        tasks = [
            self.broadcast(ch, data)
            for ch in list(self._connections.keys())
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# Module-level singleton – import this everywhere
ws_manager = ConnectionManager()
