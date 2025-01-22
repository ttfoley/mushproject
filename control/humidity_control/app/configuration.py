import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from config_helpers import Constraint,ConstraintGroup,Transitions

states = ["On","Off","Unknown"]

transitions = Transitions()


constraint_1 = Constraint("0","States.Off.time_in_state","30",">")

cg_1 = ConstraintGroup("CG_1",[constraint_1])

transitions.add_constraint_group("On","Off",cg_1)

print(transitions.configuration)
transitions.save(current_dir+"/testing.json")