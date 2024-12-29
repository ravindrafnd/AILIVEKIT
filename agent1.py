import asyncio
from asyncio import QueueEmpty
from datetime import datetime
import logging
import os
import re
import json
import requests
from typing import Optional
from livekit import rtc
from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero
from livekit.agents.llm import (
ChatContext,
ChatMessage,
ChatRole,
)
load_dotenv(dotenv_path=".env.local")
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

AGENT_NUMBER = "9650101554"



class BusinessVoiceAgent(VoicePipelineAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.awaiting_phone_number = False
        self.queue=asyncio.Queue
    def validate_phone_number(self, text: str) -> Optional[str]:
        """Extract and validate a 10-digit Indian phone number from text."""
        logger.debug(f"Validating phone number from text: {text}")
        cleaned_text = "".join(char for char in text if char.isdigit())
        pattern = r"[6-9]\d{9}"
        matches = re.findall(pattern, cleaned_text)

        if matches:
            valid_number = matches[0]
            logger.info(f"Valid phone number found: {valid_number}")
            return valid_number

        logger.info("No valid phone number found in text")
        return None

    async def handle_call_transfer(self, customer_number: str) -> str:
        """Initiate a call transfer."""
        try:
            logger.info(f"Transferring call to {customer_number}")
            api_endpoint = "https://c2c.ivrobd.com/api/c2c/process"

            payload = {
                "secretKey": os.getenv("C2C_SECRET_KEY"),
                "clientId": os.getenv("C2C_CLIENT_ID"),
                "agentNumber": AGENT_NUMBER,
                "customerNumber": customer_number,
            }

            headers = {"Content-Type": "application/json"}
            response = requests.post(api_endpoint, json=payload, headers=headers, timeout=30,verify=False)

            if response.status_code == 200:
                logger.info("Call transfer successful.")
                return "Call transfer initiated. You'll receive a call shortly."
            else:
                logger.error(f"API Error: {response.status_code} - {response.text}")
                return "Call transfer failed. Please try again."
        except Exception as e:
            logger.exception("Error during call transfer")
            return "An error occurred while connecting the call. Please try again later."


async def entrypoint(ctx: JobContext):
    
    """Entrypoint for the voice assistant agent."""
    
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a helpful voice assistant. Your primary task is to connect callers with agents. "
            "Ask for their mobile number to proceed with the connection.remove special character or space from mobile number."
        ),
    )
    agent = BusinessVoiceAgent(
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4-turbo"),
        tts=openai.TTS(),
        chat_ctx=initial_ctx,
    )
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    local_participant = ctx.room.local_participant
    logger.info(f"Participant connected: {participant.identity}")
    room=ctx.room
    

    @agent.on("user_speech_committed")
    def handle_user_speech(msg: llm.ChatMessage):
      """Handle user speech events."""
      logger.info(f"User speech received: {msg.content}")
    # Schedule the async function as a task
      logger.info(f"User speech received: {msg.content}")
      phone_number = agent.validate_phone_number(msg.content)

      if phone_number:
          asyncio.create_task(process_user_speech(phone_number))
       
    async def process_user_speech(phone_number: str):
        """Handle user speech events."""
        if phone_number:
            
            await local_participant.set_attributes({"phone_number": phone_number})
            await agent.say("Thank you. Please hold while I connect your call.")
        else:
            await agent.say("I couldn't detect a valid phone number. Please repeat.")
    
    @room.on("participant_attributes_changed")
    def on_attributes_changed(
     changed_attributes: dict[str, str], participant: rtc.Participant):
     logging.info(
        "participant attributes changed: %s %s",
        participant.attributes,
        changed_attributes,
    )
     try:
      phone_number = changed_attributes["phone_number"]
      result = asyncio.create_task( agent.handle_call_transfer(phone_number))
      print(result)
     except Exception: 
         print("error")
        
     
    @agent.on("agent_speech_committed")
    def handle_agent_speech(msg: llm.ChatMessage):
      logger.info(f"User speech received: {msg.content}")
    # Schedule the async function as a task
     # customer_number =  self.queue.get()
      customer_number = agent.validate_phone_number(msg.content)

      if customer_number:
        asyncio.create_task(handle_agent_speechas(customer_number))
    
    
    async def handle_agent_speechas(customer_number:str):
        """Handle agent speech events."""
        phone_number =""# attributes.get("phone_number",None)
        try:
            print("**********************"+phone_number)
            
            print("**********************"+customer_number)
            result = await agent.handle_call_transfer(customer_number)
            await agent.say(result)
        except asyncio.QueueEmpty:
            logger.warning("Queue is empty; no phone number available.")
            await agent.say("I couldn't find a phone number. Please try again.")
 
    agent.start(ctx.room, participant)
    await agent.say("Hello! How can I assist you today?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
