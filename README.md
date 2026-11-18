# voice-agent-open-source

Two local voice agents call each other to book a clinic appointment — no Twilio, no
ElevenLabs, no paid API keys. A black-and-white landing page sits on top so you can watch the
call happen and record it for a demo.

- **Aria** (`bot.py`) — the clinic's receptionist agent. Owns the calendar.
- **My Assistant** (`my_assistant.py`) — calls Aria on your behalf and books the slot.

Both are built the same way: **LiveKit** (WebRTC transport) + **Pipecat** (pipeline) +
**Whisper** (local STT) + **Ollama** (local LLM) + **Kokoro** (local TTS).

## Run it

Six terminals.

**1. LiveKit server** (dev mode: devkey/secret, matches `.env.example`)
```
docker run --rm -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server --dev --bind 0.0.0.0 --node-ip 127.0.0.1
```
`--bind 0.0.0.0` and `--node-ip 127.0.0.1` are required on Docker Desktop (Windows/Mac) — without
them the server only listens on the container's own loopback and advertises its internal
container IP for audio, so the signaling handshake and/or audio never reach the host.

**2. Ollama**
```
ollama serve
ollama pull llama3.2:3b
```

**3. Python setup** (once)
```
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
```

**4. Aria** — start this first, she waits for a caller
```
python bot.py
```

**5. My Assistant** — joins second, which is what makes Aria greet and the call start
```
python my_assistant.py
```

**6. The landing page**
```
uvicorn server:app --port 8000
```

Open http://localhost:8000 and press "Watch call." You don't talk on this page — it just joins
the room silently and shows the live transcript and the booking once it lands.

## What it does

Aria answers as the receptionist for "Lakeview Family Clinic": asks for the caller's name and
reason for the visit, checks open slots, and books the appointment into a local SQLite file
(`clinic.db`). The two tools the LLM can call are `check_availability` and `book_appointment`
in `appointments.py`.

My Assistant is told who it's booking for, why, and a preferred date — edit `PATIENT_NAME`,
`PATIENT_REASON`, `PREFERRED_DATE` in `.env` (or the defaults at the top of `my_assistant.py`).
It calls in, gives those details when Aria asks, takes whatever slot she offers, and says
goodbye once it's booked.

Fetch `/api/appointments` any time to see everything booked so far.

## Notes

- First run downloads the Whisper and Kokoro model weights (a few hundred MB) — expect a pause.
- This machine has no dedicated GPU, so `llama3.2:3b` and Whisper's `base` model are picked for
  CPU speed over quality. Swap `OLLAMA_MODEL` in `.env` or the model sizes in `bot.py` if you
  have more horsepower.
- The chat bubbles on the page come from a LiveKit data-channel message the bot sends after
  each turn; the voice call itself doesn't depend on that working.
