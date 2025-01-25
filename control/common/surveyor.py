from collections import defaultdict
import os
from typing import Dict,Tuple
from points import Remote_Write,Remote_Read, Remote_Sensor,Value, ControlPoint
from states import State

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
        #This is kind of hacky just so I can get my type hints from the constructor.
        self.constructor = Surveyor_Constructor(points_config)
        self.layout,self.control_points_dict,self.sensor_points_dict = self.constructor.build_layout_and_points()
        self.virtual_points = defaultdict(dict)
        self.cached_lookup = {}
        #This whole update method for building these is maybe an antipattern?
    

    def cp_value(self,cp_name:str)->str:
        #This is a convenience method for getting the value of a control point, which I guess are still just strings, seems like they should be typed.
        return self.control_points_dict[cp_name].value
    
    def cp_lookup(self,cp_name:str)->ControlPoint:
        return self.control_points_dict[cp_name]

    def get_compatible_states(self,states:Dict[str,State])->list[State]:
        ##Should loop through the states, and return the ones that are compatible with the current outputs.
        #Again assumes every state has same number of control points. Need to have an "any" type state for this to work with states with different # of control points.
        #Dummy for now
        cp_names = list({cp for state in states.values() for cp in state.outputs.keys()})
        #could be neater
        for _,state in states.items():

            live_points = {cp:self.cp_value(cp) for cp in cp_names}
            compatible_states= []
            for state in states.values():
                if state.matched_outputs(live_points):
                    compatible_states.append(state)
    
        return compatible_states

    def lookup_dot_path(self,dot_path:str)->Value:
        if dot_path in self.cached_lookup:
            return self.cached_lookup[dot_path]
        else:
            found_value,D = self.parse_dot_path(dot_path)
            if found_value:
                self.cached_lookup[dot_path] = D
                return D
            else:
                raise ValueError(f"Dot path {dot_path} does not exist.")


    def parse_dot_path(self,dot_path:str)->Tuple[bool,Value]:
        """
        Given a dot path, return the dictionary that represents the path.
        If it's goes all the way down to a leaf, that leaf should have a .value
        """
        split_path = dot_path.split(".")
        D = self.layout
        for key in split_path:
            #print(D)
            #print('/n')
            D = D[key]
        assert isinstance(D,Value)
        found_value = D.value != ""
        return found_value,D
    
    def value_exists(self,dot_path:str)->bool:
        if dot_path in self.cached_lookup:
            return True
        else:
            exists,v = self.parse_dot_path(dot_path)
            if exists:
                self.cached_lookup[dot_path] = v
                return True
            else:
                return False

    @property
    def substriction_topics(self)->list[str]:
        #Will get all of the topics we want to subrscribe to, excluding Write topics.
        #TODO, make this depend on the states and transition rules, so we're not subscribing to everything.
        topics = []
        for cp in self.control_points_dict.values():
            topics.append(cp.readback_point._read_address)
        #Iterates over temp,humidity, etc.
        for sensor_type in self.sensor_points_dict.values():
            for sensor in sensor_type.values():
                topics.append(sensor._read_address)
        return topics
    
        

    def update_virtual_sensors(self,fsm_sensors)->None:
        #This is slopppppy right now.
        #TODO CLEAN THIS UP.
        self.layout["R"]["fsm"]["sensors"].update(fsm_sensors["fsm"]["sensors"])
        self.virtual_points.update(fsm_sensors)
        #self.virtual_points["fsm"]["sensors"]["state"] = fsm_sensors["sensors"]["state"]
        #fsm_sensors should look like {"fsm":{"sensors":{"time_in_state":0,"state":"Off"}}}
        ##some

class Surveyor_Constructor:
    #I don't know why I decided to make this a separate class instead of a method, I guess I thought it waas just too big.
    def __init__(self,points_config:dict):
        self.points_config = points_config
    
    """Note how this whole thing still looks pretty arcane. It defines the "topology" of the system. In a perfect world,
    I would encode enough info in together with some general rules about where things belong, and then the surveyor would be able to build itself. 
    But alas, I just want to get it working.
    """
    def build_layout_and_points(self)->Tuple[dict,Dict[str,ControlPoint],Dict[str,Dict[str,Remote_Sensor]]]:
        Big_D = defaultdict(dict)
        Big_D["R"] = defaultdict(dict)
        D = defaultdict(dict)
        D["sys"]["control_points"] = defaultdict(dict)
        control_points = self.points_config["sys"]["control_points"]
        control_points_dict = {}
        sensor_points_dict = defaultdict(dict)
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
        sensor_points = self.points_config["sys"]["sensors"]

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
        D["fsm"] = defaultdict(dict)
        Big_D = defaultdict(dict)
        Big_D["R"] = D
        
        return Big_D,control_points_dict,sensor_points_dict



class MQTT_PointInfo:
    def __init__(self, control_points_dict: Dict[str, ControlPoint], sensor_points_dict: Dict[str,Dict[str, Remote_Sensor]]):
        #Unwrapping them so they can be accessed by the mqtt_handler easily
        self._sensor_points_dict = {sensor_name:sensor for sensor_type in sensor_points_dict.values() for sensor_name, sensor in sensor_type.items()}
        self._control_points_dict = control_points_dict
      
    @property
    def control_points(self)->Dict[str,ControlPoint]:
        return self._control_points_dict
    
    @property 
    def sensor_points(self)->Dict[str,Remote_Sensor]:
        return self._sensor_points_dict
