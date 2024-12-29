import logging
from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain_community.tools import PineconeTool
from pyairtable import Table
import os

# Load environment variables
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

# Configuration
os.environ["OPENAI_API_KEY"] = "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"
AIRTABLE_API_KEY = "patv8wqy7DYxTv07F.35d34761c43c81cbff8e2d403e3287ab8a0e75c19c13bde16df08bd21c608862"
AIRTABLE_BASE_ID = "https://api.airtable.com/v0/test_langchain/"

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

def handle_booking_test(user_input, airtable_registered_users, airtable_price_list):
    """Handles the booking of a test."""
    name = user_input.get("name")
    mobile_number = user_input.get("mobile_number")

    # Check if mobile number exists in registered users
    user_exists = airtable_registered_users.first(formula=f"{{mobile_number}}='{mobile_number}'")

    if user_exists:
        last_test = user_exists["fields"].get("last_test")
        response = f"Would you like to repeat the same test ({last_test}) or book a new one?"
        return response

    # For new bookings or booking a different test
    test_name = user_input.get("test_name")
    test_details = airtable_price_list.first(formula=f"{{test_name}}='{test_name}'")

    if test_details:
        price = test_details["fields"].get("price")
        response = f"The test {test_name} is available for INR {price}. Would you like to book it for a morning or evening slot?"
        return response
    else:
        return "We don’t have this test available for sample collection. Would you like to book any other test?"

def handle_retrieving_report(user_input, airtable_registered_users, airtable_reports):
    """Handles retrieving a test report."""
    mobile_number = user_input.get("mobile_number")
    user_record = airtable_registered_users.first(formula=f"{{mobile_number}}='{mobile_number}'")

    if user_record:
        name = user_record["fields"].get("name")
        report = airtable_reports.first(formula=f"{{mobile_number}}='{mobile_number}'")
        if report:
            link = report["fields"].get("link")
            return f"Hi {name}, I’ve found your test report. Sending the link details: {link} to your mobile number {mobile_number}."
        else:
            return "I couldn’t find a report associated with your number. Can I help you with anything else?"
    else:
        return "I couldn’t find any records for this number. Can I help you with anything else?"

def handle_general_query(query, wikipedia_tool, pinecone_tool):
    """Handles general queries."""
    try:
        # Search using Wikipedia or Pinecone
        wikipedia_response = wikipedia_tool.search(query)
        if wikipedia_response:
            return wikipedia_response

        pinecone_response = pinecone_tool.search(query)
        if pinecone_response:
            return pinecone_response

    except Exception:
        pass

    return "I’m sorry, I couldn’t find the information you were looking for. Is there anything else I can help you with?"

def connect_to_human(user_input):
    """Connects the user to a human representative."""
    mobile_number = user_input.get("mobile_number")
    if mobile_number:
        return f"Please wait, I am initiating a voice call between you and our Customer Sales Representative at {mobile_number}."
    else:
        return "Please provide your mobile number to connect with our Customer Sales Representative."

async def entrypoint(ctx: JobContext):
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a voice assistant created by LiveKit. Your interface with users will be voice. "
            "You should use short and concise responses, and avoiding usage of unpronouncable punctuation. "
            "You were created as a demo to showcase the capabilities of LiveKit's agents framework."
        ),
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    # Initialize LangChain tools
    memory = ConversationBufferMemory()
    llm = ChatOpenAI(temperature=0.7)
    conversation = ConversationChain(llm=llm, memory=memory)
    airtable_registered_users = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, "registered_users")
    airtable_price_list = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, "price_list")
    airtable_reports = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, "test_reports")
    wikipedia_tool = WikipediaTool()
    pinecone_tool = PineconeTool()

    # Initialize LiveKit VoicePipelineAgent
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(),
        chat_ctx=initial_ctx,
    )

    agent.start(ctx.room, participant)

    # The agent should greet the user
    await agent.say("Hey, how can I help you today?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
