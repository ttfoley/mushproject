from collections import defaultdict
import os
from typing import Dict,Tuple,List, Any
from points import PublishInfo,Point,ReadOnly_Point,Writable_Point,ControlPoint,Writeable_Continuous_Point,Writeable_Discrete_Point,FSM_StateTimePoint,TimeProvider
from values import Value,Discrete_Value,Continuous_Value
from datetime import datetime
from messaging import MessagePublisher

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
    
def make_sensor_point(value: Value) -> Point:
    """Create a read-only point for microcontroller sensors"""
    return ReadOnly_Point(value)

def make_command_point(value: Value) -> Point:
    """Create a read-only point for governor commands"""
    return ReadOnly_Point(value)

class Points_Manager:
    """Base Points Manager without MQTT functionality"""
    def __init__(self, points_config: dict, settings: dict):
        self._points_config = points_config
        self._settings = settings  # Store full settings dict
        
        # Get publish settings with defaults
        publish_settings = settings.get('points', {}).get('publish', {})
        self._default_retry = publish_settings.get('default_retry_interval', 5)
        self._default_republish = publish_settings.get('default_republish_frequency', 60)
        self._point_settings = publish_settings.get('point_types', {})
        
        self._points_lookup = {}
        self._uuid_lookup = {}
        self._uuids = []
        self.points = self.build_microcontroller_points()
        self.control_points = self.build_control_points()
        self._topics_to_subscribe = set() 

    def get_point_settings(self, point_type: str) -> dict:
        """Get publish settings for a point type"""
        settings = self._point_settings.get(point_type, {})
        return {
            'retry_interval': settings.get('retry_interval', self._default_retry),
            'republish_frequency': settings.get('republish_frequency', self._default_republish)
        }

    def update_uuid_lookup(self,uuid:int,point:Point):
        assert not (uuid  in self._uuids)
        self._points_lookup[uuid] = point
        self._uuid_lookup[point.addr] = uuid
        self._uuids.append(uuid)

    def next_uuid(self):
        return max(self._uuids)+1
    
    def value_exists(self,uuid:int):
        return uuid in self._points_lookup
    
    def get_value(self,uuid:int)->Value:
        return self._points_lookup[uuid].value
    
    def get_point(self,uuid:int)->Point:
        return self._points_lookup[uuid]

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
            source = self._points_config["microcontrollers"]
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
                            point = make_sensor_point(value)
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
                                settings = self.get_point_settings('control_points')
                                point = Writeable_Discrete_Point(value, **settings)
                                controller_points["control_points"][cp_name]["write"] = point
                                self.update_uuid_lookup(value.uuid,point)

                points["microcontrollers"][controller] = controller_points

            return points
    
    def build_control_points(self) -> Dict[str, Dict[str, ControlPoint]]:
        """Build control points mapping: controller -> name -> ControlPoint"""
        control_points = {}
        for controller, controller_dict in self.points["microcontrollers"].items():
            if "control_points" in controller_dict:
                control_points[controller] = {}
                for cp_name, cp_dict in controller_dict["control_points"].items():
                    control_points[controller][cp_name] = ControlPoint(cp_dict["write"], cp_dict["readback"])
        return control_points
    
    def dump_uuid_lookup(self):
        return self._uuid_lookup

    def get_point_by_topic(self, topic: str) -> Point:
        """Get a point by its MQTT topic"""
        if topic not in self._uuid_lookup:
            raise ValueError(f"No point found for topic: {topic}")
        return self._points_lookup[self._uuid_lookup[topic]]

    def get_control_point_pair(self, cp_id: str) -> tuple[ReadOnly_Point, Writeable_Discrete_Point]:
        """Get (readback, write) points for a control point ID
        
        Args:
            cp_id: Control point ID in format 'controller/name'
            
        Returns:
            Tuple of (readback point, write point)
        """
        controller, name = cp_id.split('/')
        cp_dict = self.points["microcontrollers"][controller]["control_points"][name]
        rb_point = cp_dict["readback"]
        write_point = cp_dict["write"]
        
        return (rb_point, write_point)

    def build_driver_points(self, driver_name: str, state_names: list[str]) -> None:
        """Create driver status points for FSM monitoring"""
        driver_config = self._points_config["drivers"][driver_name]["sensors"]["status"]
        
        # Create state point using existing UUID
        state_config = driver_config["state"]
        state_value = make_value("driver state", state_config)
        assert isinstance(state_value, Discrete_Value)  # Type check
        settings = self.get_point_settings('state')
        state_point = Writeable_Discrete_Point(state_value, **settings)
        self.update_uuid_lookup(state_value.uuid, state_point)
        
        # Create time point using existing UUID  
        time_config = driver_config["time_in_state"]
        time_value = make_value("state time", time_config)
        assert isinstance(time_value, Continuous_Value)  # Type check
        settings = self.get_point_settings('state_time')
        time_point = FSM_StateTimePoint(value_class=time_value, time_provider=None, **settings)
        self.update_uuid_lookup(time_value.uuid, time_point)

    def build_governor_points(self) -> dict:
        """Build governor command points"""
        points = {"governors": defaultdict(dict)}
        governor_name = self._settings["governor"]["name"]
        
        valid_states = (self._points_config["drivers"][self._settings["driver"]["name"]]
                       ["sensors"]["status"]["state"]["valid_values"])
        
        topic = f"mush/governors/{governor_name}/commands/state"
        value = Discrete_Value(
            uuid=self._points_config["governors"][governor_name]["commands"]["state"]["UUID"],
            addr=topic,
            init_raw=valid_states[0],
            description="State command",
            valid_values=valid_states
        )
        point = make_command_point(value)
        points["governors"][governor_name]["state"] = point
        self.update_uuid_lookup(value.uuid, point)
        #adding governor state command to the set of topics to subscribe to
        self._topics_to_subscribe.add(topic)
        
        return points

class Active_Points_Manager(Points_Manager):
    """Points Manager with MQTT capabilities"""
    def __init__(self, base_manager: Points_Manager, message_publisher: MessagePublisher):
        # Inherit all attributes from base manager
        self.__dict__.update(base_manager.__dict__)
        self._publisher = message_publisher
        self._subscribed_points = set()
        self._published_points = set()
        self._last_periodic_publish = datetime.now()
        self._pending_publishes = {}  # topic -> (expected_value, time_requested)
        #Points that were flagged during construction as needing to be monitored    
        self.add_monitored_points(read_points=self._topics_to_subscribe, write_points=set())

    def add_monitored_points(self, read_points: set[str], write_points: set[str]):
        """Add points to monitor by their topics"""
        self._subscribed_points.update(read_points)
        self._published_points.update(write_points)
        self._subscribe_points()

    def _subscribe_points(self):
        """Subscribe to monitored ReadOnly points"""
        for topic in self._subscribed_points:
            self._publisher.subscribe(topic)

    def publish_point(self, point: Writable_Point, force: bool = False) -> None:
        """Publish a point's value with retry logic"""
        now = datetime.now()
        
        # Check if we need to publish
        if not force and point.value == point.requested_value:
            return
        
        # Check retry interval for pending publishes
        if point.addr in self._pending_publishes:
            _, time_requested = self._pending_publishes[point.addr]
            if (now - time_requested).total_seconds() < point.retry_interval:
                return  # Too soon to retry
        
        # Attempt publish
        success = self._publisher.publish(point.addr, point.requested_value)
        if success:
            self._pending_publishes[point.addr] = (point.requested_value, now)
        

    def handle_mqtt_message(self, topic: str, value: Any):
        """Called when any subscribed topic receives a message"""
        # First update the point's value
        point = self.get_point_by_topic(topic)
        point.value_class.value = value  # This will set is_initialized to True
        
        # Then handle any pending publish confirmations
        if topic in self._pending_publishes:
            assert isinstance(point, Writable_Point)
            expected_value, time_requested = self._pending_publishes[topic]
            if value == expected_value:
                # Success! Value confirmed
                point._time_last_published = datetime.now()
                del self._pending_publishes[topic]

    def periodic_publish(self):
        """Retry any unconfirmed publishes and handle regular republishing"""
        now = datetime.now()
        
        # Check regular periodic publishes
        for topic in self._published_points:
            point = self.get_point_by_topic(topic)
            if isinstance(point, Writable_Point):
                point.pre_publish()  # This will update time_in_state for FSM_StateTimePoint
                time_since_publish = (now - point._time_last_published).total_seconds()
                if time_since_publish >= point.republish_frequency:
                    self.publish_point(point, force=True)

        # Check pending publishes for retry using point's retry interval
        for topic, (value, time_requested) in list(self._pending_publishes.items()):
            point = self.get_point_by_topic(topic)
            assert isinstance(point, Writable_Point)
            if (now - time_requested).total_seconds() >= point.retry_interval:
                self.publish_point(point, force=True)