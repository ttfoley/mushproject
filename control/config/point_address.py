from typing import Optional

class PointAddress:
    """Represents a point's location in the configuration hierarchy"""
    @classmethod
    def make_sensor_address(cls, controller: str, sensor: str, reading: str) -> str:
        return f"mush/controllers/{controller}/sensors/{sensor}/{reading}"
    
    @classmethod
    def make_control_point_address(cls, controller: str, cp_name: str, access_type: str) -> str:
        return f"mush/controllers/{controller}/control_points/{cp_name}/{access_type}"

    @classmethod
    def make_driver_address(cls, driver: str, category: str, name: str) -> str:
        return f"mush/drivers/{driver}/{category}/{name}"

    def __init__(self, address: str):
        parts = address.split('/')
        if parts[1] == "controllers":
            self.type = "microcontroller"
            self.controller = parts[2]
            self.point_type = parts[3]  # control_points or sensors
            self.name = parts[4]
            self.access_type = parts[5] if len(parts) > 5 else None  # readback/write for control points, None for sensors
        elif parts[1] == "drivers":
            self.type = "driver"
            self.driver = parts[2]
            self.category = parts[3]  # status or command
            self.name = parts[4]

    def add_to_config(self, config: dict, point_config: dict):
        """Add point config to the right place in config structure"""
        if self.type == "microcontroller":
            if self.controller not in config["microcontrollers"]:
                config["microcontrollers"][self.controller] = {
                    "control_points": {}, 
                    "sensors": {}
                }
            target = config["microcontrollers"][self.controller][self.point_type]
            if self.name not in target:
                target[self.name] = point_config 