from __future__ import annotations

import logging
from typing import Any

from master.application.game_manager import GameManager

__all__ = ["ControlHandler"]

log = logging.getLogger(__name__)


class ControlHandler:
    async def handle_message(
        self, message: dict[str, Any], game_manager: GameManager,
    ) -> dict[str, Any] | None:
        msg_type = message.get("type", "")
        payload = message.get("payload", {})

        if msg_type == "start_game":
            first_turn = payload.get("first_turn", "human")
            ai_strategy = payload.get("ai_strategy")
            if ai_strategy:
                log.info("Dynamic strategy switch to: %s", ai_strategy)
            await game_manager.start_game(first_turn)
            return None

        if msg_type == "force_reset":
            await game_manager.force_reset()
            return None

        if msg_type == "get_internal_state":
            state = game_manager.get_internal_state()
            return {"type": "internal_state_response", "payload": state}

        log.warning("Unknown control message type: %s", msg_type)
        return None
