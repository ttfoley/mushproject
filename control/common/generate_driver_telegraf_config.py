import json
import sys
from pathlib import Path
from typing import Dict, Any
from .utils import find_project_root

def generate_driver_telegraf_config(driver_dir: Path) -> str:
    """Generate minimal telegraf config for driver state monitoring"""
    # Load driver config
    config_path = driver_dir / "config" / "full_config.json"
    with open(config_path) as f:
        config = json.load(f)

    driver_name = config["settings"]["driver"]["name"]
    mqtt_config = config["settings"]["mqtt"]
    state_point = config["points"]["drivers"][driver_name]["status"]["state"]
    state_addr = state_point["addr"]

    # Generate TOML config
    config_lines = [
        f'# Telegraf Configuration for {driver_name}',
        '',
        '[[inputs.mqtt_consumer]]',
        f'  servers = ["tcp://{mqtt_config["broker"]}:{mqtt_config["port"]}"]',
        f'  username = "{mqtt_config["username"]}"',
        f'  password = "{mqtt_config["password"]}"',
        '  topics = [',
        f'    "{state_addr}"',
        '  ]',
        '  data_format = "value"',
        '  data_type = "integer"',
        '',
        '  [inputs.mqtt_consumer.value_mapping]',
        '    off = 0',
        '    on = 1', 
        '    unknown = 2'
    ]

    return '\n'.join(config_lines)

def write_driver_telegraf_config(driver_dir: str):
    """
    Generate telegraf config for a specific driver directory
    Args:
        driver_dir: Name of driver directory (e.g. 'temperature_driver')
    """
    project_root = find_project_root()
    driver_path = project_root / "control" / driver_dir
    telegraf_d_dir = project_root / "docker" / "config" / "telegraf" / "telegraf.d"
    
    # Validate driver directory
    if not driver_path.exists():
        print(f"Error: Driver directory {driver_path} does not exist")
        sys.exit(1)
    if not (driver_path / "config" / "full_config.json").exists():
        print(f"Error: No full_config.json found in {driver_path}/config")
        sys.exit(1)

    # Create telegraf.d if it doesn't exist
    telegraf_d_dir.mkdir(parents=True, exist_ok=True)

    # Generate and write config
    config_content = generate_driver_telegraf_config(driver_path)
    driver_name = json.loads((driver_path / "config" / "full_config.json").read_text())["settings"]["driver"]["name"]
    config_file = telegraf_d_dir / f"{driver_name}.conf"
    config_file.write_text(config_content)
    print(f"Generated telegraf config for {driver_name}")

def main():
    """Main entry point with proper error handling"""
    try:
        if len(sys.argv) != 2:
            print("Usage: python -m control.common.generate_driver_telegraf_config <driver_directory>")
            print("Example: python -m control.common.generate_driver_telegraf_config temperature_driver")
            sys.exit(1)
        
        write_driver_telegraf_config(sys.argv[1])
        
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 