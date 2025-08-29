# stefan-api-test-6 — FastAPI Realtime STT backend

Backend för live-transkribering med **FastAPI** → **OpenAI Realtime API** över WebSocket.
Frontend (Lovable) skickar PCM16-chunks till `/ws`. Backend skickar tillbaka partial/final text i realtid.

## Huvudfunktioner
- WebSocket `/ws` tar emot **PCM16 (mono, 16 kHz)** och skickar vidare till OpenAI Realtime.
- **Server‑VAD** i Realtime (auto-commit) för smidig streaming.
- **Partial & final** transkriptioner i retur, på svenska.
- Debug-endpoints (öppna, senaste N poster):
  - `GET /debug/front-chunks` – chunkar mottagna från frontend
  - `GET /debug/openai-chunks` – chunkar skickade till OpenAI
  - `GET /debug/openai-text` – text mottagen från OpenAI
  - `GET /debug/front-text` – text skickad till frontend
- Övrigt: `GET /healthz`, `GET /config`

> **Obs – tidsstämplar:** Realtime-transcribe‑modellerna (`gpt-4o-(mini-)transcribe`) har idag begränsat stöd
> för detaljerade **ord**‑tidsstämplar. Koden levererar segment‑/chunk‑nivåns approx‑tidsstämplar baserat på
> inkommande PCM16 (sample rate) och event‑metadata. För **exakt ord‑timestamp** kan batch‑läget med `whisper-1`
> krävas.

## Kör lokalt

1) Skapa `.env` från mallen och fyll i din nyckel:
```bash
cp .env.example .env
# OPENAI_API_KEY=sk-....
```

2) Installera & starta:
```bash
make install
make run
# servern kör på http://127.0.0.1:8000
```

3) WebSocket
- Anslut till `ws://127.0.0.1:8000/ws`
- Skicka **binära** PCM16‑chunkar (mono, 16 kHz). Backend gör base64 och streamar till OpenAI Realtime.
- Mottag JSON‑meddelanden:
  ```json
  { "type": "partial" | "final", "text": "...", "ts": { "start_s": 0.0, "end_s": 0.32 } }
  ```

## Deploy på Render
- Byggs automatiskt via `Dockerfile`.
- Ställ in env vars i Render Dashboard:
  - `OPENAI_API_KEY`
  - (valfritt) `OPENAI_REALTIME_MODEL` (default `gpt-4o-mini-transcribe`)
  - `LANGUAGE` (default `sv`)
  - `ALLOWED_ORIGINS` (kommaseparerad lista – default inkluderar `https://stefan-api-test-6.lovable.app` och regex för `*.lovable.app`)
- Exponera port **8000**.

## Struktur
```
app/
  main.py
  realtime.py
  buffers.py
  config.py
  __init__.py
Dockerfile
Makefile
requirements.txt
.env.example
README.md
```

## Licens
MIT
