"""Serves the landing page and mints LiveKit room tokens for the browser."""

import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from livekit import api as lk_api

import appointments

load_dotenv(override=True)

LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
ROOM_NAME = os.environ.get("ROOM_NAME", "clinic-demo")

appointments.init_db()

app = FastAPI()


@app.get("/api/token")
def issue_token():
    identity = f"observer-{uuid.uuid4().hex[:8]}"
    token = lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    token.with_identity(identity).with_name("Observer")
    token.with_grants(lk_api.VideoGrants(room_join=True, room=ROOM_NAME, can_publish=False))
    return {"token": token.to_jwt(), "url": LIVEKIT_URL, "room": ROOM_NAME}


@app.get("/api/appointments")
def list_appointments():
    return appointments.recent()


app.mount("/", StaticFiles(directory="static", html=True), name="static")
