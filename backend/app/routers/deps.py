import hashlib
import hmac
import ipaddress
import logging
from typing import Callable, Iterable

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.redis_client import rate_limit_check
from app.core.config import settings
from app.core.database import get_db
from app.repositories import api_key as api_key_repo
from app.repositories import tenant as tenant_repo
from app.schemas.deps import TenantContext

logger = logging.getLogger(__name__)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


async def get_current_tenant(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    hash_key = hashlib.sha256(x_api_key.encode()).hexdigest()
    api_key = await api_key_repo.get_by_hash(db, hash_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    gemini_api_key: str | None = None
    tenant = await tenant_repo.get_by_id(db, api_key.id_tenant)
    if tenant and tenant.gemini_api_key_encrypted:
        from app.core.crypto import decrypt
        gemini_api_key = decrypt(tenant.gemini_api_key_encrypted)

    return TenantContext(
        tenant_id=api_key.id_tenant,
        api_key_id=api_key.id,
        gemini_api_key=gemini_api_key,
    )


def _parse_ip(value: str) -> IPAddress:
    ip = ipaddress.ip_address(value.strip())
    # Treat IPv4-mapped IPv6 (::ffff:10.0.0.1) as the underlying IPv4 address.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _parse_networks(entries: Iterable[str]) -> list[IPNetwork]:
    """Parse IPs/CIDRs into networks. Raises ValueError on any invalid entry."""
    networks: list[IPNetwork] = []
    for entry in entries:
        net = ipaddress.ip_network(entry.strip(), strict=False)
        if isinstance(net, ipaddress.IPv6Network) and net.network_address.ipv4_mapped is not None:
            # ::ffff:a.b.c.d/N -> a.b.c.d/(N-96)
            net = ipaddress.ip_network(
                f"{net.network_address.ipv4_mapped}/{max(net.prefixlen - 96, 0)}", strict=False
            )
        networks.append(net)
    return networks


def _in_networks(ip: IPAddress, networks: list[IPNetwork]) -> bool:
    return any(ip.version == net.version and ip in net for net in networks)


def resolve_client_ip(
    peer: str | None,
    forwarded_for: list[str],
    trusted_proxies: list[IPNetwork],
) -> IPAddress | None:
    """Return the effective client IP, or None if it cannot be determined safely.

    - The socket peer is authoritative. X-Forwarded-For is only consulted when the
      peer itself is a trusted proxy.
    - When it is, the chain ``XFF entries + [peer]`` is walked right-to-left and the
      first address that is NOT a trusted proxy is returned (the right-most untrusted
      hop). Left-most entries are client-controlled and never trusted on their own.
    - Any malformed address yields None (fail closed).
    """
    if not peer:
        return None
    try:
        peer_ip = _parse_ip(peer)
    except ValueError:
        return None

    if not trusted_proxies or not _in_networks(peer_ip, trusted_proxies):
        return peer_ip

    hops = [h.strip() for header in forwarded_for for h in header.split(",") if h.strip()]
    client = peer_ip
    for hop in reversed(hops):
        try:
            hop_ip = _parse_ip(hop)
        except ValueError:
            return None
        client = hop_ip
        if not _in_networks(hop_ip, trusted_proxies):
            return hop_ip
    # Every hop is a trusted proxy: the left-most one is the best we have.
    return client


async def require_admin(
    request: Request,
    x_service_key: str = Header(...),
) -> None:
    expected = settings.SERVICE_API_KEY
    if not expected or not hmac.compare_digest(
        x_service_key.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service key")

    forbidden = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not allowed")
    try:
        allowed = _parse_networks(settings.ADMIN_ALLOWED_IPS)
        trusted = _parse_networks(settings.TRUSTED_PROXIES)
    except ValueError:
        logger.error("Invalid ADMIN_ALLOWED_IPS / TRUSTED_PROXIES entry; denying admin access")
        raise forbidden

    if not allowed:
        raise forbidden

    client_ip = resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.getlist("x-forwarded-for"),
        trusted,
    )
    if client_ip is None or not _in_networks(client_ip, allowed):
        raise forbidden


def get_checkpointer(request: Request):
    return request.app.state.checkpointer.saver


def _rate_limiter(endpoint_tag: str, limit: int, window: int) -> Callable:
    async def dependency(
        request: Request,
        response: Response,
        tenant: TenantContext = Depends(get_current_tenant),
    ) -> None:
        key = f"ratelimit:{tenant.tenant_id}:{endpoint_tag}"
        allowed, headers = await rate_limit_check(key, limit, window)
        for k, v in headers.items():
            response.headers[k] = v
        if not allowed:
            response.headers["Retry-After"] = str(window)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={**headers, "Retry-After": str(window)},
            )

    return dependency


rate_limit_ingest = _rate_limiter(
    "ingest", settings.RATE_LIMIT_INGEST, settings.RATE_LIMIT_INGEST_WINDOW
)
rate_limit_query = _rate_limiter(
    "query", settings.RATE_LIMIT_QUERY, settings.RATE_LIMIT_QUERY_WINDOW
)
