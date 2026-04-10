from pathlib import Path
from dotenv import load_dotenv


def load_local_env():
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env", override=False)
