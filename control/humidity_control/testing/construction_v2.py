import os
import sys
import json
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from construction import Constructor

# Create and connect system
constructor = Constructor(config_path)
constructor.connect_mqtt()

# Get references to components
fsm = constructor.FSM
tm = constructor.TM
pm = constructor.PM

# Print initial state
print(f"Initial FSM State: {fsm.current_state.state.name}")
print(f"Available Transitions: {tm.transitions}")