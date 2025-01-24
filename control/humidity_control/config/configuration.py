import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from config_helpers import Constraint,ConstraintGroup,Transitions
#This whole this obviously needs to be more config bases.
states = ["On","Off","Unknown"]

transitions = Transitions()
#   "state_time_transitions": {
#     "Off": {"to_state": "HumidOn", "time": "30"},
#     "HumidOn": {"to_state": "Humidify", "time": "45"},
#     "Humidify": {"to_state": "FanOff", "time": "30"},
#     "FanOff": {"to_state": "Off", "time": "15"},
#     "Unknown": {"to_state": "Off", "time": "0"}
#   }
# }

constraint_Off_HumidOn = Constraint("0","fsm.sensors.time_in_state","30",">","float")
constraint_HumidOn_Humidify = Constraint("0","fsm.sensors.time_in_state","30",">","float")
constraint_Humidify_Fan_Off = Constraint("0","fsm.sensors.time_in_state","30",">","float")
constraint_Fan_Off = Constraint("0","fsm.sensors.time_in_state","30",">","float")
constraint_UnknownOff= Constraint("0","fsm.sensors.time_in_state","0",">","float")

cg_1 = ConstraintGroup("CG_1",[constraint_Off_HumidOn])
cg_2 = ConstraintGroup("CG_2",[constraint_HumidOn_Humidify])
cg_3 = ConstraintGroup("CG_3",[constraint_Humidify_Fan_Off])
cg_4 = ConstraintGroup("CG_4",[constraint_Fan_Off])
cg_5 = ConstraintGroup("CG_5",[constraint_UnknownOff])

for name1,name2,cg in zip(["Off","HumidOn","Humidify","FanOff","Unknown"],["HumidOn","Humidify","Fanoff","FanOff","Off"],[cg_1,cg_2,cg_3,cg_4,cg_5]):
    transitions.add_constraint_group(name1,name2,cg)

print(transitions.configuration)
transitions.save(current_dir+"/transitions_testing.json")