from collections import defaultdict

import json
from datetime import datetime
"""
We're going to generalize beyond the old ControlPoints so we can handle things like sensors and external commands from a higher level controllers.
Also changing how values are stored, indexed, and accessed via a new class.
"""

class Value:
    """
    To help with type checking and to ensure consistency in the data, every value will have a value property.
    Want to have type check, conversion, and range verification eventually.
    So far all of our messages are simply strings. We will have conversions within the setters.
    """
    def __init__(self, raw_value, description: str, value_type: type = float, raw_value_type: type = str):
        self.description = description
        self._value = raw_value

    @property
    def value(self):
        return self._value
    
    @value.setter
    def value(self, new_value):
        # Checks here for type, valid values, etc.
        # Also converts (like "off" to "Off")
        self.raw_value = new_value
        self._value = new_value

class RemoteValue(Value):
    """
    A derived class that includes a UUID for remote values.
    """
    def __init__(self, uuid: int, raw_value, description: str, value_type: type = float, raw_value_type: type = str):
        super().__init__(raw_value, description, value_type, raw_value_type)
        self.uuid = uuid

##Why am I rewriting so much> Where' the inheritance?
class Remote_Write(RemoteValue):
    def __init__(self,uuid:int,raw_value,write_addr:str,description:str,valid_values:list[str]):
        super().__init__(uuid,raw_value,description)
        self._write_address =write_addr

        self.valid_values = valid_values

        
    @property
    def value(self):
        #
        return self._value       
     
    @value.setter
    def value(self,new_value):
        ##Checks here for type, valid values, etc.
        ##Also converts (like "off" to "Off")
        self.raw_value = new_value
        self._value = new_value

    @property
    def write_address(self):
        return self._write_address
    

    def value_valid(self,new_value):
        return new_value in self.valid_values

class Remote_Read(RemoteValue):
    def __init__(self,uuid:int,raw_value,read_addr:str,description:str,valid_values:list[int]):## Remember it's writing back 
        super().__init__(uuid,raw_value,description)
        self._read_address = read_addr
        self.valid_values = valid_values


    @property
    def value(self) -> str:
        #
        return self._value       
     
    @value.setter
    def value(self,new_value):
        ##Checks here for type, valid values, etc.
        ##Also converts (like "off" to "Off")
        self.raw_value = new_value
        new_value = int(float(new_value))
        print(f"NEW VALUE  {new_value}")
        if not self.value_valid(new_value):
            self._value = "Unknown" ## Unknown state for control points
            raise ValueError(f"New value {new_value} not in valid values {self.valid_values}")
        if new_value == 1:
            self._value = "On"
        if new_value == -1:
            print(new_value)
            self._value = "Off"

    @property
    def read_address(self):
        return self._read_address
    
    def value_valid(self,new_value)-> bool: 
        return new_value in self.valid_values
        



class Remote_Sensor(RemoteValue):
    ##For continous values like temperature, humidity, etc. I would also like to have units in all of these, but that's a future feature.
    def __init__(self,uuid:int,raw_value,read_addr:str,description:str,lower_bound:float,upper_bound:float):
        super().__init__(uuid,raw_value,description)
        self._read_address = read_addr
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.last_read = datetime.now()
        self._value = raw_value

    @property
    def value(self):
        #
        return self._value
    
    @value.setter
    def value(self,new_value):
        ##Checks here for type, valid values, etc.
        ##Also converts (like "off" to "Off")
        ## Need to put in all of the helpful typing and conversion I could do here.
        self.last_read = datetime.now()
        self._raw_value = new_value
        self._value = float(new_value)

    @property
    def read_address(self):
        return self._read_address
    
    def value_valid(self,new_value):
        return new_value >= self.lower_bound and new_value <= self.upper_bound

class Virtual_Sensor(Value):
    def __init__(self,raw_value,description:str):
        super().__init__(raw_value,description)
        self.last_read = datetime.now()
        self._value = raw_value

    @property
    def value(self):
        #
        return self._value
    
    @value.setter
    def value(self,new_value):
        self._value = new_value
        ##Checks here for type, valid values, etc.
        ##Also converts (like "off" to "Off")
        ## Need to put in all of the helpful typing and conversion I could do

class ControlPoint:
    """
    Right now this does not verify its state with readback.  It's just a container for the state. I want control points to have a liveness/staleness, but
    I don't know if this is the best place to do it.  Something like a separate health monitor class?
    I made some stuff properties because I want to protect them, but I should be even more careful probably.
    """
    def __init__(self, name, write_point:Remote_Write, readback_point:Remote_Read,republish_frequency_match = 60,republish_frequency_mismatch = 5):
        self._name = name
        self.write_point = write_point
        self.readback_point = readback_point
        self._value = self.readback_point.value
        self.requested_value = None
        self.time_start_value = datetime.now() #these really shouldn't be initialized on creation.
        self.time_last_published = datetime.now()
        self.republish_frequency_match = republish_frequency_match
        self.republish_frequency_mismatch = republish_frequency_mismatch
        #So we're resigning ourselves to no memory of the last state after a reboot, which seems fine for now

    def set_known_value(self, new_value):
        #This should only be used if you know the state from readback.
        #If state changed, restart the timer
        #only used within mqtt_handler callback
        #Validation should happen here.
        if self.readback_point.value != new_value:
            self.time_start_value = datetime.now()
        self.readback_point.value = new_value
    
    @property
    def status(self)->dict[str,str]:
        return {"point_name":self._name,"value":self._value}
    
    @property
    def state(self):
        return self._value
    
    @property
    def name(self):
        return self._name

    def time_in_value(self):
        return (datetime.now() - self.time_start_value).total_seconds()
    
    def time_since_last_published(self):
        return (datetime.now() - self.time_last_published).total_seconds()    

    def set_requested_value(self, state:str):
        assert state in ["On","Off"]
        self.requested_value = state

    def publish_requested_value(self, mqtt_handler):
        #Setting this at beginning so we don't spam mqtt channel.
        #TODO should have exception catching on the publish command.
        self.time_last_published = datetime.now()
        if self.requested_value == "On":
            mqtt_handler.publish(self.write_point.write_address, "on")
        elif self.requested_value == "Off":
            mqtt_handler.publish(self.write_point.write_address, "off")
        else:
            raise ValueError("Requested state must be On or Off")
        
    def publish(self,mqtt_handler,immediately=False):
        assert self._value in ["On","Off","Unknown"]
        if self._value != self.requested_value:
            if immediately:
                self.publish_requested_value(mqtt_handler)
            elif self.time_since_last_published() > self.republish_frequency_mismatch:
                self.publish_requested_value(mqtt_handler)
        elif self.time_since_last_published() > self.republish_frequency_match:
            self.publish_requested_value(mqtt_handler)
        

    def __eq__(self, other):
        #This is obviously not good enough, but it's a start.
        if not isinstance(other, ControlPoint):
            return False
        return (self._name == other._name) and (self._value == other._value)

    def __hash__(self):
        return hash(self._name)
    
    def __repr__(self) -> str:
        return f"ControlPoint {self._name}, state: {self._value}, requested_value: {self.requested_value}"


class Outputs:
    """
    To keep track of groups of outputs.  Methods for equality and comparison.
    Include "Unknown" as a valid control point state. 
    Valid value of outputs are "On","Off","Unknown"
    #TODO: I don't like that this is a named_tuple.  I don't like that I have to use output_value to keep the name and value together. 
    #Note that the control points are sorted by name.  This is to make sure that the hash is consistent.
    #There should be no way to change the values of control points from here, but they should be kept live by the mqtt_handler.
    ## It seems redundant
    """
    def __init__(self,control_points:list[ControlPoint]):
        self._control_points = self.sort_and_validate(control_points)
        self.lookup = {cp._name:cp for cp in control_points}


    @property
    def point_names(self):
        return [cp._name for cp in self._control_points]
    
    @property
    def outputs(self):
        return {cp:cp._value for cp in self._control_points}  
      
    @property
    def outputs_str(self):
        return {cp._name:cp._value for cp in self._control_points}

    @property
    def is_unknown(self):
        return any([cp.state == "Unknown" for cp in self._control_points])

    def sort_and_validate(self,control_points:list[ControlPoint])->list[ControlPoint]:
        #Make sure the outputs are valid
        for cp in control_points:
            assert cp.state in ["On","Off","Unknown"], f"Invalid state for control point {cp.name}:{cp.state}"
        #Sort the outputs by name
        return sorted(control_points,key = lambda x: x._name)
    
    # def match_state_output(self,state:State)->bool:
    #     #Check if the state outputs match the outputs of the actual.
    #     #note 
    #     return state.outputs.outputs == self.outputs_str

    def __eq__(self, other):
        """To compare two Outputs, they must have the same control points and the same values for each control point.
        I think I could get by with just comparing the dictionaries, but this is more explicit and gives better error messages.
        Note this does not include the "Unknown" state, as that is not a valid state for a state."""
        if not isinstance(other, Outputs):
            return False
        
        if len(self._control_points) != len(other._control_points):
            print("Different number of outputs")
            return False
        
        elif self.point_names != other.point_names:
            print("Different control points")
            return False

        elif self.is_unknown:
            #This is comparing two unknown states, which is always true.
            if other.is_unknown:
                return True
            #If I'm unknown, and the other isn't, then they're not equal.
            else:
                return False

        else:
            for point_name in self.point_names:
                if self.outputs[point_name] != other.outputs[point_name]:
                    return False
            return True
        
    def __repr__(self):
        return f"Outputs: {self.outputs}"
        
    def __hash__(self):
        #This is ugly, one example of why I want to get rid of type named_tuple
        point_names = sorted([point._name for point in self.outputs.keys()])
        output_values = []
        for point in point_names:
            for key in self.outputs.keys():
                if key._name == point:
                    output_values.append(self.outputs[key])
        hashed = ""
        for point_name,output_value in zip(point_names,output_values):
            hashed += f"{point_name}:{output_value},"
        hashed = hashed[:-1]

        return hash(hashed)