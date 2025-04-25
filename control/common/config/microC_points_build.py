# control/common/config/microC_points_build.py

from collections import defaultdict
import json
import os
from pathlib import Path
# Assuming these are in the same directory or accessible via PYTHONPATH
from uuid_database import UUIDDatabase
from point_address import PointAddress

current_dir = os.path.dirname(os.path.abspath(__file__))
# Make sure uuid_db.json is found relative to this script
uuid_db = UUIDDatabase(db_path=os.path.join(current_dir, "uuid_db.json"))

"""
Generates the microC_points.json configuration file.
"""
sensor_config = {"C1":{"sht_0":["temperature","humidity"],"dht_0":["temperature","humidity"],"scd_0":["temperature","humidity","co2"]}}
sensor_config.update({"C2":{"status":["wifi_uptime"]}})
CP_config = {"C2":{"CP_25":"Humidifier","CP_26":"HeatingPad","CP_32":"Light","CP_33":"VentFan","led1":"Status_LED"}}
controllers = list(set(sensor_config.keys()).union(CP_config.keys()))
#uptime is in minutes,temperature is fahrenheit, humidity is percentage, co2 is ppm
valid_sensor_ranges = {"temperature":[0,100],"humidity":[0,100],"co2":[0,10000],"wifi_uptime":[0,1000000]}

# Define value types for sensors (assuming all these are continuous)
sensor_value_types = {
    "temperature": "continuous",
    "humidity": "continuous",
    "co2": "continuous",
    "wifi_uptime": "continuous"
}

cp_read_valid_values =  ["unknown","on","off"]
cp_write_valid_values = ["on","off"]

points = {"microcontrollers":{}}

for controller in controllers:
    points["microcontrollers"][controller] = defaultdict(dict)
    p_C = points["microcontrollers"][controller]

    # Process Sensors
    if controller in sensor_config:
        p_C_S = p_C["sensors"] = defaultdict(dict)
        for sensor_name, sensor_types in sensor_config[controller].items():
            p_C_S[sensor_name] = defaultdict(dict)
            for sensor_type in sensor_types:
                addr = PointAddress.make_sensor_address(controller, sensor_name, sensor_type)
                d = {}
                d["addr"] = addr
                # *** ADDED VALUE TYPE HERE ***
                d["value_type"] = sensor_value_types.get(sensor_type, "continuous") # Default to continuous if type unknown
                d["valid_range"] = {}
                d["valid_range"]["lower"],d["valid_range"]["upper"] = valid_sensor_ranges[sensor_type]
                d["UUID"] = uuid_db.get_uuid(addr)
                p_C_S[sensor_name][sensor_type] = d

    # Process Control Points
    if controller in CP_config:
        p_C_CP = p_C["control_points"] = defaultdict(dict)
        for cp_name, cp_desc in CP_config[controller].items():
            d = {}
            d["description"] = cp_desc
            d["readback"] = {}
            d["write"] = {}

            rb_addr = PointAddress.make_control_point_address(controller, cp_name, "readback")
            wr_addr = PointAddress.make_control_point_address(controller, cp_name, "write")

            # Readback point config
            d["readback"]["addr"] = rb_addr
            d["readback"]["UUID"] = uuid_db.get_uuid(rb_addr)
            # Control point readbacks are typically discrete states
            d["readback"]["value_type"] = "discrete" # Assuming discrete based on valid_values
            d["readback"]["raw_value_type"] = ("str","int") # Example raw types
            d["readback"]["value_mapper"] = {"-1":"off","1":"on","0":"unknown"}
            d["readback"]["valid_values"] = cp_read_valid_values

            # Write point config
            d["write"]["addr"] = wr_addr
            d["write"]["UUID"] = uuid_db.get_uuid(wr_addr)
            # Control point writes are typically discrete commands
            d["write"]["value_type"] = "discrete" # Assuming discrete based on valid_values
            d["write"]["raw_value_type"] = ("str","str") # Example raw types
            d["write"]["valid_values"] = cp_write_valid_values

            p_C_CP[cp_name] = d

# Define the output path relative to the script directory
output_path = os.path.join(current_dir, "microC_points.json")

# Save the config
print(f"Saving generated config to: {output_path}")
with open(output_path, 'w') as f:
    json.dump(points, f, indent=4)

print("Finished generating microC_points.json")