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

# Type alias for all possible action types
AnyAction = WriteAction # Add other action types here in the future

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
AnyConstraintDefinition = Union[StateTimeConstraintDefinition, ValueConstraintDefinition] # Add others to Union

class ConstraintDefinition(BaseModel):
    """Container for a single constraint within a group, matching config structure."""
    definition: AnyConstraintDefinition = Field(..., description="The specific parameters defining the constraint's logic.")
    type: str = Field(..., description="Type of the constraint (e.g., state_time, discrete_value). Must match the type within 'definition'.")
    description: Optional[str] = Field(None, description="Overall description of this constraint instance.")

    @model_validator(mode='after')
    def check_type_match(self) -> Self:
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
    transitions: Dict[str, Dict[str, TransitionDefinition]] = Field(..., description="Definitions for transitions between states.")
    pwm_outputs: Optional[List[DriverPWMOutputMapping]] = Field(None, description="Optional list of PWM output configurations handled by this driver.")

    model_config = {"extra": "forbid"}


# ==============================================================================
# === NEW/UPDATED MODELS FOR MICROCONTROLLER AND GOVERNOR (START) =============
# ==============================================================================

# --- Microcontroller Supporting Sub-Models ---

class I2CConfig(BaseModel):
    sda_pin: int = Field(..., description="GPIO pin number for I2C SDA.")
    scl_pin: int = Field(..., description="GPIO pin number for I2C SCL.")
    clock_speed: Optional[int] = Field(None, description="Optional I2C clock speed in Hz (e.g., 100000).")
    model_config = {"extra": "forbid"}

class I2CDevice(BaseModel):
    # Define the specific sensor models you are using here
    sensor_model: Literal["SHT85", "BME280", "SCD41", "SHT31", "SHT40", "MCP23017"] = Field(...,
        description="Specific model of the sensor/device (e.g., 'SHT85', 'BME280').")
    address: Union[int, str] = Field(..., description="I2C address (e.g., 0x44 or 68).")
    # Define the measurements provided by this sensor model
    point_uuids: Dict[Literal["temperature", "humidity", "co2", "pressure"], str] = Field(...,
        description="Mapping of measurement type (e.g., 'temperature', 'humidity') to Point UUID.")
    settings: Optional[Dict[str, Any]] = Field(None, description="Optional device-specific settings (e.g., {'automatic_self_calibration': False}).")
    model_config = {"extra": "forbid"}

class OneWireConfig(BaseModel):
    pin: int = Field(..., description="GPIO pin number for the OneWire bus.")
    model_config = {"extra": "forbid"}

class OneWireDevice(BaseModel):
    sensor_model: Literal["DS18B20"] = Field(..., description="Specific model of the sensor (e.g., 'DS18B20').")
    point_uuid: str = Field(..., description="Point UUID for the temperature reading from this sensor.")
    model_config = {"extra": "forbid"}

class DHTSensorConfig(BaseModel):
    sensor_model: Literal["DHT11", "DHT22"] = Field(..., description="Specific model of the DHT sensor ('DHT11' or 'DHT22').")
    pin: int = Field(..., description="GPIO pin number connected to the DHT sensor.")
    point_uuids: Dict[Literal["temperature", "humidity"], str] = Field(...,
        description="Mapping of measurement type to Point UUID.")
    model_config = {"extra": "forbid"}

class DigitalOutputConfig(BaseModel):
    pin: int = Field(..., description="GPIO pin number for the digital output.")
    name: Optional[str] = Field(None, description="Logical name for this output (e.g., 'MisterRelay').")
    point_uuid: str = Field(..., description="Point UUID for the command/status of this output.")
    initial_state: Optional[Literal["on", "off"]] = Field("off", description="Initial state on startup ('on' or 'off').")
    model_config = {"extra": "forbid"}

# --- Microcontroller Config Root Model ---

class MicrocontrollerConfig(BaseModel):
    """Pydantic model for a Microcontroller's specific hardware configuration file."""
    # General hardware bus setup
    i2c: Optional[I2CConfig] = Field(None, description="I2C bus configuration, required if i2c_devices are listed.")
    onewire: Optional[OneWireConfig] = Field(None, description="OneWire bus configuration, required if onewire_devices are listed.")
    # spi: Optional[SPIConfig] = None # Add later if needed

    # Lists of connected devices/pins
    i2c_devices: Optional[List[I2CDevice]] = Field(None, description="List of sensors/devices connected via I2C.")
    onewire_devices: Optional[List[OneWireDevice]] = Field(None, description="List of sensors connected via OneWire.")
    dht_sensors: Optional[List[DHTSensorConfig]] = Field(None, description="List of connected DHT sensors.")
    digital_outputs: Optional[List[DigitalOutputConfig]] = Field(None, description="List of configured digital output pins.")
    # digital_inputs: Optional[List[DigitalInputConfig]] = None # Add later if needed

    # Timing parameters controlled by the Microcontroller firmware
    publish_frequency_ms: Optional[int] = Field(None,
        description="Sensor publish interval in milliseconds used by the microcontroller. (e.g., 15000 for 15 seconds). If not set, firmware default applies.")
    output_republish_frequency_ms: Optional[int] = Field(None,
        description="Output status republish interval in milliseconds used by the microcontroller. If not set, firmware default applies.")

    @model_validator(mode='after')
    def check_bus_configs(self) -> Self:
        if self.i2c_devices and not self.i2c:
            raise ValueError("i2c bus configuration must be provided if i2c_devices are listed.")
        if self.onewire_devices and not self.onewire:
             raise ValueError("onewire bus configuration must be provided if onewire_devices are listed.")
        # Add similar check for SPI if implemented
        return self

    model_config = {"extra": "forbid"}


# --- Governor Supporting Sub-Models (REVISED FOR GENERIC CONTROL) ---

# NEW: Configuration specific to a Bang-Bang controller
class BangBangControllerConfig(BaseModel):
    """Configuration for a Bang-Bang (on/off) control loop."""
    controller_type: Literal["bang_bang"] = Field("bang_bang", description="Discriminator field for controller type.")

    # --- Inputs ---
    sensor_point_uuid: str = Field(..., description="UUID of the Point providing the process variable (e.g., temperature sensor).")
    target_setpoint_point_uuid: str = Field(..., description="UUID of the Point providing the desired target value (e.g., target temperature setpoint).")
    # CHANGED: Replaced static hysteresis with a point UUID
    hysteresis_point_uuid: str = Field(..., description="UUID of the Point providing the hysteresis value (deadband).")

    # --- Outputs ---
    output_command_point_uuid: str = Field(..., description="UUID of the Point where the Governor writes the calculated command ('on' or 'off').")

    model_config = {"extra": "forbid"}


# UPDATED: Add controller_type discriminator to PID config
class PIDControllerConfig(BaseModel):
    """Configuration for a single PID control loop within the Governor."""
    controller_type: Literal["pid"] = Field("pid", description="Discriminator field for controller type.")

    # --- Inputs ---
    sensor_point_uuid: str = Field(..., description="UUID of the Point providing the process variable (e.g., temperature sensor).")
    target_setpoint_point_uuid: str = Field(..., description="UUID of the Point providing the desired target value (e.g., target temperature setpoint).")

    # --- Outputs (Points the Governor WRITES TO) ---
    output_pwm_setpoint_point_uuid: str = Field(..., description="UUID of the Point where the Governor writes the calculated PWM duty cycle (0.0-1.0).")
    output_on_duration_point_uuid: str = Field(..., description="UUID of the Point where the Governor writes the calculated ON duration (seconds) for the PWM cycle.")
    output_off_duration_point_uuid: str = Field(..., description="UUID of the Point where the Governor writes the calculated OFF duration (seconds) for the PWM cycle.")
    mode_command_point_uuid: str = Field(..., description="UUID of the Point where the Governor writes its mode command (e.g., 'PWM', 'OFF') to the corresponding Driver.")

    # --- Tuning & Parameters ---
    kp: float = Field(..., description="Proportional gain.")
    ki: float = Field(..., description="Integral gain.")
    kd: float = Field(..., description="Derivative gain.")
    min_output: float = Field(0.0, ge=0.0, le=1.0, description="Minimum output clamp value (usually 0.0).")
    max_output: float = Field(1.0, ge=0.0, le=1.0, description="Maximum output clamp value (usually 1.0).")
    pwm_period_seconds: float = Field(..., gt=0, description="The PWM period this PID loop targets (used to calculate ON/OFF durations). Must match the corresponding Driver's PWM configuration period.")

    model_config = {"extra": "forbid"}


# NEW: Type Alias for the Union of all possible controller configurations
AnyControllerConfig = Union[PIDControllerConfig, BangBangControllerConfig]
# Add future controller config types to this Union, e.g., Union[PIDControllerConfig, BangBangControllerConfig, FuzzyLogicControllerConfig]


# --- Governor Config Root Model (UPDATED) ---

class GovernorConfig(BaseModel):
    """Pydantic model for a Governor's specific configuration file."""
    update_interval_seconds: float = Field(10.0, gt=0, description="How often the Governor runs its control logic loop (in seconds).")
    # UPDATED: List now uses the Union type AnyControllerConfig
    controllers: List[AnyControllerConfig] = Field(...,
        description="List of control loops (e.g., PID, Bang-Bang) managed by this Governor. The 'controller_type' field determines the specific parameters required for each.")
    # Add other potential governor configs - e.g., global settings

    model_config = {"extra": "forbid"}

# ==============================================================================
# === END OF GOVERNOR MODEL SECTION ============================================
# =============================================

