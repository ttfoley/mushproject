import os
import sys
import json
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from construction import FSMConstructor

# Create and connect system
fsm, pm, tm, mqtt = (FSMConstructor(config_path)
    .build_points_manager()
    .build_states_manager()
    .build_transitions_manager()
    .add_mqtt()
    .build_active_fsm()
    .build())


# Get references to components

# Print initial state
print(f"Initial FSM State: {fsm.current_state.name}")
print(f"Available Transitions: {tm.transitions}")