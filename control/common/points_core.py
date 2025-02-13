from typing import Dict, Any, Tuple, List
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
from dataclasses import dataclass

@dataclass
class ControlPointInfo:
    """Information needed to register a control point"""
    controller: str
    name: str
    point: ControlPoint

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
    def __init__(self, settings: dict):
        self._points_lookup = {}  # uuid -> Point
        self._topic_lookup = {}   # topic -> uuid
        self._control_points = {} # controller -> name -> ControlPoint
        self._uuids = []
        self._settings = settings
        self.driver_name = settings["driver"]["name"]

    def register_point(self, point: Point):
        """Register a point in the lookup tables"""
        uuid = point.uuid
        if uuid not in self._points_lookup:
            self._points_lookup[uuid] = point
            self._topic_lookup[point.addr] = uuid
            self._uuids.append(uuid)

    def register_control_point(self, cp_info: ControlPointInfo):
        """Register a control point"""
        if cp_info.controller not in self._control_points:
            self._control_points[cp_info.controller] = {}
        self._control_points[cp_info.controller][cp_info.name] = cp_info.point

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

    @property
    def state_point(self) -> Point:
        """Get the driver's state point"""
        return self.get_point_by_topic(f"mush/drivers/{self.driver_name}/status/state")

    @property 
    def state_time_point(self) -> Point:
        """Get the driver's state time point"""
        point = self.get_point_by_topic(f"mush/drivers/{self.driver_name}/status/state_time")
        assert isinstance(point, FSM_StateTimePoint)
        return point

class PointsBuilder:
    """Handles construction of points from configuration"""
    def __init__(self, full_config: dict, settings: dict):
        self.full_config = full_config
        self.settings = settings
        self.driver_name = settings["driver"]["name"]
        self._uuid_db = UUIDDatabase()

    def build_points_from_config(self) -> Tuple[List[Point], List[ControlPointInfo]]:
        """Build points from configuration and return structures for registration
        Returns:
            points_to_register: Flat list of points to register
            control_points: List of ControlPointInfo objects to register
        """
        points_to_register: List[Point] = []
        control_points: List[ControlPointInfo] = []

        # Build microcontroller points
        if "microcontrollers" in self.full_config:
            self._build_points_section(
                self.full_config["microcontrollers"], 
                points_to_register, 
                control_points
            )

        # Build driver points - different structure
        if "drivers" in self.full_config:
            _ = self._build_driver_section(  # Ignore returned dict
                self.full_config["drivers"],
                points_to_register
            )
        
        return points_to_register, control_points

    def _build_points_section(self, config: dict, points_to_register: List[Point], 
                            control_points: List[ControlPointInfo]) -> None:
        """Build points from any config section (microcontrollers or drivers)"""
        for controller, controller_dict in config.items():
            # Build sensors if present
            if "sensors" in controller_dict:
                self._build_sensors(
                    controller, controller_dict["sensors"], points_to_register
                )
                
            # Build control points if present    
            if "control_points" in controller_dict:
                self._build_control_points(
                    controller, controller_dict["control_points"], 
                    points_to_register, control_points
                )

    def _build_sensors(self, controller: str, sensors_dict: dict, points_to_register: List[Point]) -> None:
        """Build sensors for a controller"""
        for sensor_name, sensor_dict in sensors_dict.items():
            for reading_type, reading_dict in sensor_dict.items():
                value = make_value(f"microcontroller:{controller} {sensor_name} {reading_type}", reading_dict)
                point = make_sensor_point(value)
                points_to_register.append(point)

    def _build_control_points(self, controller: str, control_points_dict: dict, points_to_register: List[Point], control_points: List[ControlPointInfo]) -> None:
        """Build control points for a controller"""
        for cp_name, cp_dict in control_points_dict.items():
            readback_point = None
            write_point = None
            for rb_or_w in ["readback", "write"]:
                desc = f"{controller} {cp_name} {rb_or_w}"
                value = make_value(desc, cp_dict[rb_or_w])
                if rb_or_w == "readback":
                    readback_point = ReadOnly_Point(value)
                    points_to_register.append(readback_point)
                else:
                    assert isinstance(value, Discrete_Value)
                    write_point = Writeable_Discrete_Point(value)
                    points_to_register.append(write_point)
            
            assert write_point is not None and readback_point is not None
            cp = ControlPoint(
                write_point,
                readback_point
            )
            control_points.append(ControlPointInfo(controller, cp_name, cp))

    def _build_driver_section(self, drivers_config: dict, points_to_register: List[Point]) -> dict:
        """Build driver points which have a different structure from microcontroller points"""
        points = defaultdict(dict)
        
        for driver_name, driver_dict in drivers_config.items():
            points[driver_name] = defaultdict(dict)
            
            # Build status points
            if "status" in driver_dict:
                points[driver_name]["status"] = {}
                for point_name, point_config in driver_dict["status"].items():
                    value = make_value(f"driver:{driver_name} status {point_name}", point_config)
                    if point_name == "state_time":
                        assert isinstance(value, Continuous_Value), "state_time value must be Continuous_Value"
                        point = FSM_StateTimePoint(value)
                    else:
                        assert isinstance(value, Discrete_Value), "state value must be Discrete_Value"
                        point = Writeable_Discrete_Point(value)
                    points[driver_name]["status"][point_name] = point
                    points_to_register.append(point)

            # Build command points
            if "command" in driver_dict:
                points[driver_name]["command"] = {}
                for point_name, point_config in driver_dict["command"].items():
                    value = make_value(f"driver:{driver_name} command {point_name}", point_config)
                    assert isinstance(value, Discrete_Value), "command value must be Discrete_Value"
                    point = make_command_point(value)
                    points[driver_name]["command"][point_name] = point
                    points_to_register.append(point)

        return points 