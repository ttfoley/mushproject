from collections import defaultdict
import json
import os
from pathlib import Path
from uuid_database import UUIDDatabase
from point_address import PointAddress

current_dir = os.path.dirname(os.path.abspath(__file__))
uuid_db = UUIDDatabase()

"""
Should be able to construct much more systematically with the new naming conventions.
a given sensor value will have :/mush/controllers/controller_name/sensors/sensor_name/value_name
and control_point will have :/mush/controllers/controller_name/control_points/CP_name/(reaback,write)
"""
sensor_config = {"C1":{"sht_0":["temperature","humidity"],"dht_0":["temperature","humidity"],"scd_0":["temperature","humidity","co2"]}}
sensor_config.update({"C2":{"status":["wifi_uptime"]}})
CP_config = {"C2":{"CP_25":"Humidifier","CP_26":"HeatingPad","CP_32":"Light","CP_33":"VentFan","led1":"Status_LED"}}
controllers = list(set(sensor_config.keys()).union(CP_config.keys()))
#uptime is in minutes,temperature is fahrenheit, humidity is percentage, co2 is ppm
valid_sensor_ranges = {"temperature":[0,100],"humidity":[0,100],"co2":[0,10000],"wifi_uptime":[0,1000000]}
#This is a departure from the previous naming for cp vlaues. I think it will be more flexible in the long run.
cp_read_valid_values =  ["unknown","on","off"]
cp_write_valid_values = ["on","off"]

points = {"microcontrollers":{}}

for controller in controllers:
    points["microcontrollers"][controller] = defaultdict(dict)
    p_C = points["microcontrollers"][controller]
    if controller not in sensor_config:
        continue
    else:
        p_C_S = p_C["sensors"] = defaultdict(dict)
        for sensor_name, sensor_types in sensor_config[controller].items():
            p_C_S[sensor_name] = defaultdict(dict)
            for sensor_type in sensor_types:
                addr = PointAddress.make_sensor_address(controller, sensor_name, sensor_type)
                d = {}
                d["addr"] = addr
                d["valid_range"] = {}
                d["valid_range"]["lower"],d["valid_range"]["upper"] = valid_sensor_ranges[sensor_type]
                d["UUID"] = uuid_db.get_uuid(addr)
                p_C_S[sensor_name][sensor_type] = d

    if controller not in CP_config:
        continue
    else:
        p_C_CP = p_C["control_points"] = defaultdict(dict)
        for cp_name, cp_desc in CP_config[controller].items():
            d = {}
            d["description"] = cp_desc
            d["readback"] = {}
            d["write"] = {}
            
            rb_addr = PointAddress.make_control_point_address(controller, cp_name, "readback")
            wr_addr = PointAddress.make_control_point_address(controller, cp_name, "write")
            
            d["readback"]["addr"] = rb_addr
            d["write"]["addr"] = wr_addr
            d["readback"]["UUID"] = uuid_db.get_uuid(rb_addr)
            d["write"]["UUID"] = uuid_db.get_uuid(wr_addr)
            d["write"]["valid_values"] = cp_write_valid_values
            d["write"]["value_type"] = "str"
            d["write"]["raw_value_type"] = ("str","str")
            d["readback"]["value_type"] = "str"
            d["readback"]["raw_value_type"] = ("str","int")
            d["readback"]["value_mapper"] = {"-1":"off","1":"on","0":"unknown"}
            d["readback"]["valid_values"] = cp_read_valid_values
            p_C_CP[cp_name] = d

# Save the config
with open(os.path.join(current_dir, "microC_points.json"), 'w') as f:
    json.dump(points, f, indent=4)