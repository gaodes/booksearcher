import os
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_settings() -> Dict[str, Any]:
    """
    Load settings from environment variables.
    Raises EnvironmentError if required variables are not set.
    """
    required_vars = ["PROWLARR_URL", "API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise EnvironmentError(
            f"Required environment variables not set: {', '.join(missing_vars)}\n"
            "Please check your .env file."
        )

    try:
        cache_max_age = int(os.getenv("CACHE_MAX_AGE", "604800").split('#')[0].strip())
    except ValueError as e:
        raise ValueError(
            f"CACHE_MAX_AGE must be a valid integer. Error: {str(e)}"
        )

    return {
        "PROWLARR_URL": os.getenv("PROWLARR_URL"),
        "API_KEY": os.getenv("API_KEY"),
        "CACHE_MAX_AGE": cache_max_age  # 7 days in seconds default
    }

settings = load_settings()

if __name__ == "__main__":
    print("Settings loaded successfully:")
    for key, value in settings.items():
        print(f"{key}: {value}")
