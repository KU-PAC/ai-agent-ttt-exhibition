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
from master.application.ports import LLMClientPort
from master.config import Config, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


def _build_llm_client(config: Config) -> LLMClientPort:
    if config.llm_provider == "openai":
        from master.adapters.llm_client import OpenAILLMClient

        return OpenAILLMClient(
            api_key=config.llm_api_key,
            model=config.llm_model,
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
        )
    from master.adapters.llm_client import AnthropicLLMClient

    return AnthropicLLMClient(
        api_key=config.llm_api_key,
        model=config.llm_model,
        max_tokens=config.llm_max_tokens,
    )


async def main() -> None:
    config = load_config()

    ws_server = WebSocketServer()

    vision = VisionWebSocketAdapter(
        ws_server,
        timeout=config.vision_timeout,
        max_retries=config.vision_max_retries,
    )
    robot = RobotWebSocketAdapter(
        ws_server,
        placement_timeout=config.robot_timeout,
    )
    unity = UnityWebSocketAdapter(ws_server)

    llm_client = _build_llm_client(config)

    reaction_generator = LLMReactionAdapter(
        llm_client=llm_client,
        max_retries=config.llm_max_retries,
        timeout=config.llm_timeout,
    )

    if config.ai_strategy == "llm":
        strategy = LLMStrategy(
            llm_client=llm_client,
            max_retries=config.llm_max_retries,
            timeout=config.llm_timeout,
        )
    else:
        strategy = AlgorithmStrategy(reaction_generator=reaction_generator)

    human_turn = HumanTurnProcessor(
        vision=vision,
        poll_interval=config.poll_interval,
        stable_count_required=config.stable_count_required,
    )
    ai_turn = AITurnProcessor(
        strategy=strategy,
        robot=robot,
        vision=vision,
        unity=unity,
    )

    game_manager = GameManager(
        vision=vision,
        robot=robot,
        unity=unity,
        human_turn=human_turn,
        ai_turn=ai_turn,
        reaction_generator=reaction_generator,
        game_over_wait=config.game_over_wait,
    )

    control = ControlHandler()
    ws_server.set_control_handler(control)
    ws_server.set_game_manager(game_manager)
    ws_server.set_disconnect_handler(game_manager.on_client_disconnected)

    log.info(
        "Starting Master (strategy=%s, provider=%s, port=%d)",
        config.ai_strategy,
        config.llm_provider,
        config.port,
    )
    await ws_server.start(host=config.host, port=config.port)


if __name__ == "__main__":
    asyncio.run(main())
