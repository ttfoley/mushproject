from collections import defaultdict
import json
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

sensor_names = ["sht_0","dht_0","scd_0"]
sensor_topic_names = {"sht_0":"sht","dht_0":"dht","scd_0":"scd"}## Bad, need to change this on controller1
sensor_parent_addr = {"sht_0":"mush/controller1/", "dht_0":"mush/controller1/", "scd_0":"mush/controller1/"}
sensor_readings = {"sht_0":["temperature","humidity"],"dht_0":["temperature","humidity"],"scd_0":["temperature","humidity","co2"]}
valid_sensor_ranges = {"temperature":[0,100],"humidity":[0,100],"co2":[0,10000]}

sensors = defaultdict(dict)
UUID = 0
for sensor_name in sensor_names:
    for sensor_type in sensor_readings[sensor_name]:
        d = defaultdict()
        d["read_addr"] = f"{sensor_parent_addr[sensor_name]}{sensor_topic_names[sensor_name]}/{sensor_type}"
        d["valid_range"] = valid_sensor_ranges[sensor_type]
        d["UUID"] = UUID
        UUID += 1
        sensors[sensor_type][sensor_name] = d
#const char* scd_temperature_topic = "mush/controller1/scd/temperature";


cp_write_valid_values = ["On","Off"]
cp_read_valid_values = ["Unknown","On","Off"]
cp_pins = {"C2":[25,26,32,33]}## Trying to accound for future controllers in the future.
cp_pin_description = {"C2":{25:"Humidifier",26:"HeatingPad",32:"Light",33:"VentFan"}}
parent_addrs = {"C2":"mush/controller2/"}
control_points = defaultdict(dict)
for controller in cp_pins.keys():
    for pin in cp_pins[controller]:
        cp_name = f"CP_{controller}_{pin}"
        d = defaultdict(dict)
        d["readback"]["addr"] = f"{parent_addrs[controller]}readback/pin{pin}"
        d["write"]["addr"] = f"{parent_addrs[controller]}control/pin{pin}"
        d["readback"]["UUID"] = UUID
        UUID += 1
        d["write"]["UUID"] = UUID
        UUID += 1
        d["write"]["valid_values"] = cp_write_valid_values
        d["readback"]["valid_values"] = cp_read_valid_values
        control_points[cp_name] = d

all_physical_points = {"sensors":sensors,"control_points":control_points}
with open(config_path+"/physical_points.json","w") as f:
    json.dump(all_physical_points,f,indent=4)