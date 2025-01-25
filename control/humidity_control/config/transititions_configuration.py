import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from config_helpers import Constraint,ConstraintGroup,Transitions_Maker
#This whole this obviously needs to be more config based. But it's basicall a config file as is.
states = ["Off","HumidOn","Humidify","FanOff","Unknown"]


##Notice how we're using the same sensor for all of these, it's the state_time sensor.
#This whole thing could definitely be prettier. But I want to move on to control now.
#Could have separate file of state_time constraint params, but then that's one more place where names could start differing.
# Like if state names change, or if the sensor naming conventions changes... the dependendencies should be built in.
# Like we should be using a survery class while constructing transitions here to know what sensors are available and what they're called. 
state_time_sensor = "R.fsm.sensors.time_in_state"
timed_constraints = {}
constraint_Off_HumidOn = Constraint("0","R.fsm.sensors.time_in_state","1200",">","float")
constraint_HumidOn_Humidify = Constraint("0","R.fsm.sensors.time_in_state","30",">","float")
constraint_Humidify_Fan_Off = Constraint("0","R.fsm.sensors.time_in_state","300",">","float")
constraint_FanOff_Off = Constraint("0","R.fsm.sensors.time_in_state","30",">","float")
constraint_Unknown_Off= Constraint("0","R.fsm.sensors.time_in_state","0",">","float")

#COnstraint groups by themselves aren't tied to pairs of states. They're just a collection of constraints.
cg_1 = ConstraintGroup("CG_1",[constraint_Off_HumidOn])
cg_2 = ConstraintGroup("CG_2",[constraint_HumidOn_Humidify])
cg_3 = ConstraintGroup("CG_3",[constraint_Humidify_Fan_Off])
cg_4 = ConstraintGroup("CG_4",[constraint_FanOff_Off])
cg_5 = ConstraintGroup("CG_5",[constraint_Unknown_Off])
states = ["Off","HumidOn","Humidify","FanOff","Unknown"]

transitions = Transitions_Maker()

for name1,name2,cg in zip(["Off","HumidOn","Humidify","FanOff","Unknown"],["HumidOn","Humidify","FanOff","Off","Off"],[cg_1,cg_2,cg_3,cg_4,cg_5]):
    assert(name1 in states)
    assert(name2 in states)
    transitions.add_constraint_group(name1,name2,cg)

#print(transitions.configuration)
transitions.save(config_path+"/transitions.json")