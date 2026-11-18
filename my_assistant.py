"""My Assistant: a second local voice agent that calls the clinic's agent (Aria) and
books an appointment on your behalf — same local stack as bot.py (Whisper + Ollama + Kokoro),
just a different identity, prompt, and no booking tools (Aria owns the clinic's calendar).
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv
from livekit import api as lk_api
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="INFO")

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
ROOM_NAME = os.environ.get("ROOM_NAME", "clinic-demo")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

# --- who you're booking for and what you want — edit these for your own demo ---
PATIENT_NAME = os.environ.get("PATIENT_NAME", "Mujtaba Junaid")
PATIENT_REASON = os.environ.get("PATIENT_REASON", "an annual checkup")
PREFERRED_DATE = os.environ.get(
    "PREFERRED_DATE", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
)

SYSTEM_PROMPT = (
    f"You are My Assistant, calling a clinic's phone agent on behalf of {PATIENT_NAME} to book "
    f"an appointment. You are not the patient — you are calling for them. "
    f"The visit is for {PATIENT_REASON}. The preferred date is {PREFERRED_DATE}, "
    "but take whatever slot the clinic agent offers that day; if that day has nothing open, "
    "ask for the nearest other day. "
    f"When asked for the patient's name, give '{PATIENT_NAME}'. When asked the reason for the "
    f"visit, give '{PATIENT_REASON}'. "
    "Once the clinic agent confirms the appointment is booked, thank them, say goodbye, and stop "
    "talking. Your replies are spoken aloud: keep them short and plain — no emojis, no lists, no "
    "markdown, no symbols that can't be said out loud."
)


def _token() -> str:
    token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    token.with_identity("my-assistant").with_name("My Assistant")
    token.with_grants(lk_api.VideoGrants(room_join=True, room=ROOM_NAME))
    return token.to_jwt()


async def main():
    transport = LiveKitTransport(
        url=LIVEKIT_URL,
        token=_token(),
        room_name=ROOM_NAME,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    stt = WhisperSTTService(settings=WhisperSTTService.Settings(model="base"))

    llm = OLLamaLLMService(
        base_url="http://localhost:11434/v1",
        settings=OLLamaLLMService.Settings(
            model=OLLAMA_MODEL,
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    tts = KokoroTTSService(settings=KokoroTTSService.Settings(voice="am_michael"))

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner()
    await runner.add_workers(worker)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message):
        await transport.send_message(
            {"type": "line", "speaker": "My Assistant", "text": message.content}
        )

    logger.info(
        f"My Assistant is live in room '{ROOM_NAME}' — booking for {PATIENT_NAME} "
        f"on {PREFERRED_DATE}, model {OLLAMA_MODEL}"
    )
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
