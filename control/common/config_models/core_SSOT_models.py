# common/config_models/core_SSOT_models.py

import enum
# Make sure Literal and Union are imported from typing
from typing import Any, Dict, List, Optional, Union, Literal 
# from pydantic import BaseModel, Field, FilePath # If using FilePath
from pydantic import BaseModel, Field

# --- Enums for controlled vocabulary ---

class ValueType(str, enum.Enum):
    """Defines the type of value a point represents."""
    CONTINUOUS = "CONTINUOUS"
    DISCRETE = "DISCRETE"
    BOOLEAN = "BOOLEAN"

class DataSourceLayer(str, enum.Enum):
    """Indicates the primary source layer of a point's data."""
    MICROCONTROLLER = "microcontroller"
    DRIVER = "driver"
    DATA_PROCESSOR = "data_processor"
    GOVERNOR = "governor"
    MANUAL_INPUT = "manual_input"
    # Add others as needed

class AccessMode(str, enum.Enum):
    """Defines read/write access for a point."""
    READ_ONLY = "READ_ONLY"
    READ_WRITE = "READ_WRITE"


class ComponentType(str, enum.Enum):
    """Defines the types of components in the system."""
    MICROCONTROLLER = "microcontroller"
    DRIVER = "driver"
    GOVERNOR = "governor"
    DATA_PROCESSOR = "data_processor"
    # Add others as needed

# --- Core SSOT Models ---

class MQTTBrokerConfig(BaseModel):
    """Configuration for the MQTT Broker connection."""
    host: str = Field(..., description="Hostname or IP address of the MQTT broker.")
    port: int = Field(1883, description="Port number for the MQTT broker.") # Default MQTT port

    model_config = {
        "extra": "forbid" # Disallow extra fields not defined in the model
    }


class PointValidationRules(BaseModel):
    """Optional validation rules for a point's value."""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None # Use for DISCRETE types

    model_config = {
        "extra": "forbid" 
    }

class PointPWMDetails(BaseModel):
    """Optional details specific to PWM-controlled points (often setpoints)."""
    # As per decision log, period seems to live in Driver config. 
    # This might hold other conceptual PWM info if needed, or be removed.
    # For now, let's keep it minimal or empty.
    # Example: purpose: Optional[str] = None 
    pass # Placeholder - refine based on Decision 10 usage. Perhaps not needed here.

    model_config = {
        "extra": "forbid" 
    }


class PointDefinition(BaseModel):
    """Defines a single logical data point within the system."""
    uuid: str = Field(..., description="Persistent unique identifier for the point (e.g., UUID v4 string).")
    name: str = Field(..., description="Human-readable identifier (e.g., FruitingChamber_Temp_Sensor). Should be unique.")
    description: Optional[str] = Field(None, description="Optional longer description of the point.")
    value_type: ValueType = Field(..., description="The type of value the point holds (e.g., CONTINUOUS).")
    # Consider making units an Enum later if vocabulary stabilizes
    units: str = Field(..., description="Units of measurement or value state (e.g., degC, percent_RH, ON/OFF, PWM_DUTY_CYCLE).") 
    data_source_layer: DataSourceLayer = Field(..., description="The system layer primarily responsible for publishing this point's data.")
    access: AccessMode = Field(..., description="Read/write access control for the point.")
    # List of Component IDs or Command Hierarchy levels allowed to write. Validation done later.
    writable_by: Optional[List[str]] = Field(None, description="Components/levels allowed to write (for READ_WRITE points).") 
    validation_rules: Optional[PointValidationRules] = Field(None, description="Optional rules to validate the point's value.")
    initial_value: Optional[Any] = Field(None, description="Optional default value on startup or reset.")
    persist_to_db: bool = Field(False, description="Flag indicating if this point's data should be persisted to the time-series database.")
    
    # pwm_details: Optional[PointPWMDetails] = Field(None, description="Optional details for PWM points.") # Revisit based on Decision 10 - likely not needed here.
    # Optional fields for linking command/status pairs for actuators/control points
    command_point_uuid: Optional[str] = Field(None, description="If this is a status point, the UUID of the corresponding command point.")
    status_point_uuid: Optional[str] = Field(None, description="If this is a command point, the UUID of the corresponding status readback point.")

# We'd also add validation later (likely in build.py or using Pydantic root_validators) 
# to ensure that if one is provided, the other exists and they point back to each other,
# and that they aren't the same UUID.
    model_config = {
        "extra": "forbid" # Prevent unexpected fields in the YAML
    }


# --- Component Definitions ---

class ComponentDefinition(BaseModel):
    """Base model for all component definitions."""
    id: str = Field(..., description="Unique identifier for this component instance (e.g., temp_driver_fruiting).")
    # 'type' field will be defined in subclasses using Literal for discrimination
    config_file: str = Field(..., description="Path to the component's specific YAML configuration file (relative to project root or a known config dir).")
    # Default MQTT client ID is None, consuming code should derive from 'id' if None ("auto" behavior)
    mqtt_client_id: Optional[str] = Field(None, description="Optional MQTT client ID. If None, defaults to component 'id'. Must be unique.")

    model_config = {
        "extra": "forbid"
    }
    # Note: Pydantic v2 automatically uses the 'type' field defined with Literal in subclasses
    # for discrimination when used in a Union. No explicit discriminator needed here usually.

class MicrocontrollerComponentDefinition(ComponentDefinition):
    """Definition for a microcontroller interface component."""
    type: Literal[ComponentType.MICROCONTROLLER] = ComponentType.MICROCONTROLLER
    points_provided: List[str] = Field(..., description="List of point UUIDs that this microcontroller directly provides.")

class DriverComponentDefinition(ComponentDefinition):
    """Definition for a driver component."""
    type: Literal[ComponentType.DRIVER] = ComponentType.DRIVER
    controls_microcontroller: str = Field(..., description="The 'id' of the microcontroller component this driver controls.")
    # Points synthesized or managed by the driver (e.g., PWM output state)
    virtual_points_provided: List[str] = Field([], description="List of point UUIDs synthesized or managed by this driver.")

class GovernorComponentDefinition(ComponentDefinition):
    """Definition for a governor component."""
    type: Literal[ComponentType.GOVERNOR] = ComponentType.GOVERNOR
    controls_drivers: List[str] = Field(..., description="List of driver component 'id's that this governor controls.")

# --- Main System Definition ---

# Type alias for the union of all possible component types
AnyComponent = Union[
    MicrocontrollerComponentDefinition, 
    DriverComponentDefinition, 
    GovernorComponentDefinition
    # Add other component types here as they are defined
]

class SystemDefinition(BaseModel):
    """Root model for the entire system definition YAML."""
    mqtt_broker: MQTTBrokerConfig = Field(..., description="MQTT broker connection details.")
    command_hierarchy: List[str] = Field(..., description="List defining command authority levels (e.g., Manual_HOA, Watchdog, Governor).")
    points: List[PointDefinition] = Field(..., description="Master list of all logical points in the system.")
    components: List[AnyComponent] = Field(..., description="List of all running component instances.")

    model_config = {
        "extra": "forbid"
    }