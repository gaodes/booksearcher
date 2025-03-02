import os
import yaml
from typing import Dict, Any
from pathlib import Path

class TestConfig:
    def __init__(self, config_path: str = "config/test_config.yaml"):
        """Initialize the test configuration handler."""
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        
    def load_or_create_config(self) -> Dict[str, Any]:
        """Load existing config or create new one from environment variables."""
        if os.path.exists(self.config_path):
            return self._load_config()
        return self._create_default_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            return self.config
        except Exception as e:
            raise Exception(f"Error loading config file: {str(e)}")
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default configuration with test values."""
        # Ensure config directory exists
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        # Create default config with test values
        default_config = {
            'prowlarr': {
                'url': 'http://localhost:9696',  # Default test URL
                'api_key': 'test_api_key_123',  # Default test API key
            },
            'cache': {
                'max_age': 1,  # 1 hour for testing
                'max_size': 10,  # 10MB for testing
                'max_entries': 10,  # Fewer entries for testing
            },
            'search': {
                'default_protocol': 'both',
                'default_media_type': 'both',
            },
            'test': {
                'enabled': True,  # Enable test mode by default
                'mock_responses': True,  # Enable mock responses by default
            }
        }
        
        # Save the default configuration
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(default_config, f, default_flow_style=False, sort_keys=False)
            self.config = default_config
            return default_config
        except Exception as e:
            raise Exception(f"Error creating default config file: {str(e)}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        try:
            keys = key.split('.')
            value = self.config
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update configuration with new values and save to file."""
        self.config.update(updates)
        try:
            with open(self.config_path, 'w') as f:
                yaml.safe_dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise Exception(f"Error updating config file: {str(e)}")

# Create a singleton instance
test_config = TestConfig() 