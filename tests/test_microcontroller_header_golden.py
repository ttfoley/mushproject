from pathlib import Path

from mushbuild.validation.ssot import SSOTValidator
from mushbuild.validation.components import ComponentConfigValidator
from mushbuild.generators.microcontrollers import MicrocontrollerConfigGenerator
from shared_libs.config_models.secrets import InfrastructureSecrets

import yaml
import pytest


def _load_infrastructure_with_secrets(config_base_dir: Path):
    infra_path = config_base_dir / "infrastructure_definition.yaml"
    infrastructure = {}
    if infra_path.exists():
        with open(infra_path) as f:
            infrastructure = yaml.safe_load(f) or {}

    project_root = config_base_dir.parent
    secrets_path = project_root / "secrets" / "infrastructure_secrets.yaml"
    with open(secrets_path) as f:
        secrets_raw = yaml.safe_load(f) or {}

    if isinstance(secrets_raw, dict) and (
        'WIFI_SSID' in secrets_raw or 'MQTT_BROKER_ADDRESS' in secrets_raw
    ):
        secrets_converted = {
            'wifi': {
                'default': {
                    'ssid': secrets_raw.get('WIFI_SSID', ''),
                    'password': secrets_raw.get('WIFI_PASSWORD', ''),
                },
                'per_device': {}
            },
            'mqtt': {
                'default': {
                    'broker_address': secrets_raw.get('MQTT_BROKER_ADDRESS', ''),
                    'broker_port': secrets_raw.get('MQTT_BROKER_PORT', 1883),
                    'username': secrets_raw.get('MQTT_USERNAME', ''),
                    'password': secrets_raw.get('MQTT_PASSWORD', ''),
                },
                'per_device': {}
            }
        }
    else:
        secrets_converted = secrets_raw

    secrets_model = InfrastructureSecrets.model_validate(secrets_converted)
    return infrastructure, secrets_model


@pytest.mark.parametrize("micro_id", ["c1", "c2", "c3"])
def test_micro_header_matches_artifact(tmp_path: Path, micro_id: str):
    project_root = Path(__file__).parent.parent
    config_base_dir = project_root / "config_sources"

    infra, secrets_model = _load_infrastructure_with_secrets(config_base_dir)

    ssot_file = config_base_dir / "system_definition.yaml"
    ssot = SSOTValidator(ssot_file).validate()
    assert ssot is not None

    points_by_uuid_map = {p.uuid: p for p in ssot.points}
    ok, validated = ComponentConfigValidator(ssot, config_base_dir, infra, secrets_model).validate(points_by_uuid_map)
    assert ok
    assert micro_id in validated

    out_dir = tmp_path / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = MicrocontrollerConfigGenerator(ssot, out_dir)
    assert gen.generate(validated, only=micro_id)

    generated = (out_dir / f"autogen_config_{micro_id}.refactor.h").read_bytes()
    artifact = (project_root / "artifacts" / "microcontrollers" / "2025-10-01" / f"autogen_config_{micro_id}.h").read_bytes()

    assert generated == artifact


