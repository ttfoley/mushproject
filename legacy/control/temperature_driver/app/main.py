import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
# Use Docker paths if in container, otherwise use relative paths
if os.getenv('IN_DOCKER'):
    lib_path = '/app/common'
    config_path = '/app/config'
else:
    lib_path = os.path.join(current_dir, '../../common')
    config_path = os.path.join(current_dir, '../config')

sys.path.append(lib_path)

from fsm_runner import FSMRunner

if __name__ == "__main__":
    fsm = FSMRunner(config_path)
    fsm.run()