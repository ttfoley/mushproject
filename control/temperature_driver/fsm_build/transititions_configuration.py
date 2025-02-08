import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)
from config_helpers import TransitionsConfigHelper, TransitionsBuilder

helper = TransitionsConfigHelper(config_path)
builder = TransitionsBuilder(helper)

# Unknown to Off transition
cg = builder.new_constraint_group("unknown", "off", 
    "Turn the driver off immediately if state is unknown")
builder.add_state_time_constraint(cg, 0)

# Off to On transition
cg = builder.new_constraint_group("off", "on",
    "off-on user transition")
builder.add_state_time_constraint(cg, 60)

# On to Off transition  
cg = builder.new_constraint_group("on", "off",
    "on-off user transition")
builder.add_state_time_constraint(cg, 60)

builder.build()
builder.save(config_path) 