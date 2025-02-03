import sys
import os
import json
from collections import namedtuple, defaultdict
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)
from config_helpers import PreTransitionsConstructor, PTC_Helper, ConstraintGroup, StateTimeConstraint, Transitions_Maker


"""
I'm not sure exactly how much of transitions should be pushed into config, but this is the most user
involved part so I'm leaving as modifiable script for now.
"""
PTC = PreTransitionsConstructor(config_path)
helper = PTC_Helper(PTC)

driver_name = helper.driver_name
driver_status_topic = f"mush/drivers/{driver_name}/sensors/status/"
driver_state_point = PTC.PM._uuid_lookup[f"{driver_status_topic}state"]
driver_state_time_point = PTC.PM._uuid_lookup[f"{driver_status_topic}state_time"]
#these are the values driver_state_point can take on.
driver_states = helper.writable_states + ["unknown"]

constraint_groups = defaultdict(dict)
constraint_group_counts = defaultdict(lambda: defaultdict(int))

## Define constraint groups for each pair of states here.
def new_cg(from_state: str, to_state: str, description: str = "", priority: int = 0) -> ConstraintGroup:
    assert (from_state in driver_states) and (to_state in driver_states)
    if from_state not in constraint_groups:
        constraint_groups[from_state] = {}
    if to_state not in constraint_groups[from_state]:
        constraint_groups[from_state][to_state] = []

    constraint_group_counts[from_state][to_state] += 1
    cg_id = constraint_group_counts[from_state][to_state]

    return ConstraintGroup(from_state, to_state, cg_id, description=description, priority=priority)

def value_description(uuid: int) -> str:
    point = PTC.PM._points_lookup[uuid]
    return point.description

# Example usage
cg = new_cg("unknown", "off", "Turn the driver off immediately if state is unknown", priority=0)
value = driver_state_time_point
desc = value_description(value)
cg.add_constraint(StateTimeConstraint(cg.num_constraints, value, 0, ">=" ,description=desc))
constraint_groups["unknown"]["off"].append(cg)

cg = new_cg("off", "hum1_fan0", "off-hum1_fan0 user transition", priority=0)
value = driver_state_time_point
desc = value_description(value)
cg.add_constraint(StateTimeConstraint(cg.num_constraints, value, 60, ">=",description=desc))
constraint_groups["off"]["hum1_fan0"].append(cg)

cg = new_cg("hum1_fan0", "off", "hum1_fan0-off user transition", priority=0)
value = driver_state_time_point
desc = value_description(value)
cg.add_constraint(StateTimeConstraint(cg.num_constraints, value, 60, ">=",description=desc))
constraint_groups["hum1_fan0"]["off"].append(cg)

TM = Transitions_Maker()
# Save the constraint groups
for from_state in constraint_groups:
    for to_state in constraint_groups[from_state]:
        for cg in constraint_groups[from_state][to_state]:
            TM.add_constraint_group(from_state, to_state, cg)

print(TM.configuration)
TM.save(config_path +"/transitions_test.json")







