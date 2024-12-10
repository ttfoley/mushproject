import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from datetime import datetime
mqtt_uname = "ttfoley"
mqtt_pwd = "password"
mqtt_broker = "192.168.1.17"
mqtt_port = 1883
mqtt_client_id = "control"
control_led_topic = "mush/controller2/control/led1"

to_subscribe = ["mush/controller2/control/pin25","mush/controller2/control/pin26","mush/controller2/control/pin32","mush/controller2/control/pin33",
                "mush/controller2/control/pin25_rb","mush/controller2/control/pin26_rb","mush/controller2/control/pin32_rb","mush/controller2/control/pin33_rb",]

def on_message(client, userdata, msg:mqtt.MQTTMessage):
    print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")

def on_connect(client:mqtt.Client, userdata, flags, rc,properties = None):
    # For paho-mqtt 2.0.0, you need to add the properties parameter.
    # def on_connect(client, userdata, flags, rc, properties):
    if rc == 0:
        print("Connected to MQTT Broker!")
        for topic in to_subscribe:
            client.subscribe(topic)

    else:
        print("Failed to connect, return code %d\n", rc)


def on_publish(client, userdata, mid,reason_code="Success", properties=None):
    print("Message published with mid: " + str(mid))

def connect_mqtt(client_id, broker, port, username, password):

    # Set Connecting Client ID
    client = mqtt.Client(client_id=client_id,callback_api_version=CallbackAPIVersion.VERSION2)

    #TODO: username and password in environment variables
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_publish = on_publish
    #Todo: return status of connection, verify connection
    client.connect(broker, port)
    return client


def main():
    #TODO: verify the connection, add reconnect logic
    client = connect_mqtt(mqtt_client_id, mqtt_broker, mqtt_port,mqtt_uname, mqtt_pwd)
    client.loop_start()
    t0 = datetime.now()
    print(t0)
    i = 0 
    message_sent = False
    while True:

        t1 = datetime.now()

        if (t1 - t0).total_seconds() > 1:
            i += 1
            t0 = t1
            message_sent = False

        if i!= 0:
            if (i % 5 == 0) and (i % 10 == 0):
                if not message_sent:
                    print(i,"turn off")
                    client.publish(control_led_topic, "off")
                    message_sent = True

            elif (i % 5) == 0:
                if not message_sent:
                    print(i,"turn on")
                    client.publish(control_led_topic, "on")
                    message_sent = True


    client.loop_stop()
if __name__ == "__main__":
    main()