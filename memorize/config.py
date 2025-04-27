import os
import yaml


def load_config():
    """Load configuration from config.yaml or return defaults."""
    default_config = {
        "reviews": {"daily_limit": 20, "count": 20},
        "speech": {"engine": "vosk"},
    }
    
    # Check for config file
    if os.path.exists("config.yaml"):
        try:
            with open("config.yaml", "r") as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    # Merge with defaults to ensure all expected keys exist
                    if "reviews" in user_config:
                        default_config["reviews"].update(user_config.get("reviews", {}))
                    if "speech" in user_config:
                        default_config["speech"].update(user_config.get("speech", {}))
                    # Add any new top-level sections
                    for key, value in user_config.items():
                        if key not in default_config:
                            default_config[key] = value
        except Exception as e:
            print(f"Error loading config.yaml: {e}")
            print("Using default configuration")
    
    # Override with environment variables if present
    if "MEMORIZE_DAILY_LIMIT" in os.environ:
        try:
            default_config["reviews"]["daily_limit"] = int(os.environ["MEMORIZE_DAILY_LIMIT"])
        except ValueError:
            pass
    
    if "MEMORIZE_SPEECH_ENGINE" in os.environ:
        default_config["speech"]["engine"] = os.environ["MEMORIZE_SPEECH_ENGINE"]
    
    return default_config


def save_config(config):
    """Save configuration to config.yaml."""
    try:
        with open("config.yaml", "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        return True
    except Exception as e:
        print(f"Error saving config.yaml: {e}")
        return False