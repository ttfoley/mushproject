from collections import defaultdict
from typing import Dict,Any, List
from points import Point,ReadOnly_Point,Writable_Point,ControlPoint,Writeable_Discrete_Point,FSM_StateTimePoint
from values import Value,Discrete_Value,Continuous_Value
from datetime import datetime
from mqtt_handler import MQTTHandler
from points_core import PointsRegistry

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


class PointsMessenger:
    """Handles MQTT messaging for points - publishing, monitoring, and message handling"""
    def __init__(self, registry: PointsRegistry, mqtt_handler: MQTTHandler, settings: dict):
        self.registry = registry
        self._publisher = mqtt_handler
        self._settings = settings
        self.driver_name = settings["driver"]["name"]
        
        # MQTT state
        self._subscribed_points = set()
        self._published_points = set()
        self._last_periodic_publish = datetime.now()
        self._pending_publishes = {}

        # Register with MQTT handler
        self._publisher.register_connect_handler(self._subscribe_points)
        
        # Initialize MQTT monitoring and publishing
        self._initialize_points()

    def _initialize_points(self):
        """Initialize points for monitoring and publishing"""
        # Set up monitoring
        points_to_monitor = self._collect_points_to_monitor()
        self.subscribe_to_points(points_to_monitor)
        
        # Set up publishing for writable points
        for point in self.registry._points_lookup.values():
            if isinstance(point, Writable_Point):
                self._published_points.add(point.addr)

    def _collect_points_to_monitor(self) -> set[str]:
        """Determine which points need to be monitored"""
        points_to_monitor = set()
        
        # Add control point readbacks
        for controller in self.registry.control_points:
            for cp in self.registry.control_points[controller].values():
                points_to_monitor.add(cp.readback_point.addr)

        # Add driver command point if governor needed
        if self._settings["driver"].get("needs_governor", False):
            command_topic = f"mush/drivers/{self.driver_name}/command/state"
            print(f"Setting up command topic subscription: {command_topic}")
            points_to_monitor.add(command_topic)

        return points_to_monitor

    def subscribe_to_points(self, points: set[str]):
        """Subscribe to points we need to monitor"""
        self._subscribed_points.update(points)
        # Register handlers for new points
        for topic in points:
            self._publisher.register_message_handler(topic, self.handle_mqtt_message)
        self._subscribe_points()

    def _subscribe_points(self):
        """Subscribe to monitored ReadOnly points"""
        for topic in self._subscribed_points:
            self._publisher.subscribe(topic)

    def publish_point(self, point: Writable_Point, force: bool = False) -> None:
        """Publish a point's value with retry logic"""
        now = datetime.now()
        
        print(f"Points Messenger - Attempting publish to {point.addr}: {point.requested_value}")
        
        # Check if we need to publish
        if not force and point.value == point.requested_value:
            print(f"Points Messenger - Skipping publish to {point.addr} (values match)")
            return
        
        # Check retry interval for pending publishes
        if point.addr in self._pending_publishes:
            _, time_requested = self._pending_publishes[point.addr]
            if (now - time_requested).total_seconds() < point.retry_interval:
                print(f"Points Messenger - Too soon to retry {point.addr}")
                return  # Too soon to retry
        
        # Attempt publish
        success = self._publisher.publish(point.addr, point.requested_value)
        if success:
            point._time_last_published = datetime.now()
        else:
            # Add to pending publishes for retry
            self._pending_publishes[point.addr] = (point.requested_value, now)

    def handle_mqtt_message(self, topic: str, value: str):
        """Handle incoming MQTT message"""
        if "readback" not in topic:  # Only print non-readback messages
            print(f"MQTT message received - topic: {topic}, value: {value}")
        point = self.registry.get_point_by_topic(topic)
        point.value_class.value = value

        # Handle pending publishes
        if topic in self._pending_publishes:
            expected_value, time_requested = self._pending_publishes[topic]
            if value == expected_value:
                assert isinstance(point, Writable_Point)
                point._time_last_published = datetime.now()
                del self._pending_publishes[topic]

    def periodic_publish(self):
        """Retry any unconfirmed publishes and handle regular republishing"""
        now = datetime.now()
        
        # Check regular periodic publishes
        for topic in self._published_points:
            point = self.registry.get_point_by_topic(topic)
            if isinstance(point, Writable_Point):
                point.pre_publish()  # This will update time_in_state for FSM_StateTimePoint
                time_since_publish = (now - point._time_last_published).total_seconds()
                if time_since_publish >= point.republish_frequency:
                    self.publish_point(point, force=True)

        # Check pending publishes for retry using point's retry interval
        for topic, (value, time_requested) in list(self._pending_publishes.items()):
            point = self.registry.get_point_by_topic(topic)
            assert isinstance(point, Writable_Point)
            if (now - time_requested).total_seconds() >= point.retry_interval:
                self.publish_point(point, force=True)

