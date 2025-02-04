from abc import ABC, abstractmethod
from typing import Any

class MessagePublisher(ABC):
    """Abstract interface for message publishing and subscribing"""
    
    @abstractmethod
    def publish(self, topic: str, value: Any) -> bool:
        """Publish a value to a topic. Returns True if successful."""
        pass
    
    @abstractmethod
    def subscribe(self, topic: str) -> None:
        """Subscribe to a topic"""
        pass 