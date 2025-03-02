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
        # Convert hours to seconds
        cache_max_age = int(os.getenv("CACHE_MAX_AGE", "168").split('#')[0].strip()) * 3600
    except ValueError as e:
        raise ValueError(
            f"CACHE_MAX_AGE must be a valid integer (hours). Error: {str(e)}"
        )

    try:
        # Convert MB to bytes
        cache_max_size = int(os.getenv("CACHE_MAX_SIZE", "100").split('#')[0].strip()) * 1024 * 1024
    except ValueError as e:
        raise ValueError(
            f"CACHE_MAX_SIZE must be a valid integer (MB). Error: {str(e)}"
        )

    try:
        cache_max_entries = int(os.getenv("CACHE_MAX_ENTRIES", "100").split('#')[0].strip())
    except ValueError as e:
        raise ValueError(
            f"CACHE_MAX_ENTRIES must be a valid integer. Error: {str(e)}"
        )

    return {
        "PROWLARR_URL": os.getenv("PROWLARR_URL"),
        "API_KEY": os.getenv("API_KEY"),
        "CACHE_MAX_AGE": cache_max_age,  # Stored in seconds internally
        "CACHE_MAX_SIZE": cache_max_size,  # Stored in bytes internally
        "CACHE_MAX_ENTRIES": cache_max_entries
    }

settings = load_settings()

if __name__ == "__main__":
    print("Settings loaded successfully:")
    for key, value in settings.items():
        if key == "CACHE_MAX_SIZE":
            print(f"{key}: {value/1024/1024:.1f}MB")
        elif key == "CACHE_MAX_AGE":
            print(f"{key}: {value/3600:.1f} hours")
        else:
            print(f"{key}: {value}")
