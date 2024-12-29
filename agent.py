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
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("voice_business_agent.log", mode='a')
    ]
)
logger = logging.getLogger("voice-business-agent")

# Load environment variables
load_dotenv(dotenv_path=".env.local")

# Fixed agent number
AGENT_NUMBER = "9650101554"
queue = asyncio.Queue()

class BusinessVoiceAgent(VoicePipelineAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.awaiting_phone_number = False
        
        
    async def on_event(self, event: str, *args, **kwargs):
        """Handle events triggered in the voice agent."""
        logger.info(f"Received event: {event}")

        if event == "user_stopped_speaking":
            logger.info("Handling 'user_stopped_speaking' event.")
            await self.handle_user_stopped_speaking()

    
    def validate_phone_number(self, text: str) -> Optional[str]:
        """Extract and validate Indian phone number from text."""
        logger.debug(f"Validating phone number from text: {text}")
        cleaned_text = ''.join(char for char in text if char.isdigit())
        logger.debug(f"Cleaned text (digits only): {cleaned_text}")
        
        pattern = r'[6-9]\d{9}'
        matches = re.findall(pattern, cleaned_text)
        
        if matches:
            valid_number = matches[0]
            logger.info(f"Valid phone number found: {valid_number}")
            return valid_number
        
        logger.info("No valid phone number found in text")
        return None

    async def handle_call_transfer(self, customer_number: str) -> str:
        """Handle call transfer with detailed logging."""
        try:
            logger.info(f"Attempting to transfer call to customer number: {customer_number}")
            api_endpoint = "https://c2c.ivrobd.com/api/c2c/process"
            
            payload = {
                "secretKey": os.getenv("C2C_SECRET_KEY"),
                "clientId": os.getenv("C2C_CLIENT_ID"),
                "agentNumber": AGENT_NUMBER,
                "customerNumber": customer_number
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            response = requests.post(api_endpoint, json=payload, headers=headers, timeout=30)
            logger.info(f"Response status: {response.status_code}, Content: {response.text}")

            if response.status_code == 200:
                return "Call transfer initiated. You'll receive a call shortly."
            else:
                raise Exception(f"API call failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Error during call transfer: {str(e)}", exc_info=True)
            return "I'm having trouble connecting the call. Please try again later."
    #@VoicePipelineAgent.on("user_user_stopped_speaking")
    async def  on_user_stopped_speaking(self):
    #async def  on_transcript(self, text: str):
        """Handle incoming transcribed text."""
        text=self.self.get_last_transcript()
        logger.info(f"Received transcript: {text}")

        if self.awaiting_phone_number:
            phone_number ="9313571554"## self.validate_phone_number(text)
            if (9==9):
                self.awaiting_phone_number = False
                response = await self.handle_call_transfer(phone_number)
                await self.say(response)
            else:
                await self.say("Please provide a valid 10-digit mobile number.")
            return

        if any(word in text.lower() for word in ["transfer", "connect", "agent", "human"]):
            self.awaiting_phone_number = True
            await self.say("Please provide your 10-digit mobile number to connect you.")
            return

        await self.say("Would you like me to connect you with our agent?")
        self.awaiting_phone_number = True

def prewarm(proc: JobProcess):
    """Prewarm function to load resources."""
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("VAD model loaded successfully during prewarm.")

async def entrypoint(ctx: JobContext):
    """Entrypoint for the voice assistant agent."""
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a helpful voice assistant. Your primary task is to connect callers with agents. "
            "Ask for their mobile number to proceed with the connection.remove special character or space from mobile number."
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
        print("*************************************************"+msg.content)
        url = "https://fonada.app.n8n.cloud/webhook/ba54b728-8f66-4ae6-9a28-9a06ea5f159b"

        payload = json.dumps({
         "data": msg.content,
          "session_id": "677777777"
         })
        headers = {
        'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=payload)

        asyncio.create_task( agent.say(response.text))
        text=msg.content
        #self.customer_number=self.validate_phone_number(msg.content)
        cleaned_text = ''.join(char for char in text if char.isdigit())
        logger.debug(f"Cleaned text (digits only): {cleaned_text}")
        
        pattern = r'[6-9]\d{9}'
        matches = re.findall(pattern, cleaned_text)
        
        if matches:
            valid_number = matches[0]
            logger.info(f"Valid phone number found: {valid_number}")
            customer_number= valid_number
            queue.put(customer_number)
        print(customer_number)
    
    @agent.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        # convert string lists to strings, drop images
        try:
            customer_number= queue.get_nowait()
         #print("*************************************************"+customer_number)
       
            print("*************************************************"+msg.content)
            """Handle incoming transcribed text."""
        #text="9313571554"
        #logger.info(f"Received transcript: {text}")

        
        ##customer_number ="9313571554"## self.validate_phone_number(text)
        
            logger.info(f"Attempting to transfer call to customer number: {customer_number}")
            api_endpoint = "https://c2c.ivrobd.com/api/c2c/process"
            
            payload = {
                "secretKey": os.getenv("C2C_SECRET_KEY"),
                "clientId": os.getenv("C2C_CLIENT_ID"),
                "agentNumber": AGENT_NUMBER,
                "customerNumber": customer_number
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            if("an agent" in msg.content):
               response = requests.post(api_endpoint, json=payload, headers=headers, timeout=30,verify=False)
               logger.info(f"Response status: {response.status_code}, Content: {response.text}")
               print(response)
               if response.status_code == 200:
                return "Call transfer initiated. You'll receive a call shortly."
               else:
                raise Exception(f"API call failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Error during call transfer: {str(e)}", exc_info=True)
            return "I'm having trouble connecting the call. Please try again later."
            #print(response)
        if isinstance(msg.content, list):
            msg.content = "\n".join(
                "[image]" if isinstance(x, llm.ChatImage) else x for x in msg
            )
        log_queue.put_nowait(f"[{datetime.now()}] USER:\n{msg.content}\n\n")

    agent.start(ctx.room, participant)
    ##await agent.on_transcript("9313571554")
    await agent.say("Hello! How can I assist you today?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            
        )
    )
