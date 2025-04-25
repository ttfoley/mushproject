# control/common/governor/controllers/bangbang.py
import logging
from typing import Dict, Any, TYPE_CHECKING

# Import the base class
from .controller_base import BaseController

# Use TYPE_CHECKING and forward reference for GovernorPointManager
if TYPE_CHECKING:
    from ..point_manager import GovernorPointManager

logger = logging.getLogger(__name__)

# Make BangBangController inherit from BaseController
class BangBangController(BaseController):
    """
    Implements simple bang-bang (on/off) control logic
    with a deadband. Now implements the BaseController interface.
    """

    def __init__(self):
        # No specific config needed at init time for this simple version
        pass

    def calculate_command(self, sensor_value: float | None, setpoint: float, deadband: float) -> str | None:
        """
        Calculates the desired output state ("on" or "off") based on inputs.
        (This internal logic remains the same)
        """
        if sensor_value is None:
            raise ValueError("Cannot calculate command: Invalid sensor value (None).")
        if deadband < 0:
             raise ValueError(f"Cannot calculate command: Invalid deadband ({deadband}).")

        upper_bound = setpoint + deadband
        lower_bound = setpoint - deadband

        if sensor_value > upper_bound:
            return "off"
        elif sensor_value < lower_bound:
            return "on"
        else:
            return None

    # Implement the required method from BaseController
    def execute_cycle(self, point_manager: 'GovernorPointManager', strategy_settings: Dict[str, Any]) -> None:
        """
        Executes one cycle of the BangBang controller.
        Fetches points based on strategy_settings and requests updates.
        """
        # 1. Get required point addresses from settings
        sensor_addr = strategy_settings["sensor_point_addr"]
        setpoint_addr = strategy_settings["setpoint_point_addr"]
        deadband_addr = strategy_settings["deadband_point_addr"]
        actuator_cmd_addr = strategy_settings["actuator_command_addr"]

        # Basic check if addresses are configured
        if not all([sensor_addr, setpoint_addr, deadband_addr, actuator_cmd_addr]):
            logger.warning("BangBangController: Missing required point addresses in strategy settings. Skipping cycle.")
            return

        # 2. Get current values from Point Manager
        try:
            sensor_val = point_manager.get_point_value(sensor_addr)
            setpoint_val = point_manager.get_point_value(setpoint_addr)
            deadband_val = point_manager.get_point_value(deadband_addr)
            ### I really need to use pydantic...
            assert isinstance(sensor_val, float), "Sensor value must be a float."
            assert isinstance(setpoint_val, float), "Setpoint value must be a float."
            assert isinstance(deadband_val, float), "Deadband value must be a float."

            # Check if inputs are valid
            if None in [sensor_val, setpoint_val, deadband_val]:
                # Log less frequently? Or only if state changes?
                # logger.debug(f"BangBangController: Required inputs not ready (Sensor={sensor_val}, Setpoint={setpoint_val}, Deadband={deadband_val}). Skipping cycle.")
                return # Skip calculation if any input is invalid/None

            # 3. Perform control calculation
            logger.debug(f"BangBang executing: Sensor={sensor_val}, Setpoint={setpoint_val}, Deadband={deadband_val}")
            command = self.calculate_command(sensor_val, setpoint_val, deadband_val)

            # 4. Request state change if needed
            if command is not None:
                logger.info(f"BangBang requesting actuator state: {command} for {actuator_cmd_addr}")
                point_manager.update_requested_value(actuator_cmd_addr, command)

        except ValueError as ve: # Catch calculation errors
            logger.warning(f"BangBangController calculation error: {ve}")
        except Exception as e: # Catch unexpected errors (e.g., getting point values)
            logger.error(f"Unexpected error in BangBangController execute_cycle: {e}", exc_info=True)