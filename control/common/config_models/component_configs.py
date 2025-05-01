# common/config_models/component_configs.py

import enum
from typing import Any, Dict, List, Optional, Union, Literal, Self
from pydantic import BaseModel, Field, model_validator

# --- Enums ---

class ComparatorType(str, enum.Enum):
    """Comparison operators."""
    EQ = "=="
    NE = "!="
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="

# --- Action Definitions ---

class WriteAction(BaseModel):
    """Action to write a specific value to a given point."""
    action_type: Literal["write_to_point"] = Field("write_to_point", description="Type indicator for this action.")
    point_uuid: str = Field(..., description="UUID of the Point to write to.")
    value: Any = Field(..., description="The value to write to the point.")

    model_config = {"extra": "forbid"}

# Add other action types here in the future (e.g., StartTimerAction, LogMessageAction)
# class OtherAction(BaseModel):
#    action_type: Literal["other_action"] = "other_action"
#    ...

# Type alias for all possible action types
AnyAction = WriteAction # Add OtherAction etc. here

# --- State Definition ---

class StateCondition(BaseModel):
    """A single condition (point value check) required to be true for defining a state."""
    point_uuid: str = Field(..., description="UUID of the point whose value is checked.")
    expected_value: Any = Field(..., description="The value the point must have.")

    model_config = {"extra": "forbid"}

class StateDefinition(BaseModel):
    """Defines a state by its required conditions and optional entry/exit actions."""
    defining_conditions: List[StateCondition] = Field(...,
        description="List of conditions that MUST ALL be true simultaneously for the system to BE considered in this state.")
    entry_actions: List[AnyAction] = Field([],
        description="List of actions to perform immediately upon entering this state.")
    exit_actions: List[AnyAction] = Field([],
        description="List of actions to perform immediately upon exiting this state.")

    model_config = {"extra": "forbid"}

# --- Constraint Definitions ---

class BaseConstraintDefinition(BaseModel):
    """Base model for the specific parameters defining a constraint's logic."""
    # Type field is defined in subclasses using Literal
    description: Optional[str] = Field(None, description="Optional description of the constraint's purpose.")
    id: Optional[int] = Field(None, description="Optional numeric identifier for this constraint definition.")

    model_config = {"extra": "forbid"}

class ValueConstraintDefinition(BaseConstraintDefinition):
    """
    Constraint comparing point A's value against point B's value OR a static value B.
    Evaluates: value(point_A) <comparator> value(point_B / static_value_B)
    """
    type: Literal["value", "discrete_value", "continuous_value"] = Field(..., description="Type indicator for value comparison.")
    value_A_point_uuid: str = Field(..., description="UUID of the primary Point (A) whose value is being checked.")
    comparator: ComparatorType = Field(..., description="The comparison operator.")
    comparand_B_static_value: Optional[Any] = Field(None, description="Static value (B) to compare against. Use EITHER this OR comparand_B_point_uuid.")
    comparand_B_point_uuid: Optional[str] = Field(None, description="UUID of the Point (B) providing the dynamic value to compare against. Use EITHER this OR comparand_B_static_value.")

    @model_validator(mode='after')
    def check_comparand_b_source(self) -> Self:
        static_present = self.comparand_B_static_value is not None
        point_present = self.comparand_B_point_uuid is not None
        if static_present == point_present: # True if both are present or both are absent
            raise ValueError('Exactly one of "comparand_B_static_value" or "comparand_B_point_uuid" must be provided for ValueConstraintDefinition')
        return self

class StateTimeConstraintDefinition(BaseConstraintDefinition):
    """
    Constraint comparing time in state (Point A) against a static duration (B) OR a dynamic duration from Point B.
    Evaluates: value(time_in_state_A) <comparator> value(duration_point_B / static_duration_B)
    """
    type: Literal["state_time"] = Field(..., description="Type indicator for state time comparison.")
    value_A_point_uuid: str = Field(..., description="UUID of the Point representing time elapsed in the current state (A).")
    comparator: ComparatorType = Field(ComparatorType.GE, description="Comparison operator (usually >= for time).")
    comparand_B_static_value: Optional[float] = Field(None, description="Static duration value (B, in seconds). Use EITHER this OR comparand_B_point_uuid.")
    comparand_B_point_uuid: Optional[str] = Field(None, description="UUID of the Point (B) providing the dynamic duration value. Use EITHER this OR comparand_B_static_value.")

    @model_validator(mode='after')
    def check_comparand_b_source(self) -> Self:
        static_present = self.comparand_B_static_value is not None
        point_present = self.comparand_B_point_uuid is not None
        if static_present == point_present: # True if both are present or both are absent
            raise ValueError('Exactly one of "comparand_B_static_value" or "comparand_B_point_uuid" must be provided for StateTimeConstraintDefinition')
        return self

# Type alias for all possible constraint definition types
# Add other constraint definition types here (e.g., RateOfChangeConstraintDefinition)
AnyConstraintDefinition = Union[StateTimeConstraintDefinition, ValueConstraintDefinition] # Add others to Union

class ConstraintDefinition(BaseModel):
    """Container for a single constraint within a group, matching config structure."""
    # Assuming 'definition' holds the specific typed parameters, and 'type'/'description' are alongside it
    definition: AnyConstraintDefinition = Field(..., description="The specific parameters defining the constraint's logic.")
    type: str = Field(..., description="Type of the constraint (e.g., state_time, discrete_value). Must match the type within 'definition'.")
    description: Optional[str] = Field(None, description="Overall description of this constraint instance.")

    @model_validator(mode='after')
    def check_type_match(self) -> Self:
        # Check if definition is not None and has a 'type' attribute before comparing
        if self.definition and hasattr(self.definition, 'type') and self.type != self.definition.type:
             raise ValueError(f"Outer constraint type '{self.type}' does not match definition type '{self.definition.type}'")
        return self

    model_config = {"extra": "forbid"}

# --- Constraint Group & Transition Definition ---

class ConstraintGroup(BaseModel):
    """A group of constraints that must ALL be met (logical AND)."""
    id: Optional[int] = Field(None, description="Optional numeric identifier for the group.")
    constraints: List[ConstraintDefinition] = Field(..., description="List of constraints in this group (AND logic).")
    description: Optional[str] = Field(None, description="Description of this constraint group's purpose.")
    priority: int = Field(0, description="Priority for evaluating this group (lower value = higher priority).")

    model_config = {"extra": "forbid"}

class TransitionDefinition(BaseModel):
    """Defines the conditions for transitioning to a target state."""
    constraint_groups: List[ConstraintGroup] = Field(...,
        description="List of constraint groups. Transition occurs if ANY group is met (OR logic). Evaluated in priority order.")

    model_config = {"extra": "forbid"}

# --- PWM Output Mapping ---

class DriverPWMOutputMapping(BaseModel):
    """Maps a PWM setpoint input point to a physical actuator output point and defines period."""
    input_point_uuid: str = Field(..., description="UUID of the Point providing the PWM setpoint (e.g., 0.0-1.0 value).")
    output_actuator_uuid: str = Field(..., description="UUID of the ON/OFF Point controlling the physical actuator.")
    pwm_period_seconds: float = Field(..., gt=0, description="The period (in seconds) over which the PWM cycle repeats (must be > 0).")

    model_config = {"extra": "forbid"}

# --- Driver Config Root Model ---

class DriverConfig(BaseModel):
    """Pydantic model for a Driver's complete configuration file."""
    initial_state: str = Field(..., description="The name of the state the driver should start in.")
    states: Dict[str, StateDefinition] = Field(..., description="Definitions for each possible state (map of state_name -> state_definition).")
    # Transitions: Dict[FromStateName, Dict[ToStateName, TransitionDefinition]]
    transitions: Dict[str, Dict[str, TransitionDefinition]] = Field(..., description="Definitions for transitions between states.")
    pwm_outputs: Optional[List[DriverPWMOutputMapping]] = Field(None, description="Optional list of PWM output configurations handled by this driver.")
    # Add other driver-specific config sections here as needed
    # safety_configs: Optional[Any] = None

    model_config = {"extra": "forbid"}