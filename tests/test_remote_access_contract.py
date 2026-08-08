"""Regression checks for the production same-origin gateway contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_publishes_only_the_caddy_port_on_the_tailnet_interface():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert '${TAILSCALE_IP:?' in compose
    assert '${MIROFISH_PORT:-3410}:3000' in compose
    assert '5001:5001' not in compose
    assert 'restart: unless-stopped' in compose
    assert './backend/uploads:/app/backend/uploads' in compose


def test_gateway_requires_environment_auth_and_proxies_api_to_private_backend():
    caddyfile = (ROOT / "Caddyfile").read_text()
    entrypoint = (ROOT / "docker/entrypoint.sh").read_text()

    assert '{env.MIROFISH_BASIC_AUTH_USER} {env.MIROFISH_BASIC_AUTH_HASH}' in caddyfile
    assert 'path /api/*' in caddyfile
    assert 'reverse_proxy 127.0.0.1:5001' in caddyfile
    assert 'MIROFISH_BASIC_AUTH_USER:?' in entrypoint
    assert 'MIROFISH_BASIC_AUTH_HASH:?' in entrypoint
    assert '--bind 127.0.0.1:5001' in entrypoint


def test_browser_api_defaults_to_the_current_origin_not_remote_localhost():
    api_client = (ROOT / "frontend/src/api/index.js").read_text()

    assert "baseURL: import.meta.env.VITE_API_BASE_URL || ''" in api_client
    assert 'localhost:5001' not in api_client
