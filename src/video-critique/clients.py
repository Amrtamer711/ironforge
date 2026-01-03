from fastapi import FastAPI
from openai import AsyncOpenAI
from config import OPENAI_API_KEY
from logger import logger
from messaging_platform import platform

# Initialize platform (Slack/Teams/etc)
# The platform.client will be initialized on startup
# Access via: platform.client, platform.signature_verifier
slack_client = None  # Will be set on startup via platform.client
signature_verifier = None  # Will be set on startup via platform.signature_verifier

# Initialize FastAPI app
api = FastAPI(title="Design request API", version="2.0")

# Initialize OpenAI client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Validate required environment variables
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY not found in environment variables")
    raise ValueError("OPENAI_API_KEY is required")


async def initialize_platform():
    """Initialize the messaging platform (Slack/Teams/etc)"""
    global slack_client, signature_verifier

    await platform.initialize()

    # For backward compatibility, expose platform client as slack_client
    # This allows existing code to work without changes
    slack_client = platform.client
    signature_verifier = platform.signature_verifier

    logger.info("✅ Platform initialized successfully")
