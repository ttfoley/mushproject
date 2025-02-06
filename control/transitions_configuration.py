from control.common.config_helpers import TransitionsBuilder

builder = TransitionsBuilder(helper)

# Safety-only constraint group
cg = builder.new_constraint_group("unknown", "off", "Turn off immediately if unknown")
builder.add_state_time_constraint(cg, 0)

# Command with minimum time constraint group
cg = builder.new_constraint_group("off", "on", "Command transition with minimum time")
builder.add_state_time_constraint(cg, 60)  # Must be in state for 60s
builder.add_command_constraint(cg, "set_on")  # And have command set

builder.build()
builder.save(config_path) 