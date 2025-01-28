from collections import defaultdict
import json
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

"""Herein we're going to try to build the hierarchy of the systems, starting with the lowest level (control points and sensors) and working
our way up to the physical system as whole + the FSM. Try to keep individual dictionaries as shallow as possible.
Every leaf MUST have a .value attribute attached to it.
I don't even use the UUIDs right now, but thought they may come in handy down the road.
Now all of the manually typed config info could be passed via another config as well, but I feel like having this as config script is ok middle ground for now.
Note that every leaf for the sys.sensors and sys.control points better have enough info to construct its Value class, including the class of the value. Ideally we would
encode more at the base level and things like the class would be enforced/follow by construction.
And even the topology could be defined using a bare json I guess.
Speaking of "Topology":
R
--fsm
----sensors
------time_in_state  ##These are "virtual sensors" so don't have all of the baggage.
------state

--sys
----sensors
------temperature
--------t_sht_0
----------read_addr
----------class
--------t_dht_0
-----control_points
--------CP_25
----------readback
------------read_addr
------------class
----------control
------------write_addr
------------class ()

"""


#These are the definition of all of the remote values.  They are the lowest level of the hierarchy.



##First the control points
UUID = 0
parent_rb_addr = {"CP_" + str(i):f"mush/controller2/readback/pin{i}" for i in [25,26,32,33]}
parent_control_addr = {"CP_" + str(i):f"mush/controller2/control/pin{i}" for i in [25,26,32,33]}

#Define the parent level of the considered hierarchy
control_points = defaultdict(dict)
for cp in parent_rb_addr.keys():
    control_points[cp]["readback"] = {"uuid":UUID,"read_addr":parent_rb_addr[cp],"class":"Remote_Read","valid_values":["Unknown","On","Off"]}
    UUID +=1
    control_points[cp]["control"] = {"uuid":UUID,"write_addr":parent_control_addr[cp],"class":"Remote_Write","valid_values":["On","Off"]}
    UUID +=1
##Now the sensors
temp_sensors = {
    "t_sht_0": "mush/controller1/sht/temperature",
    "t_dht_0": "mush/controller1/dht/temperature",
    "t_scd_0": "mush/controller1/scd/temperature"
}
humid_sensor = {
    "s_dht_0": "mush/controller1/sht/humidity",
    "h_dht_0": "mush/controller1/dht/humidity",
    "h_scd_0": "mush/controller1/scd/humidity"
}
co2_sensors = {
    "co2_0": "mush/controller1/scd/co2"
}

#Define the parent level of the considered hierarchy
#I separated out types of sensors, so that's one more key you need to access.
sensors = defaultdict(dict)
for p,d in zip(["temperature","humidity","co2"],[temp_sensors,humid_sensor,co2_sensors]):
    sensors[p] = defaultdict(dict)
    for k,v in d.items():
        #Defaults like this shouldn't be stored in a python ficle probably. Just creates confusion about where things are.
        upper_bound = 100
        lower_bound = 0
        if p == "co2":
            upper_bound = 10000
        sensors[p][k] = {"uuid":UUID,"read_addr":v,"class":"Remote_Sensor","upper_bound":upper_bound,"lower_bound":lower_bound}
        UUID +=1

#Then the fsm stuff.
#Not sure how to make it seems like it's on the same level as the control points and sensors, since it doesn't have all of that extra info needed.
fsm = defaultdict(dict)
fsm["sensors"] = {"time_in_state": None, "state": None}##

R = defaultdict(dict)
R = {"fsm":fsm,"sys":{"sensors":sensors,"control_points":control_points}}

json.dump(R,open(config_path+"/points.json","w"),indent=4)


