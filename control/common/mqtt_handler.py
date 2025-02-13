import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from typing import Dict, Any

class MQTTHandler():
    def __init__(self, client_id, broker, port, username, password):
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password

        self.client = mqtt.Client(client_id=self.client_id, 
                                callback_api_version=CallbackAPIVersion.VERSION2,
                                userdata=None)
        self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_publish = self.on_publish
        
        self._message_handlers = {}  # topic -> callback
        self._connect_handlers = []

    def register_message_handler(self, topic: str, handler):
        """Register callback for specific topic"""
        self._message_handlers[topic] = handler

    def register_connect_handler(self, handler):
        """Register callback for connect events"""
        self._connect_handlers.append(handler)

    def _on_message(self, client, userdata, message):
        """MQTT callback when message received"""
        topic = message.topic
        value = message.payload.decode()
        print(f"MQTT Handler received message - topic: {topic}, value: {value}")
        
        if topic in self._message_handlers:
            print(f"Found handler for topic: {topic}")
            self._message_handlers[topic](topic, value)
        else:
            print(f"No handler registered for topic: {topic}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Called when client connects to broker"""
        if rc == 0:
            print("Connected to MQTT broker")
            for handler in self._connect_handlers:
                handler()
        else:
            print(f"Failed to connect to MQTT broker with code {rc}")

    def on_publish(self, client, userdata, mid, reason_code="Success", properties=None):
        print("Message published with mid: " + str(mid))

    def publish(self, topic: str, value: Any) -> bool:
        result = self.client.publish(topic, value)
        return result[0] == 0  # Return True if successful

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

    def subscribe(self, topic: str) -> None:
        self.client.subscribe(topic)