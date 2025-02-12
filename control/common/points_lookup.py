from typing import Dict, Any, Tuple
from points import (
    Point, 
    Writable_Point, 
    ControlPoint, 
    ReadOnly_Point, 
    Writeable_Discrete_Point,
    FSM_StateTimePoint
)
from collections import defaultdict
from values import Value, Discrete_Value, Continuous_Value
from config.uuid_database import UUIDDatabase

def make_value(description, value_dict) -> Value:
    uuid, addr = value_dict["UUID"], value_dict["addr"]
    if "valid_range" in value_dict:
        valid_range = value_dict["valid_range"]
        init_raw = valid_range["lower"]
        value_class = Continuous_Value(uuid, addr, init_raw, description, valid_range)
        return value_class

    elif "valid_values" in value_dict:
        valid_values = value_dict["valid_values"]
        init_raw = valid_values[0]
        value_mapper = {}
        if "value_mapper" in value_dict:
            value_mapper = value_dict["value_mapper"]
        value_class = Discrete_Value(uuid, addr, init_raw, description, valid_values, value_mapper=value_mapper)
        return value_class

    else:
        raise ValueError("Couldn't infer value type (discrete or continuous) from valid_values or valid_range")
    
def make_sensor_point(value: Value) -> Point:
    """Create a read-only point for microcontroller sensors"""
    return ReadOnly_Point(value)

def make_command_point(value: Value) -> Point:
    """Create a read-only point for governor commands"""
    return ReadOnly_Point(value)

class PointsRegistry:
    """Central registry for looking up points by UUID, topic, or control point path"""
    def __init__(self):
        self._points_lookup = {}  # uuid -> Point
        self._topic_lookup = {}   # topic -> uuid
        self._control_points = {} # controller -> name -> ControlPoint
        self._uuids = []

    def register_point(self, point: Point):
        """Register a point in the lookup tables"""
        uuid = point.uuid
        if uuid not in self._points_lookup:
            self._points_lookup[uuid] = point
            self._topic_lookup[point.addr] = uuid
            self._uuids.append(uuid)

    def register_control_point(self, controller: str, name: str, cp):
        """Register a control point"""
        if controller not in self._control_points:
            self._control_points[controller] = {}
        self._control_points[controller][name] = cp

    def get_point(self, uuid: int) -> Point:
        return self._points_lookup[uuid]

    def get_point_by_topic(self, topic: str) -> Point:
        if topic not in self._topic_lookup:
            raise ValueError(f"No point found for topic: {topic}")
        return self._points_lookup[self._topic_lookup[topic]]

    def get_control_point_pair(self, cp_id: str):
        """Get (readback, write) points for a control point ID"""
        controller, name = cp_id.split('/')
        cp = self._control_points[controller][name]
        return (cp.readback_point, cp.write_point)

    @property
    def control_points(self):
        return self._control_points

    def value_exists(self, uuid: int) -> bool:
        return uuid in self._points_lookup

class PointsBuilder:
    """Handles construction of points from configuration"""
    def __init__(self, points_config: dict, settings: dict):
        self.points_config = points_config
        self.settings = settings
        self.driver_name = settings["driver"]["name"]
        self._uuid_db = UUIDDatabase()
        self.registry = PointsRegistry()

    def build_all(self) -> Tuple[dict, PointsRegistry]:
        """Build all points and register them"""
        points = self.build_microcontroller_points()
        return points, self.registry

    def build_microcontroller_points(self) -> dict:
        """First creates all values according to the initial points config file.
        Then makes all physical control points and sensors.
        When building valueclasses, should infer whether they are continuous or discrete based on valid_values or valid_range.
        Updates UUID lookup with all values.
        """
        source = self.points_config["microcontrollers"]
        points = {"microcontrollers": defaultdict(dict)}

        for controller, controller_dict in source.items():
            points["microcontrollers"][controller] = defaultdict(dict)
            controller_points = points["microcontrollers"][controller]

            if "sensors" in controller_dict:
                controller_points["sensors"] = defaultdict(dict)
                for sensor_name, sensor_dict in controller_dict["sensors"].items():
                    controller_points["sensors"][sensor_name] = defaultdict(dict)
                    for reading_type, reading_dict in sensor_dict.items():
                        value = make_value(f"microcontroller:{controller} {sensor_name} {reading_type}", reading_dict)
                        point = make_sensor_point(value)
                        controller_points["sensors"][sensor_name][reading_type] = point
                        self.registry.register_point(point)

            if "control_points" in controller_dict:
                controller_points["control_points"] = defaultdict(dict)
                for cp_name, cp_dict in controller_dict["control_points"].items():
                    for rb_or_w in ["readback", "write"]:
                        desc = f"{controller} {cp_name} {rb_or_w}"
                        value = make_value(desc, cp_dict[rb_or_w])
                        if rb_or_w == "readback":
                            point = ReadOnly_Point(value)
                            controller_points["control_points"][cp_name]["readback"] = point
                            self.registry.register_point(point)
                        else:
                            assert isinstance(value, Discrete_Value)
                            point = Writeable_Discrete_Point(value)
                            controller_points["control_points"][cp_name]["write"] = point
                            self.registry.register_point(point)
                    
                    # Create and register control point
                    cp = ControlPoint(
                        controller_points["control_points"][cp_name]["write"],
                        controller_points["control_points"][cp_name]["readback"]
                    )
                    self.registry.register_control_point(controller, cp_name, cp)

        return points

    def build_driver_points(self, states_config: dict) -> None:
        """Create all points for a driver"""
        base_topic = f"mush/drivers/{self.driver_name}"
        state_names = list(states_config.keys())
        
        # State readback point
        state_topic = f"{base_topic}/status/state"
        state_uuid = self._uuid_db.get_uuid(state_topic)
        state_value = Discrete_Value(
            uuid=state_uuid,
            addr=state_topic,
            init_raw="unknown",
            description="driver state",
            valid_values=state_names + ["unknown"]
        )
        state_point = Writeable_Discrete_Point(state_value)
        self.registry.register_point(state_point)
        
        # State time point
        time_topic = f"{base_topic}/status/state_time"
        time_uuid = self._uuid_db.get_uuid(time_topic)
        time_value = Continuous_Value(
            uuid=time_uuid,
            addr=time_topic,
            raw_value=0,
            description="state time",
            valid_range={"lower": 0, "upper": 1000000}
        )
        time_point = FSM_StateTimePoint(time_value)
        self.registry.register_point(time_point)
        
        # Command point
        command_topic = f"{base_topic}/command/state"
        command_uuid = self._uuid_db.get_uuid(command_topic)
        command_value = Discrete_Value(
            uuid=command_uuid,
            addr=command_topic,
            init_raw=state_names[0],
            description="state command",
            valid_values=state_names
        )
        command_point = make_command_point(command_value)
        self.registry.register_point(command_point) 