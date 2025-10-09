from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

import paho.mqtt.client as mqtt
import yaml


INFRA_DEF_PATH = (
	Path(__file__).resolve().parents[2] / "config_sources" / "infrastructure_definition.yaml"
)
INFRA_SECRETS_PATH = Path(__file__).resolve().parents[2] / "secrets" / "infrastructure_secrets.yaml"


@dataclass(frozen=True)
class BrokerConfig:
	address: str
	port: int
	username: str
	password: str


def _load_broker_config() -> BrokerConfig:
	with INFRA_DEF_PATH.open("r", encoding="utf-8") as f:
		infra_def: Mapping[str, Any] = yaml.safe_load(f)
	with INFRA_SECRETS_PATH.open("r", encoding="utf-8") as f:
		secrets: Mapping[str, Any] = yaml.safe_load(f)
	mb = infra_def.get("mqtt_broker", {})
	address = str(secrets.get("MQTT_BROKER_ADDRESS"))
	port = int(secrets.get("MQTT_BROKER_PORT"))
	username = str(secrets.get("MQTT_USERNAME"))
	password = str(secrets.get("MQTT_PASSWORD"))
	# Allow structure in infra_def to exist without values; values come from secrets
	return BrokerConfig(address=address, port=port, username=username, password=password)


def publish_json(topic: str, payload: Mapping[str, Any], *, role: str, qos: int = 0, retain: bool = False) -> None:
	config = _load_broker_config()
	client_id = f"CLI-{role}"
	client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
	client.username_pw_set(config.username, config.password)
	client.connect(config.address, config.port, keepalive=30)
	msg = json.dumps(payload, separators=(",", ":"))
	client.publish(topic, msg, qos=qos, retain=retain)
	client.disconnect()


