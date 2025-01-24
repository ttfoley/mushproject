from collections import defaultdict
import sys
import os
import time
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)
from mqtt_handler import MQTTHandler
import json
from datetime import datetime
from points import Remote_Write,Remote_Read, Remote_Sensor
from controller2 import ControlPoint


D = defaultdict(dict)
D["sys"]["control_points"] = defaultdict(dict)
points_config = json.load(open(os.path.join(config_path,"points.json"),'r'))
control_points = points_config["sys"]["control_points"]
control_points_dict = {}
print(control_points)
for cp,entries in control_points.items():
    D["sys"]["control_points"][cp] = {}
    d = defaultdict()
    for value_class,entry in entries.items():
        if value_class == "readback":
            #Probably shouldn't default to 0 for all of these...
            readback_point = Remote_Read(entry["uuid"],0,entry["read_addr"],f"Readback for {cp}",entry["valid_values"])
            d["readback"] = readback_point
        if value_class == "control":
            write_point = Remote_Write(entry["uuid"],"Unknown",entry["write_addr"],f"Write for {cp}",["On","Off"])
            d["write"] = write_point
    D["sys"]["control_points"][cp] = d
    control_points_dict[cp] = ControlPoint(cp,d["write"],d["readback"])
    
D["sys"]["sensors"] = defaultdict(dict)
sensor_points = points_config["sys"]["sensors"]
sensor_points_dict = defaultdict(dict)
for sensor_type,entries in sensor_points.items():
    D["sys"]["sensors"][sensor_type] = {}
    d = defaultdict()
    sensor_points_dict[sensor_type] = {}
    for sensor_name,entry in entries.items():
        #Now we're not using the fact that we have a class attribute, but we could.
        assert entry["class"] == "Remote_Sensor"
        sensor_point = Remote_Sensor(entry["uuid"],0,entry["read_addr"],f"Value for {sensor_name}",lower_bound=entry["lower_bound"],upper_bound=entry["upper_bound"])
        d[sensor_name] = sensor_point
        sensor_points_dict[sensor_type][sensor_name] = sensor_point
    D["sys"]["sensors"][sensor_type] = d


print(D["sys"]["sensors"]["temperature"]["t_sht_0"].value)
# ControlPoints = {"CP25":CP_25}
# SensorPoints = {"temp_1":rs}

# mqqt_dict = {"CP25":CP_25}  
# mqtt_whole = {"Control_Points":ControlPoints,"Sensor_Points":SensorPoints}


# mqtt_uname = "ttfoley"
# mqtt_pwd = "password"
# mqtt_broker = "192.168.1.17"
# mqtt_port = 1883
# mqtt_client_id = "points_test"
# #Shouldn't technically subscribe to the one you're writing to?
# topics = ["mush/controller2/control/pin25","mush/controller2/readback/pin25",temp_1]
# mqtt_handler = MQTTHandler(mqtt_client_id, mqtt_broker, mqtt_port, mqtt_uname, mqtt_pwd,userdata=mqtt_whole)
# mqtt_handler.connect()
# for topic in topics:
#     print(topic)
#     mqtt_handler.client.subscribe(topic)


# mqtt_handler.loop_start()
# while True:
#     CP_25.requested_value = "Off"
#     CP_25.publish_requested_value(mqtt_handler)
#     time.sleep(5)
#     print(CP_25.readback_point.value)
#     print(rs.value)


# mqtt_handler.loop_stop()
