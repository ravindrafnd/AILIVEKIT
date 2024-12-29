import asyncio
from datetime import datetime
import logging
import os
import re
import json
import requests
from typing import Optional
from livekit import rtc
from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero
from livekit.agents.llm import ChatContext, ChatMessage, ChatRole

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("voice_business_agent.log", mode="a")
    ],
)
logger = logging.getLogger("voice-business-agent")

# Load environment variables
load_dotenv(dotenv_path=".env.local")

class BusinessVoiceAgent(VoicePipelineAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.awaiting_phone_number = False

    

def prewarm(proc: JobContext):
    """Prewarm function to load resources."""
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("VAD model loaded successfully during prewarm.")

async def entrypoint(ctx: JobContext):
    """Entrypoint for the voice assistant agent."""
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a helpful voice assistant. Your primary task is to answer callers' queries. "
            "Ask for their query and provide relevant responses."
        ),
    )

    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    logger.info(f"Participant joined: {participant.identity}")

    agent = BusinessVoiceAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4-turbo"),
        tts=openai.TTS(),
        chat_ctx=initial_ctx,
    )
    @agent.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        logger.info(f"User speech committed: {msg.content}")
        asyncio.create_task(handle_user_message(msg.content))
    async def handle_user_message(message: str):
        """Process user speech and send it to the webhook."""
        url = "https://fonada.app.n8n.cloud/webhook/ba54b728-8f66-4ae6-9a28-9a06ea5f159b"
        payload = {
            "data": message,
            "session_id": "677777777"
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                print()
                response_data = response.json()
                print(response_data.get("output", "Response received."))
                await agent.say(response_data.get("output", "Response received."))
            else:
                logger.error(f"Webhook Error: {response.status_code} - {response.text}")
                await agent.say("Sorry, there was an error processing your request.")
        except Exception as e:
            logger.exception("Error while calling the webhook")
            await agent.say("An internal error occurred. Please try again later.")

 

    @agent.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        logger.info(f"Agent speech committed: {msg.content}")

    agent.start(ctx.room, participant)
    await agent.say("Hello! How can I assist you today?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )
