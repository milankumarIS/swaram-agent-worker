# Voice Agent Worker

This is a Python-based AI agent worker for the Voice Agent Platform. It handles real-time voice interaction using LiveKit, Google Gemini (LLM), and Sarvam AI (STT/TTS).

## Features
- **Named Dispatch**: Registers as `my-agent` on LiveKit.
- **Dynamic Config**: Fetches agent system prompts and API keys from the Node.js backend.
- **Real-time Transcripts**: Streams conversation text back to the LiveKit data channel for UI display.
- **State Sync**: Updates the backend when sessions start and end.

## Setup

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Setup environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your LIVEKIT, BACKEND_URL, and WORKER_SECRET
   ```

3. **Install dependencies**:
   ```bash
   uv sync
   ```

4. **Run the worker**:
   ```bash
   uv run python agent.py start
   ```

## Integration Flow
1. Visitor starts call from Embed Widget.
2. Node.js Backend creates room with `metadata: {agentId, sessionId}`.
3. This Worker joins, reads metadata, and calls `{BACKEND_URL}/internal/agents/{agentId}/config`.
4. Worker starts `Assistant` session with fetched config.
5. On disconnect, Worker calls `{BACKEND_URL}/api/sessions/{sessionId}/end`.
