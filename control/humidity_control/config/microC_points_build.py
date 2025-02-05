from collections import defaultdict
import json
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

"""
Should be able to construct much more systematically with the new naming conventions.
a given sensor value will have :/mush/controllers/controller_name/sensors/sensor_name/value_name
and control_point will have :/mush/controllers/controller_name/control_points/CP_name/(reaback,write)
"""
parent_addrs = {"C1":"mush/controllers/C1/","C2":"mush/controllers/C2/"}
sensor_config = {"C1":{"sht_0":["temperature","humidity"],"dht_0":["temperature","humidity"],"scd_0":["temperature","humidity","co2"]}}
sensor_config.update({"C2":{"status":["wifi_uptime"]}})
CP_config = {"C2":{"CP_25":"Humidifier","CP_26":"HeatingPad","CP_32":"Light","CP_33":"VentFan","led1":"Status_LED"}}
controllers = list(set(parent_addrs.keys()).union(sensor_config.keys(), CP_config.keys()))
#uptime is in minutes,temperature is fahrenheit, humidity is percentage, co2 is ppm
valid_sensor_ranges = {"temperature":[0,100],"humidity":[0,100],"co2":[0,10000],"wifi_uptime":[0,1000000]}
#This is a departure from the previous naming for cp vlaues. I think it will be more flexible in the long run.
cp_read_valid_values =  ["unknown","on","off"]
cp_write_valid_values = ["on","off"]

sensors_config = defaultdict(dict)
UUID = 0
def get_next_UUID():
    global UUID
    current_uuid = UUID
    UUID += 1
    return current_uuid
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
                d = {}
                d["addr"] = f"{parent_addrs[controller]}sensors/{sensor_name}/{sensor_type}"
                d["valid_range"] = {}
                d["valid_range"]["lower"],d["valid_range"]["upper"] = valid_sensor_ranges[sensor_type]
                d["UUID"] = get_next_UUID()
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
            d["readback"]["addr"] = f"{parent_addrs[controller]}control_points/{cp_name}/readback"
            d["write"]["addr"] = f"{parent_addrs[controller]}control_points/{cp_name}/write"
            d["readback"]["UUID"] = get_next_UUID()
            d["write"]["UUID"] = get_next_UUID()
            d["write"]["valid_values"] = cp_write_valid_values
            d["write"]["value_type"] = "str"
            d["write"]["raw_value_type"] = ("str","str")
            d["readback"]["value_type"] = "str"
            d["readback"]["raw_value_type"] = ("str","int")
            d["readback"]["value_mapper"] = {"-1":"off","1":"on","0":"unknown"}
            d["readback"]["valid_values"] = cp_read_valid_values
            p_C_CP[cp_name] = d



with open(config_path+"/microC_points.json","w") as f:
    json.dump(points,f,indent=4)