from collections import defaultdict
import json
outputs = ["CP_25","CP_26","CP_32","CP_33"]
output_sensors = ["control","readback"]
Temp_sensors = ["temp_0_SHT","temp_1_DHT","temp_2_SCD"]
Humidity_sensors = ["hum_0_DHT","hum_1_SCD"]
CO2_sensors = ["CO2_0"]
outputs_base = zip(outputs,output_sensors)

D_outputs = defaultdict(dict)
for output in outputs:
    D_outputs[output] = output_sensors
print(D_outputs)
D_sensors = defaultdict(dict)
D_sensors["temp"] = Temp_sensors
D_sensors["humidity"] = Humidity_sensors
D_sensors["CO2"] = CO2_sensors

D_fsm = defaultdict(dict)
D_fsm["sensors"] = ["state","time_in_state"]

Big_D = defaultdict(dict)
Big_D["fsm"].update(D_fsm)
Big_D["sys"] = defaultdict(dict)
Big_D["sys"]["sensors"].update(D_sensors)
Big_D["sys"]["outputs"].update(D_outputs)

Biggest_D = defaultdict(dict)
Biggest_D["R"] = (Big_D)
print(Biggest_D)
json.dump(Biggest_D,open("test.json","w"))


## Ok now suppose we're give R.sys.control_points_CP_25.readback.
