import time
import logging
import os
import sys
from typing import Dict, Any # Add Dict

# Path logic (keep for now, TODO replace with packaging)
current_dir = os.path.dirname(os.path.abspath(__file__))
common_path = os.path.abspath(os.path.join(current_dir, '..'))
if common_path not in sys.path:
    sys.path.append(common_path)

try:
    from common.governor.config import GovernorConfiguration, GovernorConfigurationError
    from common.governor.mqtt import GovernorMQTTHandler
    from common.governor.point_manager import GovernorPointManager, GovernorPointManagerError
    # Import the base controller and the specific implementation
    from common.governor.controllers.controller_base import BaseController
    from common.governor.controllers.bangbang import BangBangController
except ImportError as e:
    print(f"Error importing modules: {e}")
    print(f"Current sys.path: {sys.path}")
    print(f"Attempted to import from base path: {common_path}")
    raise

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GovernorRunnerError(Exception):
    """Custom exception for Governor Runner errors."""
    pass

class GovernorRunner:
    """Orchestrates the Governor application lifecycle."""

    def __init__(self, config_path: str):
        """Initializes the GovernorRunner."""
        self._config_path = config_path
        self._config: GovernorConfiguration | None = None
        self._update_interval: float = 5.0
        self.mqtt_handler: GovernorMQTTHandler | None = None
        self.point_manager: GovernorPointManager | None = None
        # Update type hint for controllers dictionary
        self.controllers: Dict[str, BaseController] = {} # Use BaseController here
        self._is_running = False

    def setup(self):
        """Loads configuration and initializes all components."""
        logger.info("GovernorRunner: Starting setup...")
        try:
            logger.info(f"Loading configuration from: {self._config_path}")
            self._config = GovernorConfiguration(self._config_path)
            runner_config = self._config.get_runner_config()
            self._update_interval = float(runner_config.get("update_interval_seconds", 5.0))
            logger.info(f"Runner update interval set to: {self._update_interval} seconds.")

            logger.info("Initializing MQTT Handler...")
            mqtt_config = self._config.get_mqtt_config()
            self.mqtt_handler = GovernorMQTTHandler(
                client_id=mqtt_config["client_id"],
                broker=mqtt_config["broker"],
                port=mqtt_config["port"],
                username=mqtt_config["username"],
                password=mqtt_config["password"]
            )
            self.mqtt_handler.connect()
            self.mqtt_handler.loop_start()
            logger.info("MQTT Handler initialized and loop started.")

            logger.info("Initializing Point Manager...")
            self.point_manager = GovernorPointManager(
                config_object=self._config,
                mqtt_handler=self.mqtt_handler
            )
            logger.info("Point Manager initialized.")

            logger.info("Initializing Controller(s)...")
            strategies = self._config.get_control_strategies_config()
            if not strategies:
                 raise GovernorRunnerError("No control strategies defined in configuration.")

            for strategy_config in strategies:
                strategy_name = strategy_config.get("name")
                strategy_type = strategy_config.get("type")
                if not strategy_name or not strategy_type:
                    logger.warning(f"Skipping invalid strategy config (missing name or type): {strategy_config}")
                    continue

                logger.info(f"Creating controller '{strategy_name}' of type '{strategy_type}'")
                controller_instance: BaseController | None = None # Type hint for clarity
                if strategy_type == "BangBang":
                    controller_instance = BangBangController()
                    logger.info(f"Instantiated BangBangController for strategy '{strategy_name}'.")
                # --- Add elif logic for other controller types here ---
                # elif strategy_type == "PID":
                #     controller_instance = PIDController(...)
                else:
                    logger.warning(f"Unsupported controller type '{strategy_type}' for strategy '{strategy_name}'. Skipping.")

                if controller_instance:
                    # Store the instance (known to be a BaseController)
                    self.controllers[strategy_name] = controller_instance

            if not self.controllers:
                 raise GovernorRunnerError("No valid controllers could be instantiated from configuration.")

            logger.info("GovernorRunner: Setup complete.")

        except (GovernorConfigurationError, GovernorPointManagerError, GovernorRunnerError) as e:
            logger.error(f"GovernorRunner Setup Failed: {e}", exc_info=True)
            self.shutdown()
            raise
        except Exception as e:
            logger.error(f"GovernorRunner Setup Failed with unexpected error: {e}", exc_info=True)
            self.shutdown()
            raise GovernorRunnerError(f"Unexpected setup error: {e}") from e

    def run(self):
        """Starts the main control loop after setup."""
        if not self._config or not self.mqtt_handler or not self.point_manager or not self.controllers:
             logger.error("Runner setup must be completed successfully before running.")
             return

        logger.info("GovernorRunner: Starting main control loop...")
        self._is_running = True
        try:
            while self._is_running:
                start_time = time.monotonic()

                # --- Main Loop Logic ---

                # 1. Execute Controller Logic(s)
                strategies = self._config.get_control_strategies_config()
                for strategy_config in strategies:
                    strategy_name = strategy_config.get("name")
                    strategy_settings = strategy_config.get("settings", {})
                    if strategy_name is None:
                        logger.warning(f"Skipping strategy due to missing 'name' in config: {strategy_config}")
                        continue # Skip to the next strategy_config in the list

                    # Get the controller instance (now typed as BaseController)
                    
                    controller_instance = self.controllers.get(strategy_name)
                    if controller_instance is None:
                        continue # Skip if no controller for this strategy
                    assert isinstance(controller_instance, BaseController), "Controller must be an instance of a controller type."


                    # Ensure point_manager exists
                    if self.point_manager is None:
                         logger.error("Point manager not initialized in run loop. Stopping.")
                         self._is_running = False # Stop the loop
                         break # Exit the strategy loop

                    # Call the standard execute method, passing necessary context
                    try:
                        logger.debug(f"Executing cycle for controller '{strategy_name}'")
                        controller_instance.execute_cycle(self.point_manager, strategy_settings)
                    except Exception as e:
                        # Catch errors during the execution of a specific controller
                        logger.error(f"Error executing controller '{strategy_name}': {e}", exc_info=True)
                        # Decide if a single controller error should stop the whole runner?
                        # For now, we just log and continue to the next controller / GPM update

                # Ensure we break outer loop if point_manager disappeared
                if not self._is_running:
                    break

                # 2. Call Point Manager Update
                # Handles publishing, retries, etc. for all points
                if self.point_manager:
                    self.point_manager.update()

                # --- Loop Timing ---
                end_time = time.monotonic()
                elapsed = end_time - start_time
                wait_time = self._update_interval - elapsed
                if wait_time > 0:
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Loop execution time ({elapsed:.3f}s) exceeded update interval ({self._update_interval:.3f}s).")

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received, stopping runner...")
        except Exception as e:
             logger.error(f"Critical error during GovernorRunner run loop: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        """Stops the runner and cleans up components."""
        # ... (shutdown method remains the same) ...
        if not self._is_running and self.mqtt_handler is None:
            return
        logger.info("GovernorRunner: Shutting down...")
        self._is_running = False
        if self.mqtt_handler:
            logger.info("Stopping MQTT handler loop...")
            self.mqtt_handler.loop_stop()
            time.sleep(0.5)
            logger.info("Disconnecting MQTT handler...")
            self.mqtt_handler.disconnect()
        self.point_manager = None
        self.controllers = {}
        self.mqtt_handler = None
        self._config = None
        logger.info("GovernorRunner: Shutdown complete.")