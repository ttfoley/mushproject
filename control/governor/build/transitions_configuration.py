import sys
import os
import json
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)
from config_helpers import TransitionsConfigHelper, GovernorTransitionsBuilder

helper = TransitionsConfigHelper(config_path)
builder = GovernorTransitionsBuilder(helper)

# Add command points for each state
builder.add_command_points()

# Load base driver transitions
base_transitions = json.load(open(os.path.join(config_path, "transitions.json")))

# Build transitions between all states with minimum state time
builder.build_all_transitions(min_state_time=60)
transitions = builder.build()

# Merge the constraint groups
for from_state, to_states in base_transitions["Transitions"].items():
    for to_state, transition in to_states.items():
        for cg in transition["constraint_groups"]:
            builder.transitions_maker.add_constraint_group(from_state, to_state, cg)

builder.save(config_path) 