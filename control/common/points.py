
from typing import Dict, NamedTuple
from datetime import datetime
from values import Value, Discrete_Value,Continuous_Value


class PublishInfo(NamedTuple):
    name: str
    uuid: int
    value: str
    topic: str


class Point:
    def __init__(self,value_class:Value):
        self.value_class = value_class## value class
        self._uuid = self.value_class.uuid
        self._description = self.value_class.description
        self._addr = self.value_class.addr
    
    @property
    def value(self):
        return self.value_class.value
    
    @property
    def last_update_time(self):
        return self.value_class.last_update_time
    
    @property
    def uuid(self):
        return self._uuid
    
    @property
    def addr(self):
        return self._addr

    @property
    def description(self):
        return self._description
    

    

##TODO Would probably be nice to have a composite point for sensors that have multiple readings.
class ReadOnly_Point(Point):
    """
    This is a class that represents a point that can be read from, shouldn't be written to.
    Do I need to sublass it for continuous and discrete? Seems like I shouldn't need to.
    """

    def __init__(self,value_class:Value):
        super().__init__(value_class)
    

class Writable_Point(Point):
    """
    This is a class that represents a point that can be written to. Information includes how frequently to republish.
    Note that in the subclasses methods are provided to ensure the requested value (for publishing) is valid.
    """
    def __init__(self,value_class:Value,republish_frequency:float = 60):
        super().__init__(value_class)

        self._republish_frequency= republish_frequency
        self._requested_value = None
        self._time_start_value = datetime.now()
        self._time_last_published = datetime.now()
        self._time_requested_value = None

    @property
    def requested_value(self):
        return self._requested_value
    
    @requested_value.setter
    def requested_value(self,value):
        raise NotImplementedError("Will depend on subclass")
    
    @property
    def time_requested_value(self):
        return self._time_requested_value
    
    @property
    def time_start_value(self):
        return self._time_start_value
    
    @property
    def time_last_published(self):
        return self._time_last_published
    
    @property
    def republish_frequency(self):
        return self._republish_frequency

class Writeable_Discrete_Point(Writable_Point):
    """
    From FSM, we're going to need to write both continuous and discrete values.
    Should we 
    """
    def __init__(self,value_class:Discrete_Value,republish_frequency = 60): 
        super().__init__(value_class,republish_frequency)
        self.value_class = value_class # How does this work? Does it just override type checking?
        self._valid_values = self.value_class._valid_values
    
    @property
    def requested_value(self):
        return self._requested_value

    @requested_value.setter
    def requested_value(self,candidate_value):
        assert type(candidate_value) == self.value_class._value_type
        if candidate_value in self._valid_values:
            self._requested_value = candidate_value
            self._time_requested_value = datetime.now()
        else:
            raise ValueError(f"Requested value {candidate_value} is not in valid values {self._valid_values}")

    
class Writeable_Continuous_Point(Writable_Point):
    """
    From FSM, we're going to need to write both continuous and discrete values.
    """
    def __init__(self,value_class:Continuous_Value,republish_frequency= 60):
        super().__init__(value_class,republish_frequency)
        self.value_class = value_class # How does this work? Does it just override type checking?
        self._valid_range = self.value_class._valid_range
    
    @property
    def requested_value(self):
        return self._requested_value

    ##This is checking requested value, not the value itself.
    @requested_value.setter
    def requested_value(self,candidate_value):
        assert type(candidate_value) == self.value_class._value_type
        if self.valid_value(candidate_value):
            self._requested_value = candidate_value
            self._time_requested_value = datetime.now()
        else:
            raise ValueError(f"Requested value {candidate_value} is not in valid range {self._valid_range}")

    def valid_value(self,candidate_value)->bool:
        if candidate_value < self._valid_range["lower"] or candidate_value > self._valid_range["upper"]:
            raise ValueError(f"Requested value {candidate_value} is not in valid range {self._valid_range}")
        return True




class ControlPoint:
    """
    This is a class that represents a control point, defined/designed to group a writable point with matching readback point. These exist only in
    in reference to the microcontroller. Stripped down from old version. 
    """


    def __init__(self, write_point:Writeable_Discrete_Point, readback_point:ReadOnly_Point,republish_frequency_mismatch = 5):
        self._write_point = write_point
        self._readback_point = readback_point
        self._name = self.derive_name()
        self._requested_value = write_point.requested_value
        self._republish_frequency_mismatch = republish_frequency_mismatch
        #So we're resigning ourselves to no memory of the last state after a reboot, which seems fine for now



    @property
    def requested_value(self):
        return self._requested_value
    
    @property
    def read_write_match(self)->bool:
        return self._write_point.value == self._readback_point.value
    
    @property
    def force_republish(self)->bool:
        #Checks if it's been too long since we tried to make readback match write.
        #I'm not sure if this logic should be inside CP or PointsManager
        #Less refactoring I think if it's inside CP.
        if not self.read_write_match:
            if (datetime.now() - self._write_point.time_last_published).total_seconds() > self._republish_frequency_mismatch:
                return True
            else:
                #Time not up yet
                return False
        return False

    @property
    def publish_write_info(self)->PublishInfo:
        return PublishInfo(
            name=self._name,
            uuid=self._write_point.uuid,
            value=self.requested_value,
            topic=self._write_point.addr
        )
    
    def request_publish(self,point_manager):
        #This is where we'lll call the PointManager.publish_now method
        publish_info = self.publish_write_info
        raise NotImplementedError("This will depend PointManager")

    def derive_name(self)->str:
        #name should be derivable from addresses. I don't know if this is better than passing name... I just like one less arg.
        try:
            read_owner = self._readback_point.addr.split("/")[-2]
            write_owner = self._write_point.addr.split("/")[-2]
            if read_owner != write_owner:
                raise ValueError(f"Read {read_owner} and write {write_owner} points don't have the same CP as their owner.")
            return write_owner
        except:
            raise ValueError("Name should be derivable from addr, something went wrong")


