import os
import sys
import json
current_dir = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_dir, '../../common')
config_path = os.path.join(current_dir, '../config')
sys.path.append(lib_path)

from construction import Constructor,Configuration


config = Configuration(config_path)
constructor = Constructor(config)
mqtt_handler = constructor.mqtt_handler
mqtt_handler.connect()
constructor.subscribe_mqtt(mqtt_handler)
fsm = constructor.fsm
surveyor = constructor.surveyor
print(constructor.transitions_manager.next_state(fsm.current_state))