import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from .buffers import RingLog, now_s
from .config import settings
from .realtime import OpenAIRealtimeSession

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title="stefan-api-test-6 Realtime STT")

# --- CORS (tillåt *.lovable.app + listade origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_origins(),
    allow_origin_regex=r"https://.*\.lovable\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ringbuffers
ring_size = settings.RING_SIZE
front_chunks = RingLog(ring_size)   # chunkar mottagna från FE
openai_chunks = RingLog(ring_size)  # chunkar skickade (samma i detta fall)
openai_text = RingLog(ring_size)    # text från OpenAI
front_text = RingLog(ring_size)     # text skickad till FE

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/config")
def config():
    return {
        "model": settings.OPENAI_REALTIME_MODEL,
        "language": settings.LANGUAGE,
        "sample_rate": settings.SAMPLE_RATE,
        "allowed_origins": settings.parsed_origins(),
        "allow_origin_regex": r"https://.*\.lovable\.app$",
    }

# --- Debug endpoints (senaste N poster)
@app.get("/debug/front-chunks")
def debug_front_chunks(limit: int = Query(50, ge=1, le=1000)):
    return {"items": front_chunks.latest(limit)}

@app.get("/debug/openai-chunks")
def debug_openai_chunks(limit: int = Query(50, ge=1, le=1000)):
    return {"items": openai_chunks.latest(limit)}

@app.get("/debug/openai-text")
def debug_openai_text(limit: int = Query(50, ge=1, le=1000)):
    return {"items": openai_text.latest(limit)}

@app.get("/debug/front-text")
def debug_front_text(limit: int = Query(50, ge=1, le=1000)):
    return {"items": front_text.latest(limit)}

# --- WebSocket för STT
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    session: Optional[OpenAIRealtimeSession] = None
    try:
        # Skapa Realtime-session per klient
        session = OpenAIRealtimeSession(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_REALTIME_MODEL,
            language=settings.LANGUAGE,
            sample_rate=settings.SAMPLE_RATE,
        )
        await session.__aenter__()

        async def pump_client_to_openai():
            while True:
                msg = await ws.receive()
                # Både text och bytes kan förekomma. Vi förväntar oss binära PCM16.
                if "bytes" in msg and msg["bytes"] is not None:
                    raw = msg["bytes"]
                    t0 = now_s()
                    start_s, end_s = await session.send_audio_chunk(raw)
                    front_chunks.add({"t": t0, "bytes": len(raw), "start_s": start_s, "end_s": end_s})
                    openai_chunks.add({"t": t0, "bytes": len(raw), "start_s": start_s, "end_s": end_s})
                elif "text" in msg and msg["text"] is not None:
                    # valfritt kontrollmeddelande från FE
                    try:
                        data = json.loads(msg["text"])
                        cmd = data.get("type")
                        if cmd == "flush":
                            # endast relevant om server_vad är avstängt
                            # await session.commit()
                            pass
                        elif cmd == "reset":
                            await session.clear()
                        # Ignorera övrigt
                    except Exception:
                        pass

        async def pump_openai_to_client():
            async for evt in session.events():
                if not evt.get("text"):
                    continue

                payload = {
                    "type": "partial" if evt["partial"] and not evt["final"] else "final" if evt["final"] else "partial",
                    "text": evt["text"],
                    "ts": {"start_s": evt.get("start_s"), "end_s": evt.get("end_s")},
                    "event": evt.get("event_type"),
                }
                # Logga inkommande och utgående text
                openai_text.add({"t": now_s(), **payload})
                await ws.send_text(json.dumps(payload))
                front_text.add({"t": now_s(), **payload})

        await asyncio.gather(pump_client_to_openai(), pump_openai_to_client())

    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as e:
        log.exception("WebSocket error: %s", e)
        try:
            await ws.send_text(json.dumps({"type": "error", "error": str(e)}))
        except Exception:
            pass
    finally:
        if session:
            await session.__aexit__(None, None, None)
        try:
            await ws.close()
        except Exception:
            pass
