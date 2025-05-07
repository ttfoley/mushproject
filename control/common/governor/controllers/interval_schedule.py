# common/governor/controllers/interval_schedule.py # <-- Filename conceptually changed

import time
import logging
from typing import Dict, Any, Optional, Literal, TYPE_CHECKING

# Import the base class and potentially the point manager for type hints
# Adjust relative import based on your final directory structure
try:
    from .controller_base import BaseController
    if TYPE_CHECKING:
        from ..point_manager import GovernorPointManager
except ImportError:
    # Fallback for different execution contexts - consider proper packaging later
    import sys
    import os
    # Assuming this file is in common/governor/controllers
    common_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if common_path not in sys.path:
        sys.path.append(common_path)
    from common.governor.controllers.controller_base import BaseController
    if TYPE_CHECKING:
        from common.governor.point_manager import GovernorPointManager


# Use the new class name for the logger
logger = logging.getLogger(__name__) # Logger name is based on module, which is now interval_schedule

# Rename the class
class IntervalScheduleController(BaseController):
    """
    Governor controller that turns an output on and off based on
    configurable time intervals (durations) read from points.
    """
    # Define a constant prefix for logging messages from this controller
    _LOG_PREFIX = "IntervalScheduleController:"

    def __init__(self):
        """Initializes the interval schedule controller state."""
        self._current_phase: Optional[Literal["on", "off"]] = None # Determined by config on first run
        self._phase_start_time: Optional[float] = None # Monotonic time when the current phase began
        # Update log message with prefix
        logger.info(f"{self._LOG_PREFIX} Initialized.")

    def execute_cycle(self, point_manager: 'GovernorPointManager', strategy_settings: Dict[str, Any]) -> None:
        """
        Executes one cycle of the interval schedule controller.
        Reads interval points, checks elapsed time, and sends commands.
        """
        # 1. Get configuration from strategy_settings
        try:
            on_interval_uuid = strategy_settings["on_interval_hours_point_uuid"]
            off_interval_uuid = strategy_settings["off_interval_hours_point_uuid"]
            output_cmd_uuid = strategy_settings["output_command_point_uuid"]
            # Get initial phase from config, default to 'off' if not specified
            initial_phase_config = strategy_settings.get("initial_phase", "off")
        except KeyError as e:
            # Update log message with prefix
            logger.warning(f"{self._LOG_PREFIX} Missing required setting '{e}' in strategy config. Skipping cycle.")
            return

        # Initialize phase on the first run
        if self._current_phase is None:
            self._current_phase = initial_phase_config
            self._phase_start_time = time.monotonic()
            # Update log message with prefix
            logger.info(f"{self._LOG_PREFIX} Initializing phase to '{self._current_phase}' and setting command.")
            # Ensure the initial command matches the starting phase
            point_manager.update_requested_value(output_cmd_uuid, self._current_phase)
            # We don't proceed further on the very first cycle to allow the command to be sent
            return

        # 2. Get interval values from Point Manager
        try:
            on_interval_hours = point_manager.get_point_value(on_interval_uuid)
            off_interval_hours = point_manager.get_point_value(off_interval_uuid)

            # Validate interval values
            if on_interval_hours is None or off_interval_hours is None:
                 # Update log message with prefix
                logger.debug(f"{self._LOG_PREFIX} Interval points not ready (ON={on_interval_hours}, OFF={off_interval_hours}). Skipping cycle.")
                # Keep current state, don't switch phase if intervals are unknown
                return

            # Convert hours to seconds for comparison
            on_interval_sec = float(on_interval_hours) * 3600.0
            off_interval_sec = float(off_interval_hours) * 3600.0

            # Ensure intervals are non-negative
            if on_interval_sec < 0 or off_interval_sec < 0:
                 # Update log message with prefix
                 logger.warning(f"{self._LOG_PREFIX} Invalid interval values (ON={on_interval_hours}h, OFF={off_interval_hours}h). Intervals must be non-negative. Skipping cycle.")
                 # Keep current state, don't switch phase
                 return

        except (TypeError, ValueError) as e:
             # Update log message with prefix
            logger.warning(f"{self._LOG_PREFIX} Could not read or convert interval points: {e}. Skipping cycle.")
            # Keep current state, don't switch phase
            return
        except Exception as e:
             # Update log message with prefix
            logger.error(f"{self._LOG_PREFIX} Unexpected error getting interval points: {e}", exc_info=True)
            # Keep current state, don't switch phase
            return

        # 3. Check elapsed time and potentially switch phase
        now = time.monotonic()
        if self._phase_start_time is None: # Should have been set during initialization
             # Update log message with prefix
             logger.warning(f"{self._LOG_PREFIX} Phase start time is not set. Resetting phase.")
             self._current_phase = initial_phase_config # Reset to initial
             self._phase_start_time = now
             point_manager.update_requested_value(output_cmd_uuid, self._current_phase)
             return

        elapsed_in_phase = now - self._phase_start_time
        phase_completed = False
        next_phase: Literal["on", "off"] = "off" # Default assignment

        if self._current_phase == "on":
            if on_interval_sec == 0: # Handle zero interval: stay off permanently if ON is zero
                 # Update log message with prefix
                logger.debug(f"{self._LOG_PREFIX} ON interval is 0, ensuring OFF state.")
                next_phase = "off"
                phase_completed = True # Force switch to off
            elif elapsed_in_phase >= on_interval_sec:
                 # Update log message with prefix
                logger.info(f"{self._LOG_PREFIX} ON interval ({on_interval_hours}h) complete. Switching to OFF.")
                next_phase = "off"
                phase_completed = True
        elif self._current_phase == "off":
             if off_interval_sec == 0: # Handle zero interval: stay on permanently if OFF is zero
                  # Update log message with prefix
                 logger.debug(f"{self._LOG_PREFIX} OFF interval is 0, ensuring ON state.")
                 next_phase = "on"
                 phase_completed = True # Force switch to on
             elif elapsed_in_phase >= off_interval_sec:
                 # Update log message with prefix
                logger.info(f"{self._LOG_PREFIX} OFF interval ({off_interval_hours}h) complete. Switching to ON.")
                next_phase = "on"
                phase_completed = True

        # 4. Update state and publish command if phase completed
        if phase_completed:
            self._current_phase = next_phase
            self._phase_start_time = now
             # Update log message with prefix
            logger.info(f"{self._LOG_PREFIX} Sending command '{self._current_phase}' to {output_cmd_uuid}")
            point_manager.update_requested_value(output_cmd_uuid, self._current_phase)
        else:
             # Update log message with prefix
             logger.debug(f"{self._LOG_PREFIX} Remaining in '{self._current_phase}' phase. Elapsed: {elapsed_in_phase:.1f}s")

