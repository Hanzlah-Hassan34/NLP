# Phase IV - DentaBot Microservice API

## Delivered
- FastAPI backend service
- WebSocket endpoint at `/ws/chat`
- JSON request/response protocol
- Async request handling with per-session locking for concurrency safety
- Streaming token events over WebSocket
- Robust validation and error events
- Phase II/III conversation orchestration (state machine, prompt templates, slot memory, policy guardrails)
- Phase V web chat interface at `/` (ChatGPT-style layout, streaming messages, conversation history, new chat/reset)
- Voice pipeline endpoint `POST /v1/voice/reply` (local ASR -> LLM -> local TTS)
- Dockerized deployment
- Postman collection for health/chat validation

## Project Structure
- `app/main.py`: FastAPI routes + WebSocket endpoint
- `app/models.py`: Pydantic schemas and event types
- `app/engine.py`: session store + async engine with optional local GGUF LLM backend
- `app/web/index.html`: web chat UI shell
- `app/web/assets/app.js`: frontend state + WebSocket integration
- `app/web/assets/styles.css`: UI styling
- `Dockerfile`, `docker-compose.yml`: container runtime
- `postman/DentaBot_Phase4.postman_collection.json`: tests/examples

## Run Locally
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Enable Local LLM (Phase II/III model path)
By default, the service runs in rule fallback mode. To enable the local GGUF model backend:

```bash
pip install -r requirements-llm.txt
```

Set environment variables before starting server:

```bash
set DENTABOT_MODEL_PATH=C:\path\to\your\Qwen2.5-1.5B-Instruct-Q4_K_M.gguf
set DENTABOT_N_CTX=2048
set DENTABOT_GPU_LAYERS=-1
```

`GET /healthz` includes `"backend": "llama-cpp"` when active, otherwise `"rule-fallback"`.

## Enable Voice Pipeline (Local CPU)
Install voice dependencies:

```bash
pip install -r requirements.txt
```

Configure ASR and TTS before startup:

```bash
set DENTABOT_ASR_MODEL=tiny.en
set DENTABOT_ASR_DEVICE=cpu
set DENTABOT_ASR_COMPUTE_TYPE=int8
set DENTABOT_TTS_MODEL_PATH=C:\path\to\piper\en_US-lessac-medium.onnx
set DENTABOT_TTS_CONFIG_PATH=C:\path\to\piper\en_US-lessac-medium.onnx.json
set DENTABOT_VOICE_CONCURRENCY=4
```

Health includes `asr_ready`, `tts_ready`, and init errors when models are missing.

## Docker Run
```bash
docker compose up --build
```

## API Contracts

### WebSocket `/ws/chat`
Client message examples:
```json
{"type":"ping"}
{"type":"reset","session_id":"demo-1"}
{"type":"chat","session_id":"demo-1","message":"I need an appointment","stream":true}
```

Server event format:
```json
{
  "type": "token",
  "session_id": "demo-1",
  "timestamp": "2026-03-05T12:00:00+00:00",
  "data": {
    "token": "Hello "
  }
}
```

Event sequence for streaming chat:
- `ack`
- `start`
- one or more `token`
- `complete`

Error format:
- `type: error`
- `data.code` and `data.detail`

### HTTP Fallback `POST /v1/chat`
Request:
```json
{
  "session_id": "demo-http-1",
  "message": "What are your hours?"
}
```

### Voice `POST /v1/voice/reply`
`multipart/form-data` fields:
- `session_id` (string)
- `audio_extension` (`webm` or `wav`)
- `audio` (binary file)

Response:
```json
{
  "session_id": "demo-voice-1",
  "transcript": "I need a check-up tomorrow morning",
  "reply": "Sure, I can help with that...",
  "state": "BOOKING",
  "turn_count": 2,
  "asr_ms": 180,
  "llm_ms": 260,
  "tts_ms": 210,
  "total_ms": 650,
  "audio_base64": "UklGR..."
}
```

Response:
```json
{
  "session_id": "demo-http-1",
  "reply": "We are open Monday to Saturday, 9:00 AM to 7:00 PM...",
  "state": "FAQ",
  "turn_count": 2
}
```
