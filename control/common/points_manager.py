from collections import defaultdict
import os
from typing import Dict,Tuple,List
from points import PublishInfo,Point,ReadOnly_Point,Writable_Point,ControlPoint,Writeable_Continuous_Point,Writeable_Discrete_Point
from values import Value,Discrete_Value,Continuous_Value

"""
This is the class that will manage the points. It will be responsible for creating the points, updating the points, and publishing the points.
This should be called from construction.py, passed a points config file for initial construction.
Then it will be used to construct states, after which points that depend on states will be added.
Finally, before the FSM is run, the points will be "activated" by setting the MQTTHandler
Features:
- Reflect topology/naming scheme of the points in the system.
- Keep track of the points in the system.
- Manages publishing points 
"""

def make_value(description,value_dict) -> Value:
    uuid,addr = value_dict["UUID"],value_dict["addr"]
    if "valid_range" in value_dict:
        valid_range = value_dict["valid_range"]
        init_raw = valid_range["lower"] ###? I don't know, hope this doesn't break anything
        value_class = Continuous_Value(uuid,addr,init_raw,description,valid_range)
        return value_class

    elif "valid_values" in value_dict:
        valid_values = value_dict["valid_values"]
        init_raw = valid_values[0]
        value_mapper = {}
        if "value_mapper" in value_dict:
            value_mapper = value_dict["value_mapper"]
        value_class = Discrete_Value(uuid,addr,init_raw,description,valid_values,value_mapper = value_mapper)
        return value_class

    else:
        raise ValueError("Couldn't infer value type (discrete or continuous) from valid_values or valid_range")
    
def make_point(value:Value,writeable = False) -> Point:
    if isinstance(value,Continuous_Value):
        if writeable:
            return Writeable_Continuous_Point(value,republish_frequency=5)
        else:
            return ReadOnly_Point(value)
        
    elif isinstance(value,Discrete_Value):
        if writeable:
            #maybe republish should be quicker, but it should write on state change.
            return Writeable_Discrete_Point(value,republish_frequency=60)
        else:
            return ReadOnly_Point(value)
        
    else:
        raise ValueError("Invalid value class, should be descrete or continuous.")

    

class Points_Manager:
    def __init__(self,microC_points_config:dict,publish_frequency:float = 60):
        self._microC_points_config = microC_points_config
        self.republish_frequency = publish_frequency
        self._points_lookup = {} ## for UUID lookup
        self._uuid_lookup = {} ## To look up UUIDS by topic
        self._uuids: List[int] = []
        self.points = self.build_microcontroller_points()
        self.control_points = self.build_control_points()



    def update_uuid_lookup(self,uuid:int,point:Point):
        assert not (uuid  in self._uuids)
        self._points_lookup[uuid] = point
        self._uuid_lookup[point.addr] = uuid
        self._uuids.append(uuid)

    def next_uuid(self):
        return max(self._uuids)+1
    
    def build_microcontroller_points(self)->dict:
            """First creates all values according to the initial points config file.
            Then makes all physical control points and sensors.
            When building valueclasses, should infer whether they are continuous or discrete based on valid_values or valid_range.
            Updates UUID lookup with all values.
            """
            ## Loop over all controllers, make values for everything. Then make control points and sensors.
            #Structure should be
            #Microncontrollers
            #--ControllerName
            #----sensors
            #------sensorName
            #--------reading_type (temperature, humidity, etc)
            #----------ValueClass for that reading (should be ContinuousValue for now, but could be DiscreteValue)
            #----control_points
            #------ControlPointName
            #--------readback:DiscreteValue
            #--------write:DiscreteValue
            source = self._microC_points_config["microcontrollers"]
            points = {"microcontrollers":defaultdict(dict)}

            for controller,controller_dict in source.items():
                points["microcontrollers"][controller] = defaultdict(dict)
                controller_points = points["microcontrollers"][controller]

                if "sensors" in controller_dict:
                    controller_points["sensors"] = defaultdict(dict)
                    for sensor_name,sensor_dict in controller_dict["sensors"].items():
                        controller_points["sensors"][sensor_name] = defaultdict(dict)
                        for reading_type,reading_dict in sensor_dict.items():
                            value = make_value(f"microcontroller:{controller} {sensor_name} {reading_type}",reading_dict)
                            point = make_point(value)
                            controller_points["sensors"][sensor_name][reading_type] = point
                            self.update_uuid_lookup(value.uuid,point)
                            
                
                if "control_points" in controller_dict:
                    controller_points["control_points"] = defaultdict(dict)
                    for cp_name,cp_dict in controller_dict["control_points"].items():
                        for rb_or_w in ["readback","write"]:
                            desc = f"{controller} {cp_name} {rb_or_w}"
                            value = make_value(desc,cp_dict[rb_or_w])
                            if rb_or_w == "readback":
                                point = ReadOnly_Point(value)
                                controller_points["control_points"][cp_name]["readback"] = point
                                self.update_uuid_lookup(value.uuid,point)
                            else:
                                assert isinstance(value,Discrete_Value)
                                point = Writeable_Discrete_Point(value,republish_frequency=self.republish_frequency)
                                controller_points["control_points"][cp_name]["write"] = point
                                self.update_uuid_lookup(value.uuid,point)

                points["microcontrollers"][controller] = controller_points

            return points
    
    def build_control_points(self)->Dict[str,ControlPoint]:
        control_points = {}
        for controller,controller_dict in self.points["microcontrollers"].items():
            if "control_points" in controller_dict:
                control_points[controller] = {}
                for cp_name,cp_dict in controller_dict["control_points"].items():
                    control_points[controller][cp_name] = ControlPoint(cp_dict["write"],cp_dict["readback"])
        return control_points
    


    def build_driver_points(self,driver_name:str,driver_states:list[str]):
        ##Build mush/drivers/driver_name/sensors/status/(state,state_time), writeable_points
        driver_points = {}
        topic_root = f"mush/drivers/{driver_name}/sensors/status/"
        valid_state_time_range = {"lower":0,"upper":1000000}
        valid_states = driver_states + ["unknown"]

        uuid = self.next_uuid()
        value = Discrete_Value(uuid,topic_root+"state","unknown","driver state",valid_states)
        point = Writeable_Discrete_Point(value,republish_frequency=self.republish_frequency)
        driver_points["state"] = point  
        self.update_uuid_lookup(uuid,point)
    
        uuid = self.next_uuid()
        value = Continuous_Value(uuid,topic_root+"state_time",0,f"{driver_name:} state_time",valid_state_time_range)
        #this guy should be updated frequently. Should probably be in settings.json
        point = Writeable_Continuous_Point(value,republish_frequency=5)
        self.update_uuid_lookup(uuid,point)
        driver_points["state_time"] = point

        return {"drivers":{driver_name:{"sensors":{"status":driver_points}}}}