#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import time
import json

# MQTT Configuration
MQTT_BROKER: str = "192.168.1.17" ## Don't know why this type hint is needed all the sudden
MQTT_PORT: int = 1883
MQTT_USERNAME: str = "ttfoley"
MQTT_PASSWORD: str = "password"
MQTT_CLIENT_ID: str = "fake_pwm_heater"

# Topic for temperature driver command
COMMAND_TOPIC = "mush/drivers/temperature_driver/command/state"

# PWM settings (in seconds)
TIME_ON = 1
TIME_OFF = 480

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")

def main():
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

        print(f"Starting PWM simulation (ON: {TIME_ON}s, OFF: {TIME_OFF}s)")
        while True:
            # Turn ON
            print("Publishing ON")
            client.publish(COMMAND_TOPIC, "on", qos=1)
            time.sleep(TIME_ON)

            # Turn OFF
            print("Publishing OFF")
            client.publish(COMMAND_TOPIC, "off", qos=1)
            time.sleep(TIME_OFF)

    except KeyboardInterrupt:
        print("\nStopping PWM simulation")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
