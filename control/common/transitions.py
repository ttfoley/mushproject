from controller import *

##Where great new transitions are born! Full rewrite of the transitions modules to allow for more complex constraints and transitions.
##And to clean up areas of code that had to do extra work to make the old transitions work. And I also just didnt really like them.




"""A transition is defined between two state. Transitions occur when you're in the "from" state all of the constraint
on the edge to "to" state are satisfied. The constrains can now be pretty arbirary and multi-level. At the base level, there are binary 
constraints like constr_1 = "time_in_state > 30." -> bool. But you can also make a complex constraint by /\ multiple base constraints together.
These combinations of constraints as a whole still evaluate to a bool. We call this collection a ConstraintGroup. Now the most simple case
of state_time > 30 is just a ConstraintGroup with one constraint, which may seems like uncessary overhead.. but I've written a script!
Finally, you can have multiple ConstraintGroups on a single transition (All ORd together for now.) The most obvious case where this be helpful you were to wire all of your states 
to "safe" off state, no matter other ConstraintGroups are on that edge, you can always add a "safe" ConstraintGroup to bypass. Say, for example, esp32 being
weird so you don't actually know state of equipment and how long it's been running. You can have universal transitions to "Off" if you think it's been too long.
"""


















class TransitionMaster:
    def __init__(self, some form of all the transition information):
        pass

    @property
    def next_state(self) -> State:
    #This is all the info the FSM needs!.
        pass
    