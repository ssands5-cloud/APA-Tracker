import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Load .env and override any existing environment variables (including Windows-level ones)
load_dotenv(ENV_PATH, override=True)
