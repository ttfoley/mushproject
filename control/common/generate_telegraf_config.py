import json
import os
import sys
from pathlib import Path
from utils import find_project_root
import toml
from io import StringIO

def validate_toml(config_str: str) -> bool:
    """Validate TOML syntax"""
    try:
        toml.loads(config_str)
        return True
    except toml.TomlDecodeError as e:
        print(f"Invalid TOML: {e}")
        return False

def generate_mqtt_state_config(config_path: str, driver_name: str) -> str:
    """Generate Telegraf MQTT config for a specific driver's state monitoring"""
    
    with open(config_path) as f:
        full_config = json.load(f)

    # Get all possible states
    states = list(full_config['states'].keys())
    states.append('unknown')  # Add unknown state

    # Create state mapping
    state_mapping = {
        state: str(i) for i, state in enumerate(states)
    }

    # Load credentials from environment or secrets file
    mqtt_user = os.getenv('MQTT_USER', 'ttfoley')
    mqtt_pass = os.getenv('MQTT_PASS', 'password')

    # Generate Telegraf config
    config = f"""
# {driver_name} Driver State Monitoring
[[inputs.mqtt_consumer]]
  ## Unique name for this consumer
  name_suffix = "_{driver_name}_states"
  
  servers = ["tcp://localhost:1883"]
  username = "ttfoley"  
  password = "password"
  
  ## Only subscribe to this specific driver's state topics
  topics = [
    "mush/drivers/{driver_name}/status/state",
    "mush/drivers/{driver_name}/status/state_time"
  ]

  data_format = "value"
  data_type = "string"

  # Map state strings to numeric values for Grafana
  [inputs.mqtt_consumer.string_fields.state]
{chr(10).join(f'    "{state}" = "{num}"' for state, num in state_mapping.items())}

  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "mush/drivers/{driver_name}/status/+"
    measurement = "{driver_name}_state"
    [inputs.mqtt_consumer.topic_parsing.tags]
    metric = "_1"  # captures state or state_time
"""
    
    # Validate before returning
    if not validate_toml(config):
        raise ValueError("Generated invalid TOML config")
        
    return config


if __name__ == "__main__":
    if len(sys.argv) > 1:
        driver_path = Path(sys.argv[1])
    else:
        common_dir = Path(__file__).parent
        driver_path = common_dir.parent / "temperature_driver"
    
    driver_name = driver_path.name.replace("_control", "").replace("_driver", "")
    config_path = driver_path / "config" / "full_config.json"
    
    # Get project root
    project_root = find_project_root()

    # Build output path
    telegraf_output_path = project_root / "docker" / "config" / "telegraf" / "telegraf.d" / f"{driver_name}_states.conf"
    
    # Generate and write config
    config = generate_mqtt_state_config(str(config_path), driver_name)
    
    # Create directory if it doesn't exist
    os.makedirs(telegraf_output_path.parent, exist_ok=True)
    
    # Write config
    with open(telegraf_output_path, 'w') as f:
        f.write(config)
    
    print(f"Generated Telegraf config for {driver_name} driver")
    print(f"Written to: {telegraf_output_path}") 