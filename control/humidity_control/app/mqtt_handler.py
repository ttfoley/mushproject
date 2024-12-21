import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from controller import ControlPoint

class MQTTHandler:
    def __init__(self, client_id, broker, port, username, password,userdata:dict[str,ControlPoint]):
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.userdata = userdata
        self.client = mqtt.Client(client_id=self.client_id, callback_api_version=CallbackAPIVersion.VERSION2,userdata=None)
        self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish

    def on_message(self, client, userdata, msg:mqtt.MQTTMessage):
        #print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        message = msg.payload.decode()
        #print(message,msg.topic)
        #values of 1.00 and -1.00 are from the arduino code, and those seem kind of silly.
        for _,point in self.userdata.items():
            if point._readback_point == msg.topic:
                if message == "1.00":
                    point.set_known_state("On")
                elif message == "-1.00":
                    point.set_known_state("Off")
                else:
                    point.set_known_state("Unknown")
                #print(f"Set state of {point.name} to {point.state}")

    def on_connect(self, client:mqtt.Client, userdata, flags, rc, properties=None):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)

    def on_publish(self, client, userdata, mid, reason_code="Success", properties=None):
        print("Message published with mid: " + str(mid))

    def publish(self, topic, msg):
        result = self.client.publish(topic, msg)
        status = result[0]
        if status == 0:
            print(f"Send `{msg}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")

    def connect(self):
        self.client.connect(self.broker, self.port)

    def loop_forever(self):
        self.client.loop_forever()

    def loop_start(self):
        self.client.loop_start()

    def loop_stop(self):  
        self.client.loop_stop()

    def is_connected(self):
        return self.client.is_connected()
    
    def reconnect(self):
        self.client.reconnect()