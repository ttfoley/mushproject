# common/governor/point_manager.py

import time
from typing import Dict, Any, Optional, Tuple

# Import the core interfaces we defined
from ..core.core_points import BasePoint, CoreWritablePoint # Assuming relative import works
from ..core.mqtt_interface import MQTTInterface, MessageHandler
from datetime import datetime # Needed for get_point_snapshot

# Placeholder for concrete Point/Value classes - we'll need these later
# from ..core.implementations import ...

class GovernorPointManager:
    """
    Manages the runtime state of Governor-relevant points,
    handles MQTT subscriptions for inputs, and orchestrates
    outgoing publishes based on requested values and internal policies
    (retries, republishing).

    NOTE: This version assumes its `update()` method is called periodically
    by an external loop (e.g., GovernorRunner). It does not manage its own thread.
    """
    def __init__(self, config_data: Dict, mqtt_handler: MQTTInterface):
        """
        Initializes the Point Manager.

        Args:
            config_data: The validated configuration dictionary for the governor.
            mqtt_handler: An object implementing the MQTTInterface.
        """
        self._config_data = config_data
        self._mqtt_handler = mqtt_handler

        self._points_by_uuid: Dict[int, BasePoint] = {}
        self._points_by_topic: Dict[str, BasePoint] = {}
        self._pending_publishes: Dict[str, Any] = {} # Track points needing publish/retry {topic: requested_value}
        self._last_publish_attempt_time: Dict[str, float] = {} # Track time for retries (using time.monotonic())
        self._last_successful_publish_time: Dict[str, float] = {} # Track time for republish (using time.monotonic())

        # No thread management needed in this version
        # No locks needed here if GR and GPM update run in same thread sequentially

        # Call setup_points during initialization
        self.setup_points()

    def setup_points(self):
        """
        Creates point instances from config, populates registries,
        and sets up MQTT subscriptions using self._mqtt_handler.
        (Requires concrete CorePoint/CoreValue classes to be implemented later)
        """
        print("GPM: Setting up points...")
        # --- Logic from previous discussion ---
        # 1. Initialize registries (done in __init__)
        # 2. Process Governor-Defined Points from self._config_data
        #    - Instantiate CONCRETE CoreValue & CorePoint (NEEDS IMPLEMENTATION)
        #    - Register point in self._points_by_uuid / self._points_by_topic
        # 3. Extract Key Point References (e.g., self.sensor_point = ...)
        # 4. Setup MQTT Subscriptions for input points using self._mqtt_handler
        #    - self._mqtt_handler.subscribe(topic)
        #    - self._mqtt_handler.register_message_handler(topic, self.process_incoming_message)
        # --- End Logic ---
        print("GPM: Point setup placeholder complete.")
        pass # Implement fully later

    def process_incoming_message(self, topic: str, payload: str):
        """
        Callback registered with MQTTInterface. Routes incoming messages
        to the appropriate point's update method.
        (This runs in the MQTT background thread - care needed if accessing
         data modified by the main GR/GPM thread, but maybe okay for just updating points)
        """
        # print(f"GPM: Received MQTT - Topic: {topic}, Payload: {payload}") # Reduce noise for now
        if topic in self._points_by_topic:
            point = self._points_by_topic[topic]
            try:
                # No lock needed here IF point internal state update IS thread-safe
                # OR if the main loop only READS values infrequently and staleness is checked.
                # Let's assume BaseValue.try_update handles its internal state safely for now.
                success, _ = point.handle_incoming_update(payload)
                if not success:
                    print(f"GPM Warning: Failed to update point {topic} with payload {payload}")
                # Optionally: Check if this incoming message confirms a pending publish
                self._check_publish_confirmation(topic, payload)
            except Exception as e:
                print(f"GPM Error processing message for topic {topic}: {e}")
        else:
            print(f"GPM Warning: Received message for unmanaged topic: {topic}")

    def update_requested_value(self, point_uuid_or_addr: int | str, value: Any):
        """
        Called by external logic (e.g., GovernorRunner) to set the
        desired state for a writable point.
        (This runs in the caller's thread, e.g., GovernorRunner's main thread)
        """
        point = None
        # No lock needed here since GR thread calls this and GPM update sequentially
        try:
            if isinstance(point_uuid_or_addr, int):
                point = self._points_by_uuid.get(point_uuid_or_addr)
            else:
                point = self._points_by_topic.get(point_uuid_or_addr)

            # Use isinstance for type narrowing - satisfies linters
            if point and isinstance(point, CoreWritablePoint):
                 current_req = point.requested_value
                 if value != current_req:
                     # print(f"GPM: Updating requested value for {point.addr} to {value}") # Reduce noise
                     success = point.set_requested_value(value)
                     if not success:
                         print(f"GPM Warning: Failed to set requested value {value} for point {point.addr}")
                     else:
                         # Mark this point as needing a potential publish check in the next update() cycle
                         self._pending_publishes[point.addr] = value
            elif point:
                 print(f"GPM Warning: Point {point.addr} ({type(point).__name__}) is not writable.")
            else:
                 print(f"GPM Warning: Point not found for identifier: {point_uuid_or_addr}")
        except Exception as e:
            print(f"GPM Error updating requested value for {point_uuid_or_addr}: {e}")

    def update(self):
        """
        Core periodic logic executed by the calling loop (e.g., GovernorRunner).
        Checks points, initiates publishes, handles retries/republishes.
        """
        now = time.monotonic()
        
        # Process points marked for immediate check due to requested value change
        points_to_publish_now = self._pending_publishes.copy()
        self._pending_publishes.clear() # Assume we try to handle them now

        # Combine check: points needing immediate publish + all other writable points
        points_to_check = set(points_to_publish_now.keys())
        for addr, point in self._points_by_topic.items():
             if isinstance(point, CoreWritablePoint): # Check all writable points
                 points_to_check.add(addr)

        for addr in points_to_check:
            point = self._points_by_topic.get(addr)
            if not point or not isinstance(point, CoreWritablePoint):
                 continue # Should not happen if registry is correct

            req_value = point.requested_value
            republish_freq = point.republish_frequency
            retry_interval = point.retry_interval
            last_attempt_time = self._last_publish_attempt_time.get(addr)
            last_success_time = self._last_successful_publish_time.get(addr)

            needs_publish = False
            # Reason 1: Explicitly requested change detected
            if addr in points_to_publish_now and points_to_publish_now[addr] == req_value:
                 needs_publish = True
                 # print(f"GPM Update: Detected requested change for {addr} to {req_value}")

            # Reason 2: Retry interval elapsed for an unconfirmed publish
            is_unconfirmed = self._is_publish_unconfirmed(addr, req_value) # Needs implementation
            if is_unconfirmed and retry_interval is not None and last_attempt_time is not None:
                if (now - last_attempt_time) >= retry_interval:
                     needs_publish = True
                     # print(f"GPM Update: Retrying publish for {addr} (value: {req_value})")

            # Reason 3: Periodic republish interval elapsed
            if not needs_publish and republish_freq is not None and last_success_time is not None:
                 if (now - last_success_time) >= republish_freq:
                     needs_publish = True
                     # print(f"GPM Update: Periodic republish for {addr} (value: {req_value})")

            # Perform publish if needed
            if needs_publish and req_value is not None:
                # print(f"GPM Update: Attempting publish {addr} = {req_value}")
                self._last_publish_attempt_time[addr] = now
                success = self._mqtt_handler.publish(addr, req_value)
                if success:
                     # Assume success for now, update confirmation logic later
                     self._last_successful_publish_time[addr] = now
                     # Clear from pending if explicit request succeeded
                     if addr in points_to_publish_now and points_to_publish_now[addr] == req_value:
                          del points_to_publish_now[addr] # No longer pending explicit request
                else:
                     print(f"GPM Warning: MQTT publish call failed for {addr}")
                     # Re-add to pending if explicit request's publish call failed
                     if addr in points_to_publish_now:
                          self._pending_publishes[addr] = req_value


    def _check_publish_confirmation(self, topic: str, payload: str):
        """Placeholder: Logic to check if an incoming message confirms a prior command."""
        # Example: If topic is driver status and payload matches commanded value,
        # update internal state to mark command publish as successful/confirmed.
        # This would influence self._is_publish_unconfirmed().
        pass

    def _is_publish_unconfirmed(self, topic: str, requested_value: Any) -> bool:
         """Placeholder: Check if the last publish attempt for this topic/value needs confirmation."""
         # Compare requested_value with driver_status_point.value? Check timestamps?
         # Needs proper implementation based on confirmation strategy.
         return False # Defaulting to "confirmed" for now to avoid infinite retries

    # --- Public Getter Methods ---

    def get_point_value(self, identifier: int | str) -> Any | None:
        """Gets the current valid value of a point."""
        point = self._get_point(identifier)
        # Assume reading point.value is safe enough without lock for now
        # since MQTT updates value, GR reads value sequentially with GPM update
        return point.value if point else None

    def get_point_snapshot(self, identifier: int | str) -> Tuple[Any | None, datetime | None, bool]:
         """Gets a snapshot of the point's state (value, timestamp, validity)."""
         point = self._get_point(identifier)
         # Assume reading multiple properties is safe enough without lock for now
         if point:
             return point.value, point.last_update_time, point.is_valid
         return None, None, False

    # --- Internal Helper ---

    def _get_point(self, identifier: int | str) -> BasePoint | None:
         """Internal helper to get point by UUID or topic."""
         if isinstance(identifier, int):
             return self._points_by_uuid.get(identifier)
         else:
             return self._points_by_topic.get(identifier)