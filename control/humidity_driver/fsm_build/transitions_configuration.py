import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)
from config_helpers import TransitionsConfigHelper, TransitionsBuilder

helper = TransitionsConfigHelper(config_path)
builder = TransitionsBuilder(helper)

min_state_time = 1 ##Don't even remember why we had this? I guess rapid cycling. 
max_on_time = 15
lockout_time = 60
# Unknown to Off - safety transition
cg = builder.new_constraint_group("unknown", "off", 
    "Turn off immediately if unknown")
builder.add_state_time_constraint(cg, 0)

# Off to On - requires command and minimum time
cg = builder.new_constraint_group("off", "on", 
    "Governor commanded transition from off to on")
builder.add_state_time_constraint(cg, min_state_time)  # Must be in off state for min_state_time
builder.add_command_constraint(cg, "on")  # Command value must match state name

# On to Off - requires command and minimum time
cg = builder.new_constraint_group("on", "off",
    "Governor commanded transition from on to off") 
builder.add_state_time_constraint(cg, min_state_time)  # Must be in on state for min_state_time
builder.add_command_constraint(cg, "off")  # Command value must match state name

# On to Lockout - requires command and minimum time
cg = builder.new_constraint_group("on", "lockout",
    "On too long, transition from on to lockout") 
builder.add_state_time_constraint(cg, max_on_time)

cg = builder.new_constraint_group("lockout", "off",
    "Lockout finished, return to off") 
builder.add_state_time_constraint(cg, lockout_time) # Must be in on state for max_on_time

builder.build()
builder.save(config_path) 