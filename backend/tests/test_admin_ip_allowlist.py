"""Admin IP allowlist: socket peer vs. X-Forwarded-For handling."""
import ipaddress

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.routers.deps import _parse_networks, require_admin, resolve_client_ip

SERVICE_KEY = "test-service-key"

_app = FastAPI()


@_app.get("/admin/ping", dependencies=[Depends(require_admin)])
async def _ping() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture(autouse=True)
def _admin_settings(monkeypatch):
    monkeypatch.setattr(settings, "SERVICE_API_KEY", SERVICE_KEY)
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS", ["203.0.113.10"])
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", [])


async def _get(peer: str, xff: str | None = None, key: str = SERVICE_KEY) -> int:
    headers = {"X-Service-Key": key}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    transport = ASGITransport(app=_app, client=(peer, 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/admin/ping", headers=headers)
    return resp.status_code


# ---------------------------------------------------------------------------
# End-to-end through require_admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_peer_in_allowlist_is_accepted():
    assert await _get("203.0.113.10") == 200


@pytest.mark.asyncio
async def test_spoofed_xff_from_untrusted_peer_is_rejected():
    # Attacker connects directly and claims to be the allowlisted IP.
    assert await _get("198.51.100.7", xff="203.0.113.10") == 403


@pytest.mark.asyncio
async def test_xff_ignored_when_no_trusted_proxies():
    # Even a private/local peer does not get its XFF honored unless configured.
    assert await _get("127.0.0.1", xff="203.0.113.10") == 403


@pytest.mark.asyncio
async def test_xff_via_trusted_proxy_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.0/8"])
    assert await _get("10.0.0.2", xff="203.0.113.10") == 200


@pytest.mark.asyncio
async def test_trusted_proxy_uses_rightmost_untrusted_not_leftmost(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.0/8"])
    # Client forged the left-most entry; the proxy appended the real client IP.
    assert await _get("10.0.0.2", xff="203.0.113.10, 198.51.100.7") == 403
    # Real client allowlisted, left-most garbage is ignored.
    assert await _get("10.0.0.2", xff="198.51.100.7, 203.0.113.10") == 200


@pytest.mark.asyncio
async def test_cidr_allowlist_match(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS", ["203.0.113.0/24"])
    assert await _get("203.0.113.77") == 200
    assert await _get("203.0.114.1") == 403


@pytest.mark.asyncio
async def test_invalid_allowlist_entry_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS", ["203.0.113.10", "not-an-ip"])
    assert await _get("203.0.113.10") == 403


@pytest.mark.asyncio
async def test_invalid_trusted_proxy_entry_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.0/33"])
    assert await _get("203.0.113.10") == 403


@pytest.mark.asyncio
async def test_malformed_xff_via_trusted_proxy_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.0/8"])
    assert await _get("10.0.0.2", xff="203.0.113.10, garbage") == 403


@pytest.mark.asyncio
async def test_empty_allowlist_denies_everyone(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS", [])
    assert await _get("203.0.113.10") == 403


@pytest.mark.asyncio
async def test_wrong_service_key_checked_before_ip():
    assert await _get("203.0.113.10", key="wrong") == 401


# ---------------------------------------------------------------------------
# resolve_client_ip unit tests
# ---------------------------------------------------------------------------

_TRUSTED = _parse_networks(["10.0.0.0/8", "192.168.1.1"])


def _ip(s: str):
    return ipaddress.ip_address(s)


def test_resolve_ignores_xff_from_untrusted_peer():
    assert resolve_client_ip("198.51.100.7", ["1.1.1.1"], _TRUSTED) == _ip("198.51.100.7")


def test_resolve_skips_chain_of_trusted_proxies():
    # client -> 192.168.1.1 (proxy) -> 10.0.0.2 (proxy) -> app
    got = resolve_client_ip("10.0.0.2", ["6.6.6.6, 203.0.113.10, 192.168.1.1"], _TRUSTED)
    assert got == _ip("203.0.113.10")


def test_resolve_handles_multiple_xff_headers():
    got = resolve_client_ip("10.0.0.2", ["6.6.6.6", "203.0.113.10"], _TRUSTED)
    assert got == _ip("203.0.113.10")


def test_resolve_trusted_peer_without_xff_returns_peer():
    assert resolve_client_ip("10.0.0.2", [], _TRUSTED) == _ip("10.0.0.2")


def test_resolve_normalizes_ipv4_mapped_ipv6():
    assert resolve_client_ip("::ffff:203.0.113.10", [], []) == _ip("203.0.113.10")


def test_resolve_missing_peer_fails_closed():
    assert resolve_client_ip(None, ["203.0.113.10"], _TRUSTED) is None
