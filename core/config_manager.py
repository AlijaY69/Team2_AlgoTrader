# file: core/config_manager.py
import json
from pathlib import Path

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.config = self._load_config()

    def _load_config(self):
        """Loads configuration from the JSON file."""
        try:
            with open(self.config_path, 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found at {self.config_path}")
        except json.JSONDecodeError:
            raise ValueError(f"Error decoding the JSON configuration file at {self.config_path}")

    def save_config(self):
        """Saves the current config to the JSON file."""
        try:
            with open(self.config_path, 'w') as file:
                json.dump(self.config, file, indent=4)
        except IOError as e:
            raise IOError(f"Error saving configuration file: {str(e)}")

    def get(self, key, default=None):
        """Returns the value of a configuration key or default."""
        return self.config.get(key, default)

    def set(self, key, value):
        """Sets a key-value pair in the configuration."""
        self.config[key] = value
        self.save_config()

    def update(self, updates):
        """Updates multiple configuration fields at once."""
        self.config.update(updates)
        self.save_config()
