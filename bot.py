"""Clinic voice agent: LiveKit + local Whisper STT + local Ollama LLM + local Kokoro TTS.

Everything runs on this machine. No paid API keys.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from livekit import api as lk_api
from loguru import logger

import appointments
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.services.llm_service import FunctionCallParams
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

SYSTEM_PROMPT = (
    "You are Aria, the appointment-booking receptionist for Lakeview Family Clinic. "
    "You talk with patients on a voice call to book, check, or reschedule an appointment. "
    "Always ask for the patient's name and the reason for the visit before booking. "
    "Use check_availability before offering a time. Use book_appointment once the patient "
    "confirms a specific date and time. Dates must be given as YYYY-MM-DD. "
    "Your replies are spoken aloud: keep them short, warm, and plain — no emojis, no lists, "
    "no markdown, no symbols that can't be said out loud."
)


def _bot_token() -> str:
    token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    token.with_identity("clinic-agent").with_name("Aria")
    token.with_grants(lk_api.VideoGrants(room_join=True, room=ROOM_NAME))
    return token.to_jwt()


_transport = None  # set in main(), used by the tool handlers below to broadcast


async def check_availability(params: FunctionCallParams, date: str):
    """Look up open appointment slots on a given day.

    Args:
        date: The day to check, formatted YYYY-MM-DD.
    """
    slots = appointments.available_slots(date)
    await params.result_callback({"date": date, "available_slots": slots})


async def book_appointment(params: FunctionCallParams, patient_name: str, reason: str, date: str, time: str):
    """Book a confirmed appointment slot for a patient.

    Args:
        patient_name: The patient's full name.
        reason: A short reason for the visit.
        date: Appointment day, formatted YYYY-MM-DD.
        time: Appointment time, formatted HH:MM (24-hour), must be one of the available slots.
    """
    result = appointments.book(patient_name, reason, date, time)
    if result.get("ok") and _transport is not None:
        await _transport.send_message({"type": "booking", **result})
    await params.result_callback(result)


async def main():
    global _transport
    appointments.init_db()

    transport = LiveKitTransport(
        url=LIVEKIT_URL,
        token=_bot_token(),
        room_name=ROOM_NAME,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )
    _transport = transport

    stt = WhisperSTTService(settings=WhisperSTTService.Settings(model="base"))

    llm = OLLamaLLMService(
        base_url="http://localhost:11434/v1",
        settings=OLLamaLLMService.Settings(
            model=OLLAMA_MODEL,
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    tts = KokoroTTSService(settings=KokoroTTSService.Settings(voice="af_heart"))

    context = LLMContext(tools=[check_availability, book_appointment])
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
        await transport.send_message({"type": "line", "speaker": "Aria", "text": message.content})

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant_id):
        await asyncio.sleep(1)
        from pipecat.frames.frames import TTSSpeakFrame

        await worker.queue_frame(
            TTSSpeakFrame(
                "Hi, you've reached Lakeview Family Clinic. I'm Aria. "
                "Would you like to book an appointment?"
            )
        )

    logger.info(f"Aria is live in room '{ROOM_NAME}' — model {OLLAMA_MODEL}")
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
