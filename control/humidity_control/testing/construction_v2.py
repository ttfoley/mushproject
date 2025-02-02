import os
import sys
import json
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from points_manager import Points_Manager
from states import States_Manager

points_config = json.load(open(os.path.join(config_path,"microC_points.json"),'r'))
PM = Points_Manager(points_config)
print(PM.points["microcontrollers"]["C1"]["sensors"]["sht_0"]["temperature"])

settings = json.load(open(os.path.join(config_path,"settings.json"),'r'))
states_config = json.load(open(os.path.join(config_path,"states.json"),'r'))
SM = States_Manager(states_config,settings["driver"]["initial_state"])
driver_points = PM.build_driver_points(settings["driver"]["name"],SM.state_names)
print(driver_points["drivers"]["humidity_control"])
PM.points.update(driver_points)
print(PM.points["drivers"]["humidity_control"]["sensors"]["status"])