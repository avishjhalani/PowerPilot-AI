import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths (Project Root: powerbi-streaming-agent/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CLEANED_DATA_DIR = DATA_DIR / "cleaned"
OUTPUT_DIR = BASE_DIR / "output"
PBIP_OUTPUT_DIR = OUTPUT_DIR / "pbip"
REPORTS_OUTPUT_DIR = OUTPUT_DIR / "reports"

# Ensure all operational directories exist
for p in [RAW_DATA_DIR, CLEANED_DATA_DIR, PBIP_OUTPUT_DIR, REPORTS_OUTPUT_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Default Fast Models
DEFAULT_GROQ_MODEL = os.getenv("MODEL_NAME", "openai/gpt-oss-120b")

# Token-Control Safeguards
MAX_SAMPLE_ROWS_FOR_LLM = 15     # Max upper-bound sample rows for LLM
MAX_SAMPLE_CHARS_FOR_LLM = 4000  # Token-budget safeguard (~1,000 tokens)
MAX_SELF_HEALING_RETRIES = 3     # Max auto-debug loops if code errors out