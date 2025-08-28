from typing import Dict
from pydantic import BaseModel, Field


class WiFiSecrets(BaseModel):
    ssid: str = Field(..., description="WiFi network SSID (secret)")
    password: str = Field(..., description="WiFi network password (secret)")
    model_config = {"extra": "forbid"}


class MQTTSecrets(BaseModel):
    broker_address: str = Field(..., description="MQTT broker address (secret)")
    broker_port: int = Field(1883, description="MQTT broker port (secret)")
    username: str = Field(..., description="MQTT username (secret)")
    password: str = Field(..., description="MQTT password (secret)")
    model_config = {"extra": "forbid"}


class WiFiSecretsGroup(BaseModel):
    default: WiFiSecrets = Field(..., description="Default WiFi secrets applied to all devices unless overridden")
    per_device: Dict[str, WiFiSecrets] = Field(
        default_factory=dict,
        description="Optional per-device WiFi overrides keyed by device_id",
    )
    model_config = {"extra": "forbid"}


class MQTTSecretsGroup(BaseModel):
    default: MQTTSecrets = Field(..., description="Default MQTT secrets applied to all devices unless overridden")
    per_device: Dict[str, MQTTSecrets] = Field(
        default_factory=dict,
        description="Optional per-device MQTT overrides keyed by device_id",
    )
    model_config = {"extra": "forbid"}


class InfrastructureSecrets(BaseModel):
    wifi: WiFiSecretsGroup = Field(..., description="WiFi secrets grouping (default + per-device)")
    mqtt: MQTTSecretsGroup = Field(..., description="MQTT secrets grouping (default + per-device)")
    model_config = {"extra": "forbid"}

    def get_wifi_for_device(self, device_id: str) -> WiFiSecrets:
        return self.wifi.per_device.get(device_id, self.wifi.default)

    def get_mqtt_for_device(self, device_id: str) -> MQTTSecrets:
        return self.mqtt.per_device.get(device_id, self.mqtt.default)


