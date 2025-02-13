from typing import Dict, NamedTuple, Protocol, Optional
from datetime import datetime
from values import Value, Discrete_Value,Continuous_Value

class PublishInfo(NamedTuple):
    name: str
    uuid: int
    value: str
    topic: str


class Point:
    def __init__(self, value_class: Value):
        self.value_class = value_class
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
    def __init__(self, value_class: Value, 
                 republish_frequency: float = 60.0,
                 retry_interval: float = 5.0):
        super().__init__(value_class)
        self._republish_frequency = republish_frequency
        self._retry_interval = retry_interval
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

    @property
    def retry_interval(self) -> float:
        """How long to wait before retrying failed publishes"""
        return self._retry_interval

    def pre_publish(self) -> None:
        """Called just before publishing to ensure fresh values"""
        pass

class Writeable_Discrete_Point(Writable_Point):
    """
    From FSM, we're going to need to write both continuous and discrete values.
    Should we 
    """
    def __init__(self, value_class: Discrete_Value,
                 republish_frequency: float = 60.0,
                 retry_interval: float = 5.0):
        super().__init__(value_class, republish_frequency, retry_interval)
        self.value_class = value_class
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
    def __init__(self, value_class: Continuous_Value,
                 republish_frequency: float = 60.0,
                 retry_interval: float = 5.0):
        super().__init__(value_class, republish_frequency, retry_interval)
        self.value_class = value_class
        self._valid_range = self.value_class._valid_range
    
    @property
    def requested_value(self):
        return self._requested_value

    @requested_value.setter
    def requested_value(self,candidate_value):
        #I don't really like that I'm casting here, but it works.
        candidate_value = self.value_class._value_type(candidate_value)
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
    def __init__(self, write_point: Writeable_Discrete_Point, readback_point: ReadOnly_Point, republish_frequency_mismatch = 5):
        self._write_point = write_point
        self._readback_point = readback_point
        self._name = self.derive_name()
        self._requested_value = write_point.requested_value
        self._republish_frequency_mismatch = republish_frequency_mismatch

    @property
    def write_point(self):
        return self._write_point
        
    @property
    def readback_point(self):
        return self._readback_point

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


class TimeProvider(Protocol):
    def get_time_in_state(self) -> float: ...

class FSM_StateTimePoint(Writeable_Continuous_Point):
    """Point that gets fresh time values from a time provider"""
    def __init__(self, value_class: Continuous_Value, time_provider: Optional[TimeProvider] = None, **kwargs):
        super().__init__(value_class, **kwargs)
        self._time_provider = time_provider
        
    def set_time_provider(self, provider):
        """Set the time provider safely"""
        self._time_provider = provider
        
    @property
    def value(self):
        """Always return fresh time from provider"""
        if self._time_provider is not None:
            return self._time_provider.get_time_in_state()
        return self.value_class.value
        
    def pre_publish(self) -> None:
        """Update requested value before publishing"""
        if self._time_provider is not None:
            self.requested_value = self._time_provider.get_time_in_state()


class PointPublisher(Protocol):
    """Interface for publishing points"""
    def publish(self, point: 'Writable_Point', force: bool = False) -> None: ...

class MonitoredPoint:
    """Point that needs periodic publishing"""
    def __init__(self, point: 'Writable_Point', publisher: PointPublisher):
        self.point = point
        self.messenger = publisher  # Could be any class that implements PointPublisher
        self._last_publish = datetime.now()
    
    def publish(self, force: bool = False):
        """Publish point value with force option"""
        self.point.pre_publish()  # Important for FSM_StateTimePoint
        self.messenger.publish(self.point, force=force)  # Use messenger
        if force:
            self._last_publish = datetime.now()
    
    def check_republish(self):
        """Check if point needs republishing based on frequency"""
        now = datetime.now()
        time_since_publish = (now - self._last_publish).total_seconds()
        if time_since_publish >= self.point.republish_frequency:
            self.publish(force=True)

    @property
    def requested_value(self):
        return self.point.requested_value

    @requested_value.setter 
    def requested_value(self, value):
        self.point.requested_value = value


