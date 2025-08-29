import asyncio
import base64
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

import websockets

log = logging.getLogger("realtime")


def b64_audio_pcm16(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def safe_get(d: Dict[str, Any], path: str, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


class OpenAIRealtimeSession:
    '''
    Minimal wrapper runt Realtime WebSocket (server-to-server).
    - Skickar input_audio_buffer.append med base64-enkoderad PCM16
    - Lyssnar på transkriptionshändelser och yield:ar {type, text, start_s, end_s, raw}
    '''
    def __init__(
        self,
        api_key: str,
        model: str,
        language: str = "sv",
        sample_rate: int = 16000,
        server_vad_silence_ms: int = 550,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.server_vad_silence_ms = server_vad_silence_ms

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._audio_time_s = 0.0  # approx clock via incoming bytes

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self):
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await websockets.connect(url, extra_headers=headers, max_size=16 * 1024 * 1024)

        # Konfigurera sessionen: PCM16 + svenska + server-VAD + transcribe-only
        session_update = {
            "type": "session.update",
            "session": {
                "input_audio_format": {"format": "pcm16", "sample_rate_hz": self.sample_rate},
                "input_audio_transcription": {"model": self.model, "language": self.language},
                "turn_detection": {"type": "server_vad", "silence_duration_ms": self.server_vad_silence_ms},
                # Vi vill INTE ha assistent-svar, bara transkript av input
                "modalities": ["text"],
            },
        }
        await self._send_json(session_update)

    async def close(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _send_json(self, obj: Dict[str, Any]) -> None:
        assert self._ws is not None
        payload = json.dumps(obj)
        await self._ws.send(payload)

    async def send_audio_chunk(self, raw_pcm16: bytes) -> Tuple[float, float]:
        '''
        Skickar en audio-chunk. Returnerar (start_s, end_s) approx utifrån chunk-längd/samplerate.
        '''
        assert self._ws is not None
        n_samples = len(raw_pcm16) / 2.0  # 16-bit
        dur_s = n_samples / float(self.sample_rate)
        start_s = self._audio_time_s
        end_s = start_s + dur_s
        self._audio_time_s = end_s

        evt = {"type": "input_audio_buffer.append", "audio": b64_audio_pcm16(raw_pcm16)}
        await self._send_json(evt)
        return start_s, end_s

    async def commit(self) -> None:
        '''Om du vill committa manuellt (ej nödvändigt med server_vad).'''
        await self._send_json({"type": "input_audio_buffer.commit"})

    async def clear(self) -> None:
        self._audio_time_s = 0.0
        await self._send_json({"type": "input_audio_buffer.clear"})

    async def events(self) -> AsyncGenerator[Dict[str, Any], None]:
        '''
        Lyssnar på alla event från Realtime och yield:ar transkriptionsrelaterade.
        Vi försöker hantera olika eventnamn som förekommer i praktiken.
        '''
        assert self._ws is not None
        while True:
            try:
                msg = await self._ws.recv()
            except websockets.ConnectionClosed:
                break

            try:
                data = json.loads(msg)
            except Exception:
                log.warning("Non-JSON message from Realtime: %s", msg[:200])
                continue

            evt_type = data.get("type", "")

            # Kandidater vi bryr oss om (varierar något mellan snapshots/leverantör):
            # - conversation.item.input_audio_transcription.delta / .completed / .done
            # - response.audio_transcript.delta / .done
            # - response.text.delta (fallback)
            # Läsa textfält: text / text_delta / transcript / transcript_delta
            def extract_text(d: Dict[str, Any]) -> Optional[str]:
                for k in ("text", "text_delta", "transcript", "transcript_delta"):
                    v = d.get(k)
                    if isinstance(v, str) and v:
                        return v
                # ibland kapslat
                v = (
                    d.get("audio") or {}
                ).get("transcript") or d.get("transcription") or safe_get(d, "response.output_text")
                if isinstance(v, str) and v:
                    return v
                return None

            is_partial = any(s in evt_type for s in (".delta", ".partial"))
            is_final = any(s in evt_type for s in (".done", ".completed", ".final"))

            text = extract_text(data) or ""

            # timestamps: vissa event har metadata; annars använd approx-klocka
            start_s = safe_get(data, "audio.start_time_s", None)
            end_s = safe_get(data, "audio.end_time_s", None)

            yield {
                "event_type": evt_type,
                "partial": is_partial and not is_final,
                "final": is_final,
                "text": text,
                "start_s": start_s,
                "end_s": end_s,
                "raw": data,
            }
