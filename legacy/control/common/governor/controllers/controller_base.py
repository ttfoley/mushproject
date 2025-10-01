# control/common/governor/controllers/controller_base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, TYPE_CHECKING # Import TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular import errors at runtime
# if GovernorPointManager also needs to import BaseController eventually
if TYPE_CHECKING:
    # Correct import: Use '..' to go up one level from 'controllers' to 'governor'
    from ..point_manager import GovernorPointManager

class BaseController(ABC):

    @abstractmethod
    def execute_cycle(self, point_manager: 'GovernorPointManager', strategy_settings: Dict[str, Any]) -> None:
        # Use forward reference (string literal) for the type hint here
        """
        Executes one control cycle.

        Implementations should:
        1. Use strategy_settings to identify required input/output point addresses.
        2. Use point_manager.get_point_value() to retrieve current input values.
        3. Perform control calculations.
        4. Use point_manager.update_requested_value() to request changes to output points.
        """
        pass

    # Optional: Could add an __init__ signature if needed, but often left to subclasses
    # def __init__(self, ...):
    #     pass