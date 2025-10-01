import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)
from config_helpers import TransitionsConfigHelper, TransitionsBuilder


"""
I'm not sure exactly how much of transitions should be pushed into config, but this is the most user
involved part so I'm leaving as modifiable script for now.
"""
helper = TransitionsConfigHelper(config_path)
builder = TransitionsBuilder(helper)

# Unknown to Off transition
cg = builder.new_constraint_group("unknown", "off", 
    "Turn the driver off immediately if state is unknown")
builder.add_state_time_constraint(cg, 0)

# Off to Hum1Fan0 transition
cg = builder.new_constraint_group("off", "hum1_fan0",
    "off-hum1_fan0 user transition")
builder.add_state_time_constraint(cg, 60)

# Hum1Fan0 to Off transition  
cg = builder.new_constraint_group("hum1_fan0", "off",
    "hum1_fan0-off user transition")
builder.add_state_time_constraint(cg, 60)

builder.build()
builder.save(config_path)







