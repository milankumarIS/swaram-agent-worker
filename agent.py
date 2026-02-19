# Voice Agent Worker — agent.py
import os
import json
import asyncio
import logging
import httpx
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io, WorkerOptions
from livekit.plugins import google, sarvam, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent-worker")

# Platform settings
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:4003")
WORKER_SECRET = os.getenv("WORKER_SECRET", "")

async def fetch_agent_config(agent_id: str):
    """Fetch decrypted agent configuration from the Node.js backend."""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{BACKEND_URL}/internal/agents/{agent_id}/config"
            headers = {"X-Worker-Secret": WORKER_SECRET}
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch agent config: {e}")
        return None

async def end_session(session_id: str):
    """Notify backend that the session has ended."""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{BACKEND_URL}/api/sessions/{session_id}/end"
            headers = {"X-Worker-Secret": WORKER_SECRET}
            await client.patch(url, headers=headers)
            logger.info(f"Session {session_id} marked as ended in backend.")
    except Exception as e:
        logger.warning(f"Failed to end session {session_id} in backend: {e}")

class DynamicAssistant(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)

server = AgentServer()

@server.rtc_session(agent_name=os.getenv("AGENT_NAME", "my-agent"))
async def voice_agent_session(ctx: agents.JobContext):
    """Entry point for each LiveKit session."""
    logger.info(f"Starting session for room {ctx.room.name}")
    
    # 1. Parse room or job metadata to get agentId and sessionId
    metadata_raw = ctx.room.metadata or ctx.job.metadata or "{}"
    session_id = None
    try:
        metadata = json.loads(metadata_raw)
        agent_id = metadata.get("agentId")
        session_id = metadata.get("sessionId")
    except json.JSONDecodeError:
        logger.error(f"Invalid room metadata: {metadata_raw}")
        return

    if not agent_id:
        logger.error("No agentId found in room metadata.")
        return

    # 2. Fetch agent config (prompts, API keys, etc.) from backend
    config = await fetch_agent_config(agent_id)
    if not config:
        logger.error("Could not load agent config. Closing session.")
        return

    logger.info(f"Config loaded for agent: {config['name']}")

    # 3. Sarvam TTS speaker fallback
    tts_voice = config.get("tts_voice", "anushka")
    if tts_voice not in ["anushka", "manisha", "vidya", "arya", "abhilash", "karun", "hitesh"]:
        logger.warning(f"Speaker '{tts_voice}' is not compatible with bulbul:v2. Falling back to 'anushka'.")
        tts_voice = "anushka"

    # 4. Initialize AgentSession
    session = AgentSession(
        preemptive_generation=True,
        stt=sarvam.STT(
            api_key=config["sarvam_api_key"],
            model="saarika:v2.5",
            language=config["stt_language_code"],
        ),
        llm=google.LLM(
            api_key=config["llm_api_key"],
            model=config.get("llm_model", "gemini-2.5-flash"),
        ),
        tts=sarvam.TTS(
            api_key=config["sarvam_api_key"],
            speaker=tts_voice,
            target_language_code=config["tts_language_code"],
        ),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    # 5. Start session and emit transcripts
    try:
        await session.start(
            room=ctx.room,
            agent=DynamicAssistant(instructions=config["system_prompt"]),
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(noise_cancellation=None),
            ),
        )

        # Emit transcripts back to UI
        def on_transcript(role: str, text: str):
            asyncio.create_task(ctx.room.local_participant.publish_data(
                json.dumps({"type": "transcript", "role": role, "text": text}),
                reliable=True
            ))

        session.on("user_transcript", lambda text: on_transcript("user", text))
        session.on("agent_transcript", lambda text: on_transcript("agent", text))

        # 6. Greet and wait
        await session.generate_reply(instructions=config.get("welcome_message", "Hello! How can I help you?"))

        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1)
            
    finally:
        if session_id:
            await end_session(session_id)
        logger.info(f"Session {ctx.room.name} finished.")

if __name__ == "__main__":
    agents.cli.run_app(server)
