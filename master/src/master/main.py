from __future__ import annotations

import asyncio
import logging

from master.adapters.algorithm_strategy import AlgorithmStrategy
from master.adapters.control_handler import ControlHandler
from master.adapters.llm_reaction_adapter import LLMReactionAdapter
from master.adapters.llm_strategy import LLMStrategy
from master.adapters.robot_adapter import RobotWebSocketAdapter
from master.adapters.unity_adapter import UnityWebSocketAdapter
from master.adapters.vision_adapter import VisionWebSocketAdapter
from master.adapters.ws_server import WebSocketServer
from master.application.ai_turn import AITurnProcessor
from master.application.game_manager import GameManager
from master.application.human_turn import HumanTurnProcessor
from master.config import load_config

__all__ = ["main"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()

    ws_server = WebSocketServer()

    vision = VisionWebSocketAdapter(ws_server)
    robot = RobotWebSocketAdapter(ws_server)
    unity = UnityWebSocketAdapter(ws_server)

    if config.ai_strategy == "llm":
        strategy = LLMStrategy(
            api_key=config.llm_api_key,
            model=config.llm_model,
        )
    else:
        reaction_generator = LLMReactionAdapter(
            api_key=config.llm_api_key,
            model=config.llm_model,
        )
        strategy = AlgorithmStrategy(
            reaction_generator=reaction_generator,
        )

    human_turn = HumanTurnProcessor(vision=vision)
    ai_turn = AITurnProcessor(
        strategy=strategy, robot=robot,
        vision=vision, unity=unity,
    )

    game_manager = GameManager(
        strategy=strategy, vision=vision,
        robot=robot, unity=unity,
        human_turn=human_turn, ai_turn=ai_turn,
    )

    control = ControlHandler()
    ws_server.set_control_handler(control)
    ws_server.set_game_manager(game_manager)
    ws_server.set_disconnect_handler(game_manager.on_client_disconnected)

    log.info(
        "Starting Master (strategy=%s, port=%d)",
        config.ai_strategy, config.port,
    )
    await ws_server.start(host=config.host, port=config.port)


if __name__ == "__main__":
    asyncio.run(main())
