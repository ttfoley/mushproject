from collections import defaultdict
import json
from typing import Dict, Tuple,Mapping, Any
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
    def __init__(self, uuid: int, addr: str, init_raw: Any, description: str, 
                 valid_values: list[str], value_mapper: Dict[str, str] = {}):
        super().__init__(uuid, addr, init_raw, description)
        self._valid_values = valid_values
        self._value_mapper = value_mapper
        self._value_type = str  # Always use strings for discrete values

    @property
    def value(self):
        return self._value

    @value.setter 
    def value(self, new_value):
        ## This is complicated, but it handles the fact that we can get floats from MQTT and we want to store them as ints.
        # First convert any string floats to actual floats
        if isinstance(new_value, str):
            try:
                new_value = float(new_value)
            except ValueError:
                pass  # Not a numeric string, keep as is

        # Now handle any numeric values by converting to clean strings
        if isinstance(new_value, (int, float)):
            # Convert to clean string without decimal if it's whole number
            if isinstance(new_value, int) or new_value.is_integer():
                new_value = str(int(new_value))
            else:
                new_value = str(new_value)
        elif not isinstance(new_value, str):
            raise ValueError(f"Cannot handle value type: {type(new_value)}")

        # Apply value mapping
        success, mapped_value = self.map_value(new_value)
        if not success:
            raise ValueError(f"Value mapping failed: {mapped_value} from {new_value} in {self._value_mapper}")

        if mapped_value in self._valid_values:
            self._value = mapped_value
            self._last_update_time = datetime.now()
        else:
            raise ValueError(f"Value {mapped_value} not in valid values {self._valid_values}")

    def map_value(self, unmapped_value: str) -> Tuple[bool, str]:
        """Map input value using value_mapper if present"""
        if not self._value_mapper:
            return True, unmapped_value
        try:
            return True, self._value_mapper[unmapped_value]
        except KeyError:
            return False, f"Invalid value {unmapped_value}, not in mapper {self._value_mapper}"


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
    


    