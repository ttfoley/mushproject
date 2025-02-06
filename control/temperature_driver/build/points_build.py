from collections import defaultdict
import json
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(current_dir, '../config')  # This resolves to temperature_driver/config

# Load settings to get driver name
with open(os.path.join(config_dir, "settings.json")) as f:
    settings = json.load(f)
    driver_name = settings["driver"]["name"]

# Load states to get valid state names
with open(os.path.join(config_dir, "states.json")) as f:
    states = json.load(f)
    state_names = list(states.keys()) + ["unknown"]

# Load existing microC points to continue UUID sequence
with open(os.path.join(config_dir, "microC_points.json")) as f:
    microC_points = json.load(f)

# Find max UUID from microC points
max_uuid = -1
for controller in microC_points["microcontrollers"].values():
    for sensor in controller.get("sensors", {}).values():
        for reading in sensor.values():
            max_uuid = max(max_uuid, reading["UUID"])
    for cp in controller.get("control_points", {}).values():
        max_uuid = max(max_uuid, cp["readback"]["UUID"], cp["write"]["UUID"])

UUID = max_uuid + 1
def get_next_UUID():
    global UUID
    current_uuid = UUID
    UUID += 1
    return current_uuid

# Build driver points
points = {
    "drivers": {
        driver_name: {
            "sensors": {
                "status": {
                    "state": {
                        "addr": f"mush/drivers/{driver_name}/sensors/status/state",
                        "UUID": get_next_UUID(),
                        "value_type": "str",
                        "valid_values": state_names
                    },
                    "state_time": {
                        "addr": f"mush/drivers/{driver_name}/sensors/status/state_time",
                        "UUID": get_next_UUID(),
                        "value_type": "float",
                        "valid_range": {"lower": 0, "upper": 1e6}
                    }
                }
            }
        }
    }
}

# Write to config directory
output_path = os.path.join(config_dir, "driver_points.json")
print(f"Attempting to write to: {output_path}")
print(f"Points to write: {json.dumps(points, indent=2)}")

try:
    with open(output_path, "w") as f:
        json.dump(points, f, indent=2)
    print(f"Successfully wrote to {output_path}")
except Exception as e:
    print(f"Failed to write file: {str(e)}")
    raise