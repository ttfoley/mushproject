import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from datetime import datetime
import time
from mqtt_handler import MQTTHandler
from controller import ControlPoint,State,Humidity_Control,output_value,transition_rule
mqtt_uname = "ttfoley"
mqtt_pwd = "password"
mqtt_broker = "192.168.1.17"
mqtt_port = 1883
mqtt_client_id = "control_test"


to_subscribe = ["mush/controller2/control/led1","mush/controller2/control/pin25","mush/controller2/control/pin26","mush/controller2/control/pin32",
                "mush/controller2/control/pin33","mush/controller2/readback/led1","mush/controller2/readback/pin25",
                "mush/controller2/readback/pin26","mush/controller2/readback/pin32","mush/controller2/readback/pin33"]

state_output_defs = {"Off":[output_value("pin25","Off"),output_value("pin33","Off")],"HumidOn":[output_value("pin25","On"),output_value("pin33","Off")],
                     "Humidify":[output_value("pin25","On"),output_value("pin33","On")],"FanOff":[output_value("pin25","On"),output_value("pin33","Off")]}

#for now only one rule per state
state_rules = {"Off":transition_rule("0","Off","HumidOn",1*60),"HumidOn":transition_rule("1","HumidOn","Humidify",15),
               "Humidify":transition_rule("2","Humidify","FanOff",2*60),"FanOff":transition_rule("3","FanOff","Off",15)}
def main():
    #TODO: verify the connection, add reconnect logic
    mqtt_handler.loop_start()
    while True:
        humid_control.update_state()
        print(humid_control.current_state,humid_control.desired_state,humid_control.time_in_state)
        changed = humid_control.update_desired_state()
        if changed:
            print(f"Desired changed to {humid_control.desired_state}")
        humid_control.write_desired_state()
        time.sleep(15)

    mqtt_handler.loop_stop()


if __name__ == "__main__":

    control_points = {point_name:ControlPoint(point_name,f"mush/controller2/control/{point_name}",f"mush/controller2/readback/{point_name}") 
                      for point_name in ["led1","pin25","pin26","pin32","pin33"]}

    states = {}
    for state_name,outputs in state_output_defs.items():
        states[state_name] = State(state_name,outputs,control_points,state_rules[state_name])

    mqtt_handler = MQTTHandler(mqtt_client_id, mqtt_broker, mqtt_port, mqtt_uname, mqtt_pwd,userdata=control_points)
    mqtt_handler.connect()
    humid_control = Humidity_Control(states,mqtt_handler,"Humidify")

    #I don't like how this is separate, but you can't add args to the callbacks...
    for topic in to_subscribe:
        mqtt_handler.client.subscribe(topic)

    main()