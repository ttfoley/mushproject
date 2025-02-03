import json
import sys
import os
from typing import Dict, Any,Tuple
#The fact that I'm importing so many separate things seems like a bad smell, but this is the constructor only...
from states import State, States_Manager
from points_manager import Points_Manager
from collections import defaultdict





class PreTransitionsConstructor(object):
    """
    Builds everything up to the transitions. Transitions are hard to build, having this info available 
    will make it easier to build them.
    """
    def __init__(self,config_path):
        self._config_path = config_path
        self._microC_points_config = json.load(open(os.path.join(config_path,"microC_points.json")))
        self._states_config = json.load(open(os.path.join(config_path,"states.json")))
        self._settings = json.load(open(os.path.join(config_path,"settings.json")))
        self._driver_name = self._settings["driver"]["name"]
        self.PM = Points_Manager(self._microC_points_config)
        self.SM = States_Manager(self._states_config,self._settings["driver"]["initial_state"])
        self._driver_points = self.PM.build_driver_points(self._driver_name,self.SM.state_names)
        self.PM.points.update(self._driver_points)


# class Constructor(object):
#     def __init__(self,configuration:Configuration):
#         self.config = configuration
#         self.states_config = self.config.states_config 
#         self.transitions_config = self.config.transitions_config
#         self.microC_points_config = self.config.microC_points_config
#         self.settings = self.config.settings
#         self.initial_state_name = self.settings["fsm"]["initial_state"]
#         #self.surveyor = Surveyor(self.points_config)
        
#         #Now why is states constructor different? It's not complicated enough to warrant a separate class I guess
#         self.states = self.build_states()
#         self.initial_state = self.states[self.initial_state_name]
#         self.transitions_manager = Transitions_Manager(self.transitions_config,self.states,self.surveyor)
#         self.fsm = FSM(self.states,self.transitions_manager,self.surveyor,self.initial_state)
#         self.add_fsm_sensors()
#         #This is just a wrapper for the mqtt_handler so we know what we're dealing with over there.
#         self.mqtt_handler = self.set_up_mqtt()
#         self.activate_CPs()

        
#     def set_up_mqtt(self):
#         mqtt_point_info = MQTT_PointInfo(self.surveyor.control_points_dict,self.surveyor.sensor_points_dict)
#         settings = self.settings["mqtt"]
#         settings.update({"userdata":mqtt_point_info})
#         mqtt_handler = MQTTHandler(**settings)
#         return mqtt_handler
    
#     def subscribe_mqtt(self,mqtt_handler:MQTTHandler):
#         for topic in self.surveyor.substriction_topics:
#             mqtt_handler.subscribe(topic)
    
#     def activate_CPs(self):
#         for cp in self.surveyor.control_points_dict.values():
#             cp.set_mqtt_handler =self.mqtt_handler


    
#     def add_fsm_sensors(self):
#         fsm_sensors = {"fsm":{"sensors":{"state":self.fsm.state,"time_in_state":self.fsm.time_in_state}}}
#         self.surveyor.update_virtual_sensors(fsm_sensors)









  