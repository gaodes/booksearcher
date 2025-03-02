import os
import yaml
from typing import Dict, Any
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

class Config:
    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize the configuration handler."""
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        
    def load_or_create_config(self) -> Dict[str, Any]:
        """Load existing config or create new one from env vars or defaults."""
        if os.path.exists(self.config_path):
            return self._load_config()
        return self._create_config_from_env()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            return self._convert_config_to_settings(self.config)
        except Exception as e:
            print(f"Warning: Failed to load config file: {str(e)}")
            return self._create_config_from_env()
    
    def _create_config_from_env(self) -> Dict[str, Any]:
        """Create configuration from environment variables or defaults."""
        # Ensure config directory exists
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        # Get values from environment or use defaults
        config = {
            'prowlarr': {
                'url': os.getenv('PROWLARR_URL', 'http://localhost:9696'),
                'api_key': os.getenv('API_KEY', ''),
            },
            'cache': {
                'max_age': int(os.getenv('CACHE_MAX_AGE', '168')),  # 7 days in hours
                'max_size': int(os.getenv('CACHE_MAX_SIZE', '100')),  # Size in MB
                'max_entries': int(os.getenv('CACHE_MAX_ENTRIES', '100')),
            },
            'search': {
                'default_protocol': os.getenv('DEFAULT_PROTOCOL', 'both'),
                'default_media_type': os.getenv('DEFAULT_MEDIA_TYPE', 'both'),
            }
        }
        
        # Save the configuration
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
            self.config = config
        except Exception as e:
            print(f"Warning: Failed to save config file: {str(e)}")
        
        return self._convert_config_to_settings(config)
    
    def _convert_config_to_settings(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert the YAML config structure to the settings format."""
        return {
            "PROWLARR_URL": config['prowlarr']['url'],
            "API_KEY": config['prowlarr']['api_key'],
            "CACHE_MAX_AGE": config['cache']['max_age'] * 3600,  # Convert hours to seconds
            "CACHE_MAX_SIZE": config['cache']['max_size'] * 1024 * 1024,  # Convert MB to bytes
            "CACHE_MAX_ENTRIES": config['cache']['max_entries'],
            "TEST_MODE": config.get('test', {}).get('enabled', False)
        }
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update configuration with new values and save to file."""
        self.config.update(updates)
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise Exception(f"Error updating config file: {str(e)}")

# Create the configuration instance
config = Config()

# Load settings
settings = config.load_or_create_config()

if __name__ == "__main__":
    print("Settings loaded successfully:")
    for key, value in settings.items():
        if key == "CACHE_MAX_SIZE":
            print(f"{key}: {value/1024/1024:.1f}MB")
        elif key == "CACHE_MAX_AGE":
            print(f"{key}: {value/3600:.1f} hours")
        else:
            print(f"{key}: {value}")
