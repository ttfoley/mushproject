# common/governor/mqtt.py

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from typing import Dict, Any, Callable, List
import socket

# Import the interface definition
from ..core.mqtt_interface import MQTTInterface, MessageHandler

class GovernorMQTTHandler: # No need to explicitly inherit if using Protocol
    """
    Concrete implementation of MQTTInterface using Paho MQTT client
    for the Governor layer.
    """
    def __init__(self, client_id: str, broker: str, port: int, username: str, password: str):
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password

        # Internal state to hold registered handlers
        self._message_handlers: Dict[str, MessageHandler] = {}
        self._connect_handlers: List[Callable[[], None]] = []

        # Paho MQTT Client Setup (similar to your existing handler)
        self.client = mqtt.Client(client_id=self.client_id,
                                callback_api_version=CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(self.username, self.password)

        # Assign internal methods to Paho callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect # Good practice to handle disconnects
        # Add other callbacks like on_publish if needed for logging/debugging

        print(f"GovernorMQTTHandler initialized for client ID: {self.client_id}")

    # --- Internal Paho Callback Handlers ---

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Internal callback for Paho client connection."""
        if rc == 0:
            print(f"GovernorMQTTHandler: Connected to MQTT broker {self.broker}")
            # Call all registered connect handlers
            for handler in self._connect_handlers:
                try:
                    handler()
                except Exception as e:
                    print(f"GovernorMQTTHandler Error in connect handler: {e}")
            # Resubscribe to topics on reconnect? Paho might handle this with clean_session=False
        else:
            print(f"GovernorMQTTHandler: Failed to connect to MQTT broker code {rc}")

    def _on_message(self, client, userdata, message):
        """Internal callback for Paho client message."""
        topic = message.topic
        payload = message.payload.decode() # Assuming UTF-8 payload
        # print(f"GovernorMQTTHandler: Raw message received - Topic: {topic}") # Debug

        # Find and call the registered handler for this topic
        if topic in self._message_handlers:
            try:
                self._message_handlers[topic](topic, payload)
            except Exception as e:
                print(f"GovernorMQTTHandler Error in message handler for topic {topic}: {e}")
        else:
            # Optional: Handle messages for topics with no specific handler registered
            # print(f"GovernorMQTTHandler: No specific handler for topic: {topic}")
            pass

    def _on_disconnect(self, client, userdata, rc, properties=None):
        print(f"GovernorMQTTHandler: Disconnected from MQTT broker with code {rc}")
        if rc != 0:
            print("GovernorMQTTHandler: Unexpected disconnection. Paho client should attempt to reconnect automatically.")
        # else: rc == 0 is a clean disconnect initiated by client.disconnect()

    # --- Implementing MQTTInterface Methods ---

    def connect(self) -> None:
        print(f"GovernorMQTTHandler: Attempting connection to {self.broker}...")
        try:
            # Consider specifying clean_session if needed, default might vary
            self.client.connect(self.broker, self.port, 60) # 60s keepalive
        except (socket.error, TimeoutError, OSError) as e: # Catch specific network errors
            print(f"GovernorMQTTHandler: Connection attempt failed - {e}")
            # Potentially raise an exception or set an internal error state
            # raise ConnectionError(f"Failed to connect to MQTT broker: {e}") from e
        except Exception as e: # Catch any other unexpected errors
            print(f"GovernorMQTTHandler: Unexpected error during connection: {e}")
            # raise # Re-raise unexpected errors?

    def disconnect(self) -> None:
        print("GovernorMQTTHandler: Disconnecting...")
        self.client.disconnect()

    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> bool:
        # print(f"GovernorMQTTHandler: Publishing to {topic}: {payload}") # Debug
        # Paho handles basic type conversion usually, but ensure payload is suitable
        msg_info = self.client.publish(topic, str(payload), qos=qos, retain=retain)
        # msg_info.is_published() might take time, rc=0 means accepted by Paho buffer
        if msg_info.rc == mqtt.MQTT_ERR_SUCCESS:
            # print(f"GovernorMQTTHandler: Publish successful (queued) mid={msg_info.mid}")
            return True
        else:
            print(f"GovernorMQTTHandler Warning: Publish failed for topic {topic}, rc={msg_info.rc}")
            return False

    def subscribe(self, topic: str, qos: int = 1) -> None:
        print(f"GovernorMQTTHandler: Subscribing to {topic}")
        self.client.subscribe(topic, qos=qos)

    def register_message_handler(self, topic: str, handler: MessageHandler) -> None:
        print(f"GovernorMQTTHandler: Registering handler for topic {topic}")
        self._message_handlers[topic] = handler

    def register_connect_handler(self, handler: Callable[[], None]) -> None:
        print("GovernorMQTTHandler: Registering connect handler")
        self._connect_handlers.append(handler)

    def loop_start(self) -> None:
        print("GovernorMQTTHandler: Starting background loop...")
        self.client.loop_start()

    def loop_stop(self) -> None:
        print("GovernorMQTTHandler: Stopping background loop...")
        self.client.loop_stop()

    def is_connected(self) -> bool:
        # Relies on Paho's internal state check
        return self.client.is_connected()