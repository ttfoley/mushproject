# control/common/governor/mqtt.py

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from typing import Dict, Any, Callable, List
import socket # Needed for connection error handling
import logging # Needed for logging

# Import the interface definition
try:
    from ..core.mqtt_interface import MQTTInterface, MessageHandler
except ImportError:
    # Fallback if run directly or path issues
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from common.core.mqtt_interface import MQTTInterface, MessageHandler


# Setup logger for this module
logger = logging.getLogger(__name__)


class GovernorMQTTHandler: # No need to explicitly inherit if using Protocol
    """
    Concrete implementation of MQTTInterface using Paho MQTT client
    for the Governor layer. Includes debugging logs.
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

        # Paho MQTT Client Setup
        self.client = mqtt.Client(client_id=self.client_id,
                                callback_api_version=CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(self.username, self.password)

        # Assign internal methods to Paho callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        # Add other callbacks like on_publish if needed for logging/debugging
        # self.client.on_publish = self._on_publish

        logger.info(f"GovernorMQTTHandler initialized for client ID: {self.client_id}")

    # --- Internal Paho Callback Handlers ---

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Internal callback for Paho client connection."""
        if rc == 0:
            logger.info(f"GovernorMQTTHandler: Connected to MQTT broker {self.broker}")
            # Call all registered connect handlers
            for handler in self._connect_handlers:
                try:
                    handler()
                except Exception as e:
                    logger.error(f"GovernorMQTTHandler Error in connect handler: {e}", exc_info=True)
        else:
            logger.error(f"GovernorMQTTHandler: Failed to connect to MQTT broker code {rc}")

    def _on_message(self, client, userdata, message):
        """Internal callback for Paho client message."""
        topic = message.topic
        try:
            payload = message.payload.decode('utf-8')
        except UnicodeDecodeError:
            payload = f"ERROR: Could not decode payload (Bytes: {message.payload!r})"
            logger.warning(f"Could not decode payload for topic '{topic}'")
        logger.info(f"RAW MQTT RECV: Topic='{topic}', Payload='{payload}'")
        # ---> Log 1: Confirm message arrival at the handler level <---
        #logger.info(f"DEBUG MQTT Handler _on_message: Received Raw Topic='{topic}', Payload='{payload}'")

        # ---> Log 2: Log the registered handlers just before lookup <---
        #logger.info(f"DEBUG MQTT Handler: Checking handlers. Registered keys: {list(self._message_handlers.keys())}")

        # Find and call the registered handler for this topic
        if topic in self._message_handlers:
            # ---> Log 3: Confirm handler was found <---
            logger.info(f"DEBUG MQTT Handler _on_message: Found handler for '{topic}'")
            try:
                # This calls GPM.process_incoming_message if registration worked
                self._message_handlers[topic](topic, payload)
            except Exception as e:
                # Log the exception details if the handler fails
                logger.error(f"GovernorMQTTHandler Error calling message handler for topic '{topic}': {e}", exc_info=True)
        else:
            # ---> Log 4: Confirm handler was NOT found <---
            logger.info(f"DEBUG MQTT Handler _on_message: NO specific handler registered for topic: '{topic}'")
            pass # Continue silently if no handler registered

    def _on_disconnect(self, client, userdata, rc, properties=None):
         """Internal callback for Paho client disconnect."""
         logger.info(f"GovernorMQTTHandler: Disconnected from MQTT broker with code {rc}")
         if rc != 0:
             logger.warning("GovernorMQTTHandler: Unexpected disconnection. Paho client may attempt to reconnect automatically.")

    # Example _on_publish if needed for debugging publishes
    # def _on_publish(self, client, userdata, mid):
    #     logger.debug(f"MQTT message published with MID: {mid}")

    # --- Implementing MQTTInterface Methods ---

    def connect(self) -> None:
        logger.info(f"GovernorMQTTHandler: Attempting connection to {self.broker}:{self.port}...")
        try:
            # Added error handling for connection
            self.client.connect(self.broker, self.port, 60) # 60s keepalive
        except (socket.error, TimeoutError, OSError) as e:
            logger.error(f"GovernorMQTTHandler: Network connection attempt failed - {e}")
            # Depending on design, might want to raise an exception here
            # raise ConnectionError(f"Failed to connect to MQTT broker: {e}") from e
        except Exception as e:
            logger.error(f"GovernorMQTTHandler: Unexpected error during connection: {e}", exc_info=True)
            # raise # Optionally re-raise unexpected errors

    def disconnect(self) -> None:
        logger.info("GovernorMQTTHandler: Disconnecting client...")
        self.client.disconnect()

    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> bool:
        logger.debug(f"GovernorMQTTHandler: Publishing to '{topic}': {payload}")
        try:
            # Convert payload to string, handle potential errors during conversion
            payload_str = str(payload)
            msg_info = self.client.publish(topic, payload_str, qos=qos, retain=retain)
            msg_info.wait_for_publish(timeout=1.0) # Wait briefly for publish ACK for QoS1/2
            if msg_info.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Publish successful (rc=0, mid={msg_info.mid}) for topic {topic}")
                return True
            else:
                logger.warning(f"Publish failed for topic '{topic}', rc={msg_info.rc}")
                return False
        except ValueError as e:
             logger.error(f"Publish failed for topic '{topic}': Error converting payload to string - {e}")
             return False
        except RuntimeError as e:
             logger.error(f"Publish failed for topic '{topic}': MQTT client runtime error (e.g., disconnected) - {e}")
             return False
        except Exception as e:
             logger.error(f"Publish failed for topic '{topic}': Unexpected error - {e}", exc_info=True)
             return False


    def subscribe(self, topic: str, qos: int = 1) -> None:
        logger.info(f"GovernorMQTTHandler: Subscribing to '{topic}' with QoS {qos}")
        # Add error handling? Paho might handle errors internally or in callbacks
        result, mid = self.client.subscribe(topic, qos=qos)
        if result == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Subscription request successful (mid={mid}) for topic '{topic}'")
        else:
            logger.warning(f"Subscription request failed (rc={result}) for topic '{topic}'")


    def register_message_handler(self, topic: str, handler: MessageHandler) -> None:
        # Added logging here
        logger.info(f"DEBUG MQTT Handler: Registering handler for topic '{topic}' with handler {getattr(handler, '__name__', repr(handler))}")
        self._message_handlers[topic] = handler

    def register_connect_handler(self, handler: Callable[[], None]) -> None:
        logger.info(f"GovernorMQTTHandler: Registering connect handler {getattr(handler, '__name__', repr(handler))}")
        self._connect_handlers.append(handler)

    def loop_start(self) -> None:
        logger.info("GovernorMQTTHandler: Starting background loop...")
        self.client.loop_start()

    def loop_stop(self) -> None:
        logger.info("GovernorMQTTHandler: Stopping background loop...")
        self.client.loop_stop() # Allow time for disconnect

    def is_connected(self) -> bool:
        # Use Paho's method
        connected = self.client.is_connected()
        logger.debug(f"MQTT is_connected check: {connected}")
        return connected