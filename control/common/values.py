from collections import defaultdict
import json
from typing import Dict, Tuple,Mapping
from datetime import datetime
#Need to define custom types
StrFloatTuple = Tuple[str,float]
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
    def __init__(self, uuid: int, addr:str, raw_value, description: str, value_type: type = float, 
                 raw_value_type: Tuple[type,type]= (str,float)):
        self.uuid = uuid
        self.description = description
        self._addr = addr
        self._raw_value_type = raw_value_type
        self._value_type = value_type
        self._raw_value = raw_value

        self._value = None
        self._last_update_time = None  # Temporary initialization
        #Note, need to call self.value = raw_value to set the value and update the last_update_time

    @property
    def value(self):
        return self._value
    
    @value.setter
    def value(self, new_value):
        # Checks here for type, valid values, etc.
        # Also converts (like "off" to "Off")
        #This should come after checks for valid values and type.
        self._raw_value = new_value
        self._value = new_value
        self._last_update_time = datetime.now()

    @property
    def addr(self):
        return self._addr

    @property
    def last_update_time(self):
        return self._last_update_time
    



class Discrete_Value(Value):
    """
     Right now values that come from MQTT are floats.
    """
    def __init__(self,uuid:int,addr,raw_value,description:str,valid_values:list[str],value_mapper:Dict[str,str]={},value_type = str,
                 raw_value_type:Tuple[type,type] = (str,float)):
        super().__init__(uuid,addr,raw_value,description,value_type,raw_value_type)
        assert type(valid_values[0]) == value_type
        self._valid_values = valid_values
        self._value_mapper = value_mapper


    @property
    def value(self):
        #What happens if nothing is set?
        return self._value       
     
    @value.setter
    def value(self,new_value):
        ##Checks here for type, valid values, etc.
        ##Also converts (like "off" to "Off")
        #only sets raw_value and value if we can make a valid value out of it.
        #For now only consider final values as strings!!
        cast_value = new_value
        if type(new_value) != str:
            try:
                cast_value = str(int(new_value))
            except:
                raise ValueError(f"New value {new_value} (raw = {self._raw_value}) couldn't be case to a str.")
       
        success,mapped_value =self.map_value(cast_value)
        if mapped_value in self._valid_values:
            self._raw_value = new_value
            self._value = mapped_value
            self._last_update_time = datetime.now()
        else:
            raise ValueError(f"Mapped value {mapped_value} (raw = {self._raw_value}) not in valid values: {self._valid_values}")
        


    
    def map_value(self,unmapped_value:str)->Tuple[bool,str]:
        #For now, we're assuming/requiring that all discrete values are strings.
        if self._value_mapper == {}:
            return True,unmapped_value
        else:
            try:
                return True,self._value_mapper[unmapped_value]
            except:
                return False,f"Invalid value {unmapped_value}, doesn't map to anything in {self._value_mapper}"


class Continuous_Value(Value):
    def __init__(self,uuid:int,addr,raw_value,description:str,valid_range:Mapping[str,float],value_type = float,
                 raw_value_type:Tuple[type,type] = (str,float)):
        super().__init__(uuid,addr,raw_value,description,value_type,raw_value_type)
        self._valid_range = valid_range

    @property
    def value(self) -> float:
        ##What does value return if it's not sucessfully set?
        return self._value       
     
    @value.setter
    def value(self,new_value):
        ##Checks here for type, valid values, etc.
        ##Also converts (like "off" to "Off")
        #Setting raw value here may be wrong, if we don't end up updating the converted value.
        #This needs to be improved.
        self._raw_value = new_value
        if self._raw_value_type[0] == str:
            if self._raw_value_type[1] == float:
                new_value = float(new_value)
            elif self._raw_value_type[1] == int:
                new_value = int(new_value)
            else:
                #try float anyway
                new_value = float(new_value)

        if self.value_valid(new_value): 
            self._value = new_value
            self._last_update_time = datetime.now()
        else:
            raise ValueError(f"New value {new_value} (raw = {self._raw_value}) not in valid range {self._valid_range['lower']} <= x <= {self._valid_range['upper']}")

    
    def value_valid(self,new_value)-> bool: 
        return self._valid_range["lower"] <= new_value <= self._valid_range["upper"]
    


    