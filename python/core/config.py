import os
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_settings() -> Dict[str, Any]:
    """Load settings from environment variables"""
    return {
        "PROWLARR_URL": os.getenv("PROWLARR_URL", "https://prowlarr.homelab.rip"),
        "API_KEY": os.getenv("API_KEY", "446137b137124aeb895da6c31afe4f10"),
        "CACHE_MAX_AGE": int(os.getenv("CACHE_MAX_AGE", "604800"))
    }

settings = load_settings()

if __name__ == "__main__":
    print("Settings loaded successfully:")
    for key, value in settings.items():
        print(f"{key}: {value}")
