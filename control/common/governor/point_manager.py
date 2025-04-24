# control/common/governor/point_manager.py

import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List, Set

# Core interfaces and concrete implementations
try:
    from ..core.core_points import BasePoint, CoreWritablePoint
    from ..core.core_values import BaseValue
    from ..core.mqtt_interface import MQTTInterface
    from ..core.implementations.value_implementations import CoreConcreteDiscreteValue, CoreConcreteContinuousValue
    from ..core.implementations.point_implementations import CoreConcreteReadOnlyPoint, CoreConcreteWritablePoint
    # Import GovernorConfiguration to type hint config_object
    from .config import GovernorConfiguration, GovernorConfigurationError
except ImportError:
    # Fallback imports - adjust as needed
    # This block assumes the script might be run in a context where 'common' is not directly importable
    # and attempts to add the parent-of-parent directory (likely 'control') to the path.
    # A more robust solution involves proper package installation or PYTHONPATH setup.
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..')) # Add control/
    from common.core.core_points import BasePoint, CoreWritablePoint
    from common.core.core_values import BaseValue
    from common.core.mqtt_interface import MQTTInterface
    from common.core.implementations.value_implementations import CoreConcreteDiscreteValue, CoreConcreteContinuousValue
    from common.core.implementations.point_implementations import CoreConcreteReadOnlyPoint, CoreConcreteWritablePoint
    from common.governor.config import GovernorConfiguration, GovernorConfigurationError


# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GovernorPointManagerError(Exception):
    """Custom exception for GPM errors."""
    pass


class GovernorPointManager:
    """
    Manages the runtime state of Governor-relevant points,
    handles MQTT subscriptions for inputs, and orchestrates
    outgoing publishes based on requested values and internal policies
    (retries, republishing).

    NOTE: This version assumes its `update()` method is called periodically
    by an external loop (e.g., GovernorRunner). It does not manage its own thread.
    """
    def __init__(self, config_object: GovernorConfiguration, mqtt_handler: MQTTInterface):
        """
        Initializes the Point Manager.

        Args:
            config_object: A fully loaded and validated GovernorConfiguration object.
            mqtt_handler: An object implementing the MQTTInterface.
        """
        assert isinstance(config_object, GovernorConfiguration), "config_object must be a GovernorConfiguration instance."
        # Basic check for MQTTInterface compliance
        assert hasattr(mqtt_handler, 'publish') and hasattr(mqtt_handler, 'subscribe') \
               and hasattr(mqtt_handler, 'register_message_handler'), "mqtt_handler must implement MQTTInterface."

        self._config = config_object
        self._mqtt_handler = mqtt_handler

        # Point Registries
        self._points_by_uuid: Dict[int, BasePoint] = {}
        self._points_by_topic: Dict[str, BasePoint] = {}

        # State for publishing logic
        self._pending_publishes: Dict[str, Any] = {} # topic: requested_value (for immediate publish/retry)
        self._last_publish_attempt_time: Dict[str, float] = {} # topic: monotonic_time
        self._last_successful_publish_time: Dict[str, float] = {} # topic: monotonic_time
        self._pending_confirmation: Dict[str, Any] = {} # topic: value_to_confirm

        # Call setup_points during initialization
        try:
            self.setup_points()
            logger.info("GovernorPointManager initialized successfully.")
        except Exception as e:
            logger.error(f"Error during GovernorPointManager setup: {e}", exc_info=True)
            # Chain the exception for clarity
            raise GovernorPointManagerError(f"Failed GPM setup: {e}") from e

    # --- Point Creation Helper ---
    def _create_point_from_config(self, point_config: Dict[str, Any], point_source_desc: str) -> Optional[BasePoint]:
        """
        Internal helper to create Value and Point instances from a config dict.

        Args:
            point_config: The dictionary defining the point.
            point_source_desc: Description of where the config came from (e.g., "governor", "external").

        Returns:
            The created BasePoint instance, or None if config is invalid.
        """
        try:
            # Basic Validation
            req_keys = ["addr", "UUID", "value_type"] # Desc optional but recommended
            missing = [k for k in req_keys if k not in point_config]
            if missing:
                logger.error(f"Skipping point creation: Missing required keys {missing} in {point_source_desc} config: {point_config.get('addr', 'N/A')}")
                return None

            addr = point_config["addr"]
            uuid = point_config["UUID"]
            value_type_str = point_config["value_type"]
            description = point_config.get("description", f"Point {addr}")
            initial_value = point_config.get("initial_value", None) # Used for gov points

            logger.debug(f"Processing point config (UUID: {uuid}, Addr: {addr}, Type: {value_type_str}) from {point_source_desc}")

            # Check for duplicates before creating
            if uuid in self._points_by_uuid:
                 logger.warning(f"Skipping point creation: Duplicate UUID {uuid} found for address {addr}. Existing point has address {self._points_by_uuid[uuid].addr}.")
                 return None
            if addr in self._points_by_topic:
                 logger.warning(f"Skipping point creation: Duplicate address '{addr}' found for UUID {uuid}. Existing point has UUID {self._points_by_topic[addr].uuid}.")
                 return None

            # Create Value Instance
            value_instance: Optional[BaseValue] = None
            if value_type_str == "discrete":
                valid_values = point_config.get("valid_values")
                value_mapper = point_config.get("value_mapper")
                if not valid_values:
                     logger.error(f"Skipping discrete point {addr}: Missing 'valid_values' in config.")
                     return None
                value_instance = CoreConcreteDiscreteValue(
                    uuid=uuid, addr=addr, valid_values=valid_values,
                    value_mapper=value_mapper, initial_value=initial_value
                )
            elif value_type_str == "continuous":
                valid_range = point_config.get("valid_range")
                py_value_type = float if point_config.get("py_value_type", "float") == "float" else int
                if not valid_range:
                     logger.error(f"Skipping continuous point {addr}: Missing 'valid_range' in config.")
                     return None
                value_instance = CoreConcreteContinuousValue(
                    uuid=uuid, addr=addr, valid_range=valid_range,
                    value_type=py_value_type, initial_value=initial_value
                )
            else:
                logger.error(f"Skipping point {addr}: Unsupported value_type '{value_type_str}'.")
                return None

            # Create Point Instance
            point_instance: Optional[BasePoint] = None
            is_writable = False
            if point_source_desc == "governor": # Governor points are writable (setpoint, deadband)
                 is_writable = True
            else: # Check if external point is an actuator command target
                 strategies = self._config.get_control_strategies_config()
                 for strategy in strategies:
                     settings = strategy.get("settings", {})
                     if settings.get("actuator_command_addr") == addr:
                          is_writable = True
                          logger.info(f"Point {addr} identified as writable actuator command.")
                          break

            if is_writable:
                publish_settings = point_config.get("publish", {})
                default_pub_config = self._config.get_point_manager_config()
                republish = publish_settings.get("republish_frequency", default_pub_config.get("default_republish_frequency"))
                retry = publish_settings.get("retry_interval", default_pub_config.get("default_retry_interval"))
                point_instance = CoreConcreteWritablePoint(
                    value_instance=value_instance,
                    republish_frequency=republish,
                    retry_interval=retry
                )
                logger.info(f"Created Writable Point: UUID={uuid}, Addr={addr}, Republish={republish}s, Retry={retry}s")
            else:
                point_instance = CoreConcreteReadOnlyPoint(value_instance=value_instance)
                logger.info(f"Created ReadOnly Point: UUID={uuid}, Addr={addr}")

            return point_instance

        except Exception as e:
            logger.error(f"Failed to create point from config {point_config.get('addr','N/A')} (Source: {point_source_desc}): {e}", exc_info=True)
            return None

    # --- Setup Method ---
    def setup_points(self):
        """
        Creates point instances from config, populates registries,
        and sets up MQTT subscriptions using self._mqtt_handler.
        """
        logger.info("GPM: Setting up points...")

        gov_points_config, external_points_config = self._config.get_all_point_definitions()
        points_to_subscribe: Set[str] = set()

        # Instantiate Governor-Defined Points
        logger.info(f"Creating {len(gov_points_config)} governor-defined points...")
        for name, point_config in gov_points_config.items():
            point = self._create_point_from_config(point_config, "governor")
            if point:
                self._points_by_uuid[point.uuid] = point
                self._points_by_topic[point.addr] = point
                # Subscribe to governor points to allow external updates (e.g., setpoint changes)
                points_to_subscribe.add(point.addr)
                logger.debug(f"Registered governor point {name} (UUID: {point.uuid}, Addr: {point.addr}) - Will subscribe.")

        # Identify and Instantiate Referenced External Points
        logger.info("Identifying and creating referenced external points...")
        referenced_addrs: Set[str] = set()
        strategies = self._config.get_control_strategies_config()
        for strategy in strategies:
             settings = strategy.get("settings", {})
             for key, addr in settings.items():
                 if key.endswith("_addr") and isinstance(addr, str):
                     referenced_addrs.add(addr)

        logger.info(f"Control strategies reference {len(referenced_addrs)} unique external addresses.")

        def find_external_point_config(addr_to_find: str) -> Optional[Dict]:
            """Searches microC and driver configs for a point definition by address."""
            # Search microcontrollers
            for mc_data in external_points_config.get("microcontrollers", {}).values():
                for s_data in mc_data.get("sensors", {}).values():
                    for r_config in s_data.values():
                        if isinstance(r_config, dict) and r_config.get("addr") == addr_to_find: return r_config
                for cp_data in mc_data.get("control_points", {}).values():
                    for access_type in ["readback", "write"]:
                         if access_type in cp_data and cp_data[access_type].get("addr") == addr_to_find: return cp_data[access_type]
            # Search drivers
            for drv_data in external_points_config.get("drivers", {}).values():
                 for st_config in drv_data.get("status", {}).values():
                      if isinstance(st_config, dict) and st_config.get("addr") == addr_to_find: return st_config
                 for cmd_config in drv_data.get("command", {}).values():
                      if isinstance(cmd_config, dict) and cmd_config.get("addr") == addr_to_find: return cmd_config
            return None

        for addr in referenced_addrs:
            if addr in self._points_by_topic:
                logger.debug(f"Address {addr} already managed. Skipping external creation.")
                continue

            point_config = find_external_point_config(addr)
            if point_config:
                point = self._create_point_from_config(point_config, "external reference")
                if point:
                    self._points_by_uuid[point.uuid] = point
                    self._points_by_topic[point.addr] = point

                    # Determine if input (subscribe) or output (don't subscribe)
                    is_input = any(k in addr for k in ["sensors", "status", "readback"])
                    is_output_cmd = any(s.get("settings",{}).get("actuator_command_addr") == addr for s in strategies)

                    if is_input and not is_output_cmd:
                        points_to_subscribe.add(addr)
                        logger.debug(f"Registered external point (UUID: {point.uuid}, Addr: {addr}) - Will subscribe.")
                    else:
                         logger.debug(f"Registered external point (UUID: {point.uuid}, Addr: {addr}) - Not subscribing (is output/command).")
            else:
                 # This is a configuration error - a referenced point doesn't exist
                 raise GovernorPointManagerError(f"Configuration Error: Referenced address '{addr}' not found in external configs (microC/driver).")

        # Setup MQTT Subscriptions
        logger.info(f"Setting up MQTT subscriptions for {len(points_to_subscribe)} topics...")
        for topic in points_to_subscribe:
            try:
                logger.debug(f"Subscribing to: {topic}")
                self._mqtt_handler.subscribe(topic, qos=1)
                self._mqtt_handler.register_message_handler(topic, self.process_incoming_message)
            except Exception as e:
                 logger.error(f"Failed to subscribe or register handler for topic {topic}: {e}", exc_info=True)
                 # Consider if this should be a fatal error

        logger.info("GPM Point setup complete.")

    # --- Runtime Methods ---
    def process_incoming_message(self, topic: str, payload: str):
        """
        Callback registered with MQTTInterface. Routes incoming messages
        to the appropriate point's handle_incoming_update method.
        """
        logger.debug(f"GPM Received MQTT - Topic: {topic}, Payload: {payload}")
        point = self._points_by_topic.get(topic)
        if point:
            try:
                success, processed_value = point.handle_incoming_update(payload)
                if success:
                    # Pass processed value if available, otherwise raw payload for comparison
                    confirm_val = processed_value if processed_value is not None else payload
                    self._check_publish_confirmation(topic, confirm_val)
                # else: try_update already logs warnings for invalid input
            except Exception as e:
                logger.error(f"GPM Error processing message for topic {topic}: {e}", exc_info=True)
        else:
            logger.warning(f"GPM Received message for unmanaged topic: {topic}")

    def update_requested_value(self, point_uuid_or_addr: int | str, value: Any):
        """
        Called by external logic (e.g., GovernorRunner) to set the
        desired state for a writable point. Validates the value and marks
        the point for publishing if valid.
        """
        point = self._get_point(point_uuid_or_addr)
        if point is None:
            logger.warning(f"Point not found for identifier: {point_uuid_or_addr}")
            return

        if isinstance(point, CoreWritablePoint):
             if point.set_requested_value(value):
                  # Validation passed, value set in point._requested_value
                  self._pending_publishes[point.addr] = point.requested_value
                  logger.info(f"Queued publish for {point.addr} with requested value {point.requested_value}")
             # Else: Validation failed, warning already logged by set_requested_value
        else:
             logger.warning(f"Point {point.addr} (UUID: {point.uuid}) is not writable.")

# Add this method to the GovernorPointManager class
# in control/common/governor/point_manager.py

    def update(self):
        """
        Core periodic logic executed by the calling loop (e.g., GovernorRunner).
        Checks points, initiates publishes, handles retries/republishes.
        NOTE: we may want have update called by some threading mechanism eventually
        """
        now = time.monotonic() # Use monotonic time for interval checks
        # logger.debug("GPM update cycle started.") # Optional: Can be noisy

        # Store actuator command addresses for confirmation logic
        # This could be optimized by storing it once in __init__
        actuator_command_addrs = set()
        for strategy in self._config.get_control_strategies_config():
            addr = strategy.get("settings", {}).get("actuator_command_addr")
            if addr:
                actuator_command_addrs.add(addr)

        # Check all managed points
        # Iterate over a copy of values in case dictionary changes (though unlikely here)
        points_to_check = list(self._points_by_uuid.values())

        for point in points_to_check:
            # Skip points that aren't writable
            if not isinstance(point, CoreWritablePoint):
                continue

            addr = point.addr
            req_value = point.requested_value
            retry_interval = point.retry_interval
            republish_freq = point.republish_frequency

            # Skip if nothing has been requested yet
            if req_value is None:
                # logger.debug(f"Skipping publish for {addr}: requested_value is None.")
                continue

            needs_publish = False
            publish_reason = "None"

            # 1. Check for pending explicit requests
            if addr in self._pending_publishes:
                # Ensure the pending value matches the current requested value
                # (Handles cases where requested value might change quickly)
                if self._pending_publishes[addr] == req_value:
                    needs_publish = True
                    publish_reason = "Pending Request"
                else:
                    # Requested value changed before we could publish the pending one.
                    # Remove the old pending request. The new value will be caught
                    # if needed by retry/republish or set again.
                    logger.debug(f"Stale pending publish removed for {addr}")
                    self._pending_publishes.pop(addr, None)


            # 2. Check for retry if publish is unconfirmed
            # Only check retry if not already triggered by a pending request
            if not needs_publish and retry_interval is not None:
                if self._is_publish_unconfirmed(addr):
                    last_attempt = self._last_publish_attempt_time.get(addr, -1.0)
                    if (now - last_attempt) >= retry_interval:
                        needs_publish = True
                        publish_reason = f"Retry (Unconfirmed > {retry_interval}s)"
                    # else: logger.debug(f"Skipping retry for {addr}: Interval not elapsed.")
                # else: logger.debug(f"Skipping retry for {addr}: Publish not unconfirmed.")


            # 3. Check for periodic republish
            # Only check republish if not already triggered by above reasons
            if not needs_publish and republish_freq is not None and not self._is_publish_unconfirmed(addr):
                last_success_time = self._last_successful_publish_time.get(addr) # Get timestamp or None
                republish_check_passed = False # Default to False

                if last_success_time is None:
                    # If it has never been published successfully, trigger the republish
                    republish_check_passed = True
                    logger.debug(f"Triggering republish for {addr}: Never published successfully before.")
                else:
                    # If it has been published, check the interval
                    if (now - last_success_time) >= republish_freq:
                        republish_check_passed = True
                        logger.debug(f"Triggering republish for {addr}: Interval ({republish_freq}s) elapsed.")
                    # else: logger.debug(f"Skipping republish for {addr}: Interval not elapsed.")

                if republish_check_passed:
                    needs_publish = True
                    publish_reason = f"Periodic Republish (Freq: {republish_freq}s)"


            # --- Perform Publish if Needed ---
            if needs_publish:
                logger.info(f"Publishing for {addr} (Reason: {publish_reason}): Value={req_value}")
                self._last_publish_attempt_time[addr] = now

                # Publish the requested value (convert to string for MQTT)
                # QoS=1 is often appropriate for commands/state updates
                success = self._mqtt_handler.publish(addr, str(req_value), qos=1, retain=False) # Check retain flag usage - usually False for commands

                if success:
                    # Remove from pending list if this publish was for an explicit request
                    self._pending_publishes.pop(addr, None)

                    # Confirmation Strategy:
                    # - Assume immediate success for non-actuator commands (e.g., setpoints)
                    # - Require confirmation for actuator commands
                    if addr in actuator_command_addrs:
                        logger.debug(f"Publish for actuator {addr} requires confirmation. Expecting value: {req_value}")
                        # Mark as pending confirmation with the value we just sent
                        self._pending_confirmation[addr] = req_value
                        # Don't update _last_successful_publish_time until confirmed
                    else:
                        # Assume success for other writable points (like setpoints)
                        logger.debug(f"Assuming immediate success for non-actuator publish: {addr}")
                        self._last_successful_publish_time[addr] = now
                        # Ensure it's not marked as pending confirmation if it somehow was
                        self._pending_confirmation.pop(addr, None)

                else:
                    # Publish call failed immediately (e.g., MQTT client buffer full)
                    logger.warning(f"MQTT publish call failed immediately for topic {addr}.")
                    # If it failed, ensure it stays in _pending_publishes if it was an explicit request
                    # so it gets picked up again on the next cycle.
                    # No need to explicitly re-add, just don't pop it.

        # logger.debug("GPM update cycle finished.") # Optional: Can be noisy

    # --- Confirmation and Retry Logic Helpers ---
    def _check_publish_confirmation(self, topic: str, value: Any):
        """
        Checks if an incoming message confirms a prior command.
        Simple value match for now. Needs refinement based on exact confirmation needs.
        """
        if topic in self._pending_confirmation:
             expected_value = self._pending_confirmation[topic]
             # Attempt string comparison as a basic check
             if str(value) == str(expected_value):
                  logger.info(f"Publish confirmed for topic {topic} with value {value}")
                  self._last_successful_publish_time[topic] = time.monotonic()
                  del self._pending_confirmation[topic]
             # Else: Value doesn't match, maybe log a warning? Or just wait for retry.

    def _is_publish_unconfirmed(self, topic: str) -> bool:
         """Checks if a specific topic is awaiting confirmation."""
         # Basic check: is it in the pending dictionary?
         # More complex logic could involve checking time since last attempt.
         return topic in self._pending_confirmation

    # --- Public Getter Methods ---
    def get_point_value(self, identifier: int | str) -> Any | None:
        """Gets the current valid value of a point."""
        point = self._get_point(identifier)
        return point.value if point else None # point.value handles validity check

    def get_point_snapshot(self, identifier: int | str) -> Tuple[Any | None, datetime | None, bool]:
         """Gets a snapshot of the point's state (value, timestamp, validity)."""
         point = self._get_point(identifier)
         if point:
             return point.value, point.last_update_time, point.is_valid
         return None, None, False

    # --- Internal Helper ---
    def _get_point(self, identifier: int | str) -> BasePoint | None:
         """Internal helper to get point by UUID or topic."""
         if isinstance(identifier, int):
             return self._points_by_uuid.get(identifier)
         elif isinstance(identifier, str):
             return self._points_by_topic.get(identifier)
         else:
              logger.warning(f"Invalid identifier type used to get point: {type(identifier)}")
              return None