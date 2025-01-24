from collections import defaultdict
import os
from points import Remote_Write,Remote_Read, Remote_Sensor,Value
from controller2 import ControlPoint

"""
This is a middle man that holds all of the information about the system, sans transitions. It has a notion of topology/groupings of the the points.
It's primary purpose was to serve as a means to eval arbitrary expressions from Constraints classes used in Transitions.
It will also be useful as a global source of truth on the state of the systems, including things like point staleness, failed point writes, etc.
The main object is a big dicrionary with "leaves" are of class Value, meaning they have a .value attribute (important for the transition design).
The leaves are the lowest level of the hierarchy.
Surveyor also holds the control_points and sensors, except "virtual sensors" like fsm.time_in_state and fsm.state.
"""



class Surveyor(object):
    def __init__(self,points_config:dict):
        self.points_config = points_config
        self.layout =defaultdict(dict)
        self.sensor_points_dict = defaultdict(dict)
        self.control_points_dict = defaultdict(dict)
        self.virtual_points = defaultdict(dict)
        self.build_layout_and_points()
    

    def parse_dot_path(self,dot_path:str)->Value:
        """
        Given a dot path, return the dictionary that represents the path.
        If it's goes all the way down to a leaf, that leaf should have a .value
        """
        split_path = dot_path.split(".")
        D = self.layout
        for key in split_path:
            print(D)
            print('/n')
            D = D[key]
        assert isinstance(D,Value)
        return D

    def build_layout_and_points(self)->None:
        Big_D = defaultdict(dict)
        Big_D["R"] = defaultdict(dict)
        D = defaultdict(dict)
        D["sys"]["control_points"] = defaultdict(dict)
        control_points = self.points_config["sys"]["control_points"]
        control_points_dict = {}
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
            self.control_points_dict = control_points_dict
            
        D["sys"]["sensors"] = defaultdict(dict)
        sensor_points = self.points_config["sys"]["sensors"]
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
        self.sensor_points_dict = sensor_points_dict
        D["fsm"] = defaultdict(dict)
        Big_D = defaultdict(dict)
        Big_D["R"] = D
        self.layout = Big_D##Seems kind of uncessary now, but it was part of my plan and I think there was a good reason. Maybe thinking ahead to multilevel control.


    def update_layout_and_points(self,fsm_sensors)->None:
        self.layout["R"]["fsm"]["sensors"].update(fsm_sensors["fsm"]["sensors"])
        self.virtual_points.update(fsm_sensors)
        #self.virtual_points["fsm"]["sensors"]["state"] = fsm_sensors["sensors"]["state"]
        #fsm_sensors should look like {"fsm":{"sensors":{"time_in_state":0,"state":"Off"}}}
        ##some
        pass