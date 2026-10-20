"""Test suite for Render Blueprint deployment configuration (render.yaml)."""

from pathlib import Path
import yaml
import pytest


@pytest.fixture
def render_config():
    """Load and parse render.yaml from the project root."""
    config_path = Path("render.yaml")
    assert config_path.exists(), "render.yaml must exist at the project root."
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def test_render_yaml_valid_syntax(render_config):
    """Verify render.yaml parses successfully as valid YAML."""
    assert isinstance(render_config, dict), "render.yaml must parse into a YAML mapping."
    assert "services" in render_config, "render.yaml must contain a top-level 'services' key."
    assert isinstance(render_config["services"], list)
    assert len(render_config["services"]) >= 1


def test_render_web_service_definition(render_config):
    """Verify web service configuration matches Render specifications."""
    web_services = [s for s in render_config["services"] if s.get("type") == "web"]
    assert len(web_services) == 1, "Expected exactly one web service definition."

    service = web_services[0]
    assert service.get("name") == "slothform"
    assert service.get("runtime") == "python"
    assert service.get("env") == "python"
    assert "pip install -r requirements.txt" in service.get("buildCommand", "")
    assert "uvicorn app.main:app" in service.get("startCommand", "")
    assert service.get("healthCheckPath") == "/health"


def test_render_environment_variables_security(render_config):
    """Verify secure handling of environment variables and secrets."""
    service = render_config["services"][0]
    env_vars = service.get("envVars", [])
    assert len(env_vars) > 0, "Service must declare required environment variables."

    var_dict = {item["key"]: item for item in env_vars}

    # Verify python version
    assert "PYTHON_VERSION" in var_dict
    assert var_dict["PYTHON_VERSION"].get("value") == "3.11.9"

    # Verify generated secrets
    for gen_key in ["SECRET_KEY", "AUTH0_TOKEN_VAULT_KEY"]:
        assert gen_key in var_dict, f"Expected {gen_key} in envVars"
        assert var_dict[gen_key].get("generateValue") is True, f"{gen_key} must have generateValue: true"

    # Verify synced API keys are not hardcoded
    sensitive_keys = [
        "BROWSERBASE_API_KEY",
        "BROWSERBASE_PROJECT_ID",
        "PAPER_INSTRUMENTS_API_KEY",
        "AUTH0_DOMAIN",
        "AUTH0_CLIENT_ID",
        "AUTH0_CLIENT_SECRET",
    ]
    for key in sensitive_keys:
        assert key in var_dict, f"Expected {key} in envVars"
        assert var_dict[key].get("sync") is False, f"{key} must have sync: false to prevent secret leakage"
        assert "value" not in var_dict[key], f"{key} must not hardcode raw secret values in blueprint"
