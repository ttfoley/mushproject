# control/governors/temperature_governor/app/main.py
import os
import sys
import logging

# Handle path to import common.governor.runner
# IMPORTANT: Adjust this relative path based on where this main.py is
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up 3 levels from app/ to control/ then down to common/
common_governor_path = os.path.abspath(os.path.join(current_dir, '..', '..', '..', 'common', 'governor'))

# Or maybe just add 'control' path? Needs careful thought based on execution env.
control_path = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))


# Use the path logic consistent with how you intend to run this
# Option 1: Add common/governor directly (less flexible)
# if common_governor_path not in sys.path:
#    sys.path.append(common_governor_path)

# Option 2: Add 'control' to path (requires packaging __init__.py files)
if control_path not in sys.path:
    sys.path.append(control_path)

try:
    from common.governor.runner import GovernorRunner, GovernorRunnerError
except ImportError as e:
    print(f"Failed to import GovernorRunner: {e}")
    print(f"Check sys.path: {sys.path}")
    print(f"Attempted path: {common_governor_path} or {control_path}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting Temperature Governor...")
    # Assumes config is in ../config relative to this main.py
    config_file = os.path.join(current_dir, '..', 'config', 'governor_config.json')

    if not os.path.isfile(config_file):
        logger.error(f"Governor configuration file not found: {config_file}")
        sys.exit(1)

    runner = GovernorRunner(config_path=config_file)
    try:
        runner.setup()
        runner.run() # This blocks until shutdown (e.g., Ctrl+C)
    except (GovernorRunnerError) as e:
         logger.error(f"Failed to start Governor: {e}")
    except Exception as e:
         logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        logger.info("Temperature Governor terminated.")