# control/common/governor/point_manager.py

import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List, Set, TYPE_CHECKING # Added TYPE_CHECKING, Set

# Core interfaces and concrete implementations (adjust relative paths if needed)
try:
    # Use TYPE_CHECKING for imports only needed for type hints to avoid circular issues
    if TYPE_CHECKING:
        from .config import GovernorConfiguration
        from ..core.mqtt_interface import MQTTInterface

    from ..core.core_points import BasePoint, CoreWritablePoint
    from ..core.core_values import BaseValue
    # Import concrete implementations directly
    from ..core.implementations.value_implementations import CoreConcreteDiscreteValue, CoreConcreteContinuousValue
    from ..core.implementations.point_implementations import CoreConcreteReadOnlyPoint, CoreConcreteWritablePoint

except ImportError as e:
    # Provide more context on import errors
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..')) # Add control/
    logger = logging.getLogger(__name__)
    logger.error(f"ImportError in point_manager.py: {e}. Check paths and file structure.", exc_info=True)
    # Re-importing after path modification might be needed in some execution contexts
    # Or preferably, fix the execution context or use packaging.
    # Attempt re-import after path modification (example, might hide issues)
    try:
        if TYPE_CHECKING:
            from common.governor.config import GovernorConfiguration
            from common.core.mqtt_interface import MQTTInterface
        from common.core.core_points import BasePoint, CoreWritablePoint
        from common.core.core_values import BaseValue
        from common.core.implementations.value_implementations import CoreConcreteDiscreteValue, CoreConcreteContinuousValue
        from common.core.implementations.point_implementations import CoreConcreteReadOnlyPoint, CoreConcreteWritablePoint
    except ImportError:
        logger.critical("Failed to import dependencies even after path adjustment.")
        raise # Re-raise the error if it still fails


# Setup logging
# Configure logging outside the class, usually done at application entry point
# Assuming basic config is done elsewhere, get logger for this module:
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
    """
    # Define _create_point_from_config as a method of the class
    def _create_point_from_config(self, point_config: Dict[str, Any], point_source_desc: str) -> Optional[BasePoint]:
        """
        Internal helper to create Value and Point instances from a config dict.
        Now defined as a method to access self._config if needed for defaults.
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
            initial_value = point_config.get("initial_value", None) # Used for gov points

            logger.debug(f"Processing point config (UUID: {uuid}, Addr: {addr}, Type: {value_type_str}) from {point_source_desc}")

            # Check for duplicates before creating (using self attributes)
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
                value_mapper = point_config.get("value_mapper") # Get potential mapper
                if not valid_values:
                     logger.error(f"Skipping discrete point {addr}: Missing 'valid_values' in config.")
                     return None
                value_instance = CoreConcreteDiscreteValue(
                    uuid=uuid, addr=addr, valid_values=valid_values,
                    value_mapper=value_mapper, initial_value=initial_value
                )
            elif value_type_str == "continuous":
                valid_range = point_config.get("valid_range")
                # Default to float if py_value_type not specified
                py_value_type = float if point_config.get("py_value_type", "float") == "float" else int
                if not valid_range:
                     logger.error(f"Skipping continuous point {addr}: Missing 'valid_range' in config.")
                     return None
                value_instance = CoreConcreteContinuousValue(
                    uuid=uuid, addr=addr, valid_range=valid_range,
                    value_type=py_value_type, initial_value=initial_value
                )
            # Added check for string type - might be used for some commands/status
            elif value_type_str == "string":
                 # String types might not need validation beyond being a string
                 # Or could have length limits etc. in future
                 valid_values = point_config.get("valid_values") # Optional validation list
                 value_instance = CoreConcreteDiscreteValue( # Can reuse discrete for basic string storage
                     uuid=uuid, addr=addr, valid_values=valid_values if valid_values else [], # Pass empty list if no specific values
                     initial_value=initial_value
                 )
                 # Hack: Override internal type if needed, though DiscreteValue handles strings okay
                 # value_instance._value_type = str
            else:
                logger.error(f"Skipping point {addr}: Unsupported value_type '{value_type_str}'.")
                return None

            # Create Point Instance
            point_instance: Optional[BasePoint] = None
            # Determine if the point should be writable
            is_writable = False
            if point_source_desc == "governor":
                is_writable = True # Governor-defined points are typically writable settings
            else: # Check external points
                strategies = self._config.get_control_strategies_config()
                # Is it an actuator command target for any strategy?
                if any(s.get("settings",{}).get("actuator_command_addr") == addr for s in strategies):
                    is_writable = True
                    logger.info(f"Point {addr} identified as writable actuator command.")
                # Could add other conditions for writability here if needed

            if is_writable:
                # Get publish settings from point config, falling back to defaults from main config
                publish_settings = point_config.get("publish", {})
                # Assuming GPM config is stored or accessible via self._config
                # Let's fetch defaults from the main config object if available
                pm_config_defaults = self._config.get_point_manager_config()
                republish = publish_settings.get("republish_frequency", pm_config_defaults.get("default_republish_frequency"))
                retry = publish_settings.get("retry_interval", pm_config_defaults.get("default_retry_interval"))
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


    # --- __init__ Method ---
    def __init__(self, config_object: 'GovernorConfiguration', mqtt_handler: 'MQTTInterface'):
        """
        Initializes the Point Manager.

        Args:
            config_object: A fully loaded and validated GovernorConfiguration object.
            mqtt_handler: An object implementing the MQTTInterface.
        """
        logger.info("Initializing GovernorPointManager...")
        # Assertions to ensure required objects are provided
        if not hasattr(config_object, 'get_all_point_definitions'): # Rough check
             raise TypeError("config_object must provide configuration data (like GovernorConfiguration).")
        if not hasattr(mqtt_handler, 'publish') or not hasattr(mqtt_handler, 'subscribe'): # Rough check
             raise TypeError("mqtt_handler must implement MQTTInterface.")

        self._config = config_object
        self._mqtt_handler = mqtt_handler

        # Point Registries
        self._points_by_uuid: Dict[int, BasePoint] = {}
        self._points_by_topic: Dict[str, BasePoint] = {}

        # State for publishing logic
        # Stores topic: value for publishes triggered by update_requested_value
        self._pending_publishes: Dict[str, Any] = {}
        # Stores topic: monotonic_time of last publish attempt (success or fail)
        self._last_publish_attempt_time: Dict[str, float] = {}
        # Stores topic: monotonic_time of last confirmed successful publish
        self._last_successful_publish_time: Dict[str, float] = {}
         # Stores topic: value awaiting confirmation via incoming message
        self._pending_confirmation: Dict[str, Any] = {}

        # Call setup_points during initialization
        try:
            self.setup_points() # Calls the method below
            logger.info("GovernorPointManager initialized successfully.")
        except Exception as e:
            logger.error(f"Error during GovernorPointManager setup: {e}", exc_info=True)
            raise GovernorPointManagerError(f"Failed GPM setup: {e}") from e


    # --- setup_points Method (with full logging) ---
    def setup_points(self):
        """
        Creates point instances from config, populates registries,
        and sets up MQTT subscriptions using self._mqtt_handler. Includes Debug Logs.
        """
        logger.info("GPM: Setting up points...")

        if not self._config or not self._mqtt_handler:
             raise GovernorPointManagerError("GPM cannot setup points: Config or MQTT handler not initialized.")

        gov_points_config, external_points_config = self._config.get_all_point_definitions()
        points_to_subscribe: Set[str] = set()
        strategies = self._config.get_control_strategies_config() # Needed for checks later

        # Instantiate Governor-Defined Points
        logger.info(f"Creating {len(gov_points_config)} governor-defined points...")
        for name, point_config in gov_points_config.items():
            point = self._create_point_from_config(point_config, "governor")
            if point:
                if point.uuid in self._points_by_uuid or point.addr in self._points_by_topic:
                     logger.warning(f"Duplicate point detected during governor point creation: UUID={point.uuid}, Addr={point.addr}. Skipping registration.")
                     continue
                self._points_by_uuid[point.uuid] = point
                self._points_by_topic[point.addr] = point
                # Subscribe to governor points to allow external updates (e.g., setpoint changes)
                points_to_subscribe.add(point.addr)
                logger.debug(f"Registered governor point {name} (UUID: {point.uuid}, Addr: {point.addr}) - Will subscribe.")
            else:
                 logger.warning(f"Failed to create governor point '{name}' from config: {point_config}")

        # Identify and Instantiate Referenced External Points
        logger.info("Identifying and creating referenced external points...")
        referenced_addrs: Set[str] = set()
        # Build the set of referenced addresses from strategies
        for strategy in strategies:
             settings = strategy.get("settings", {})
             for key, addr in settings.items():
                 if key.endswith("_addr") and isinstance(addr, str) and addr:
                     referenced_addrs.add(addr)

        # *** Log 1: Check addresses referenced by strategies ***
        logger.info(f"DEBUG GPM Setup: Addresses referenced by strategies: {referenced_addrs}")

        # Define helper function locally to search external_points_config
        def find_external_point_config(addr_to_find: str) -> Optional[Dict]:
            """Searches microC and driver configs for a point definition by address."""
            # Search microcontrollers
            for mc_name, mc_data in external_points_config.get("microcontrollers", {}).items():
                for s_name, s_data in mc_data.get("sensors", {}).items():
                    for r_name, r_config in s_data.items():
                        if isinstance(r_config, dict) and r_config.get("addr") == addr_to_find:
                            return r_config
                for cp_name, cp_data in mc_data.get("control_points", {}).items():
                    for access_type in ["readback", "write"]:
                         if access_type in cp_data and isinstance(cp_data[access_type], dict) and cp_data[access_type].get("addr") == addr_to_find:
                              return cp_data[access_type]
            # Search drivers
            for drv_name, drv_data in external_points_config.get("drivers", {}).items():
                 # Search status points (e.g., state, state_time)
                 for st_name, st_config in drv_data.get("status", {}).items(): # Iterate items
                      if isinstance(st_config, dict) and st_config.get("addr") == addr_to_find:
                           return st_config
                 # Search command points (e.g., state)
                 for cmd_name, cmd_config in drv_data.get("command", {}).items(): # Iterate items
                      if isinstance(cmd_config, dict) and cmd_config.get("addr") == addr_to_find:
                           return cmd_config
            return None
        # --- End Helper ---

        # Loop through referenced addresses
        SENSOR_TOPIC_TO_DEBUG = "mush/controllers/C1/sensors/sht_0/temperature" # Define for easy checking
        for addr in referenced_addrs:
            if addr in self._points_by_topic:
                logger.debug(f"Address {addr} already managed (likely governor point). Skipping external creation.")
                continue

            # *** Log 2: Check if config is found for the address ***
            point_config = find_external_point_config(addr)
            is_sensor_topic = (addr == SENSOR_TOPIC_TO_DEBUG) # Flag for specific logging

            if is_sensor_topic:
                logger.info(f"DEBUG GPM Setup: Result of find_external_point_config for SENSOR '{addr}': {point_config is not None}")
                if point_config: logger.info(f"DEBUG GPM Setup: Found SENSOR point_config: {point_config}")


            if point_config:
                # *** Log 3: Check result of point creation ***
                point = self._create_point_from_config(point_config, f"external ref ({addr})")
                if is_sensor_topic:
                    logger.info(f"DEBUG GPM Setup: Result RETURNED BY _create_point_from_config for SENSOR '{addr}': {'Success (Point Object)' if point else 'Failed (Returned None)'}")

                if point:
                    # Register the point if creation succeeded
                    if point.uuid in self._points_by_uuid or point.addr in self._points_by_topic:
                         logger.warning(f"Duplicate point detected during external point creation: UUID={point.uuid}, Addr={point.addr}. Skipping registration.")
                         continue
                    self._points_by_uuid[point.uuid] = point
                    self._points_by_topic[point.addr] = point
                    logger.debug(f"Registered external point: UUID={point.uuid}, Addr={point.addr}")

                    # Decide if it needs subscription
                    # Check if it's explicitly configured as the output command for any strategy
                    is_output_cmd = any(s.get("settings",{}).get("actuator_command_addr") == addr for s in strategies)
                    # Assume input if it's not the primary output command
                    # (More robust logic might check topic patterns or point type)
                    is_input = not is_output_cmd

                    if is_sensor_topic: # Specific log for sensor subscription decision
                        logger.info(f"DEBUG GPM Setup: SENSOR subscription check: is_output_cmd={is_output_cmd} -> is_input={is_input}")

                    if is_input:
                        points_to_subscribe.add(addr)
                        logger.debug(f"Added '{addr}' to points_to_subscribe.")
                    else:
                         logger.debug(f"Did NOT add '{addr}' to points_to_subscribe (considered output).")
            elif is_sensor_topic:
                 # Log if config wasn't found specifically for the sensor
                 logger.warning(f"DEBUG GPM Setup: No point_config FOUND in external configs for SENSOR address '{addr}'!")

        # *** Log 4: Check final subscription list ***
        logger.info(f"DEBUG GPM Setup: Final set of topics to subscribe to: {points_to_subscribe}")

        # Setup MQTT Subscriptions loop
        if not self._mqtt_handler:
             logger.error("Cannot setup MQTT subscriptions: MQTT handler is not initialized.")
        else:
             logger.info(f"Setting up MQTT subscriptions for {len(points_to_subscribe)} topics...")
             for topic in points_to_subscribe:
                 try:
                     logger.debug(f"Subscribing to: {topic}")
                     self._mqtt_handler.subscribe(topic, qos=1)
                     self._mqtt_handler.register_message_handler(topic, self.process_incoming_message)
                 except Exception as e:
                      logger.error(f"Failed to subscribe or register handler for topic {topic}: {e}", exc_info=True)

        # *** Log 5: Check final registered points by topic ***
        logger.info(f"DEBUG GPM Setup: Final keys in _points_by_topic AT END of setup: {list(self._points_by_topic.keys())}")
        logger.info("GPM Point setup complete.")


    # --- Runtime Methods ---
    def process_incoming_message(self, topic: str, payload: str):
        """
        Callback registered with MQTTInterface. Routes incoming messages
        to the appropriate point's handle_incoming_update method.
        """
        logger.info(f"GPM Received MQTT - Topic: {topic}, Payload: '{payload}'") # Keep this log
        point = self._points_by_topic.get(topic)
        if point:
            try:
                success, processed_value = point.handle_incoming_update(payload)
                if success:
                    logger.debug(f"Successful update for {topic}. Processed value: {processed_value}")
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
            logger.warning(f"Point not found for identifier: {point_uuid_or_addr} in update_requested_value")
            return

        if isinstance(point, CoreWritablePoint):
             # set_requested_value performs validation
             if point.set_requested_value(value):
                  # If valid and value changed (or first time), mark for publish
                  self._pending_publishes[point.addr] = point.requested_value
                  logger.info(f"Queued publish for '{point.addr}' with requested value: {point.requested_value}")
             # Else: Validation failed, warning logged by set_requested_value
        else:
             logger.warning(f"Attempted to set requested value for non-writable point: {point.addr} (UUID: {point.uuid})")


    def update(self):
        """
        Core periodic logic executed by the calling loop (e.g., GovernorRunner).
        Checks points, initiates publishes, handles retries/republishes.
        """
        now = time.monotonic() # Use monotonic time for interval checks
        if not self._mqtt_handler:
            logger.error("Cannot perform GPM update: MQTT handler is missing.")
            return
        if not self._config:
             logger.error("Cannot perform GPM update: Configuration is missing.")
             return

        # Determine actuator command addresses (needed for confirmation logic)
        actuator_command_addrs = set()
        try:
            # Ensure config/strategies are available
            strategies = self._config.get_control_strategies_config()
            for strategy in strategies:
                addr = strategy.get("settings", {}).get("actuator_command_addr")
                if addr:
                    actuator_command_addrs.add(addr)
        except Exception as e:
             logger.error(f"Error getting control strategies during GPM update: {e}", exc_info=True)
             # Continue without actuator confirmation logic? Or return? For now, log and continue.
             actuator_command_addrs = set() # Ensure it's empty


        # Iterate over a copy of point values in case dictionary changes during iteration
        points_to_check = list(self._points_by_uuid.values())

        for point in points_to_check:
            if not isinstance(point, CoreWritablePoint):
                continue # Skip non-writable points

            addr = point.addr
            req_value = point.requested_value
            retry_interval = point.retry_interval
            republish_freq = point.republish_frequency

            if req_value is None: # Nothing requested for this point yet
                continue

            needs_publish = False
            publish_reason = "None"

            # 1. Check for pending explicit requests
            if addr in self._pending_publishes:
                if self._pending_publishes[addr] == req_value:
                    needs_publish = True
                    publish_reason = "Pending Request"
                else:
                    logger.debug(f"Stale pending publish removed for {addr} (requested value changed)")
                    self._pending_publishes.pop(addr, None)

            # 2. Check for retry if publish is unconfirmed
            if not needs_publish and retry_interval is not None:
                if self._is_publish_unconfirmed(addr):
                    last_attempt = self._last_publish_attempt_time.get(addr, -retry_interval - 1.0) # Ensure first retry happens
                    if (now - last_attempt) >= retry_interval:
                        needs_publish = True
                        publish_reason = f"Retry (Unconfirmed > {retry_interval:.1f}s)"

            # 3. Check for periodic republish (if not unconfirmed)
            if not needs_publish and republish_freq is not None and not self._is_publish_unconfirmed(addr):
                last_success_time = self._last_successful_publish_time.get(addr, -republish_freq - 1.0) # Ensure first republish happens
                if (now - last_success_time) >= republish_freq:
                        needs_publish = True
                        publish_reason = f"Periodic Republish (Freq: {republish_freq:.1f}s)"

            # --- Perform Publish if Needed ---
            if needs_publish:
                logger.info(f"Publishing for '{addr}' (Reason: {publish_reason}): Value={req_value}")
                self._last_publish_attempt_time[addr] = now

                # Publish the requested value
                success = self._mqtt_handler.publish(addr, req_value, qos=1, retain=False)

                if success:
                    # Remove from explicit pending list if this publish was for that reason
                    self._pending_publishes.pop(addr, None)

                    # Decide on confirmation strategy
                    if addr in actuator_command_addrs:
                        logger.debug(f"Publish for actuator '{addr}' requires confirmation. Expecting value: {req_value}")
                        self._pending_confirmation[addr] = req_value
                    else: # Assume immediate success for non-actuator writable points
                        logger.debug(f"Assuming immediate success for non-actuator publish: {addr}")
                        self._last_successful_publish_time[addr] = now
                        self._pending_confirmation.pop(addr, None)
                else:
                    # Publish call failed immediately (e.g., buffer full, disconnected)
                    logger.warning(f"MQTT publish call failed immediately for topic '{addr}'. Will retry if configured.")
                    # Do not remove from _pending_publishes if it was there


    # --- Confirmation and Retry Logic Helpers ---
    def _check_publish_confirmation(self, topic: str, value: Any):
        """Checks if an incoming message confirms a prior command."""
        if topic in self._pending_confirmation:
             expected_value = self._pending_confirmation[topic]
             # Simple string comparison (adjust if complex types needed)
             if str(value) == str(expected_value):
                  logger.info(f"Publish confirmed for topic '{topic}' with value '{value}'")
                  self._last_successful_publish_time[topic] = time.monotonic()
                  del self._pending_confirmation[topic]
             else:
                  logger.warning(f"Confirmation mismatch for topic '{topic}'. Expected '{expected_value}', got '{value}'. Waiting for retry or matching value.")


    def _is_publish_unconfirmed(self, topic: str) -> bool:
         """Checks if a specific topic is awaiting confirmation."""
         return topic in self._pending_confirmation


    # --- Public Getter Methods ---
    def get_point_value(self, identifier: int | str) -> Any | None:
        """Gets the current valid value of a point."""
        point = self._get_point(identifier)
        # The point.value property itself handles returning None if invalid
        return point.value if point else None


    def get_point_snapshot(self, identifier: int | str) -> Tuple[Any | None, datetime | None, bool]:
         """Gets a snapshot of the point's state (value, timestamp, validity)."""
         point = self._get_point(identifier)
         if point:
             # Access properties which delegate to the underlying value instance
             return point.value, point.last_update_time, point.is_valid
         return None, None, False # Return defaults if point not found


    # --- Internal Helper ---
    def _get_point(self, identifier: int | str) -> Optional[BasePoint]:
         """Internal helper to get point by UUID or topic."""
         point: Optional[BasePoint] = None
         if isinstance(identifier, int): # Check UUID first
             point = self._points_by_uuid.get(identifier)
             if point is None: logger.warning(f"Point not found for UUID: {identifier}")
         elif isinstance(identifier, str): # Then check topic
             point = self._points_by_topic.get(identifier)
             if point is None: logger.warning(f"Point not found for topic: '{identifier}'")
         else:
              logger.warning(f"Invalid identifier type used to get point: {type(identifier)}")
         return point