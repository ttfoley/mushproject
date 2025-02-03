import os
import sys
import json
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from construction import PreTransitionsConstructor
from transitions import Transitions_Manager

PTC = PreTransitionsConstructor(config_path)
print(PTC.PM._uuid_lookup)

transitions = json.load(open(config_path +"/transitions_test.json",'r'))
states_dict = PTC.SM.states
TM = Transitions_Manager(transitions,states_dict,PTC.PM)
print(transitions)