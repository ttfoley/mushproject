from typing import Protocol, Callable, Any

# Define a type alias for the message handler callback
# It should accept topic (str) and payload (usually str)
MessageHandler = Callable[[str, str], None]

class MQTTInterface(Protocol):
    """Defines the standard interface for MQTT communication handling."""

    def connect(self) -> None:
        """Initiates connection to the MQTT broker."""
        ... # Protocol definitions use ...

    def disconnect(self) -> None:
        """Disconnects from the MQTT broker."""
        ...

    def publish(self, topic: str, payload: Any, qos: int = 1, retain: bool = False) -> bool:
        """
        Publishes a message to a topic.

        Args:
            topic: The MQTT topic.
            payload: The message payload (will likely be converted to string/bytes).
            qos: Quality of Service level (0, 1, or 2).
            retain: Retain flag.

        Returns:
            True if publishing was successful (e.g., message queued), False otherwise.
        """
        ...

    def subscribe(self, topic: str, qos: int = 1) -> None:
        """Subscribes to an MQTT topic."""
        ...

    def register_message_handler(self, topic: str, handler: MessageHandler) -> None:
        """
        Registers a callback function to handle messages received on a specific topic.
        The handler should accept topic (str) and payload (str).
        """
        ...

    def register_connect_handler(self, handler: Callable[[], None]) -> None:
        """Registers a callback function to be called upon successful connection."""
        ...

    def loop_start(self) -> None:
        """Starts the MQTT client's network loop in a background thread."""
        ...

    def loop_stop(self) -> None:
        """Stops the MQTT client's network loop."""
        ...

    def is_connected(self) -> bool:
        """Returns True if the client is currently connected to the broker."""
        ...