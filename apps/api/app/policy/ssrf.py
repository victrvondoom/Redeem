"""SSRF guard for any server-side fetch or browser navigation. Fails closed."""
import ipaddress
import socket
from urllib.parse import urlparse

from ..config import settings


class UnsafeURL(Exception):
    pass


def _check_ip(ip: str) -> None:
    a = ipaddress.ip_address(ip)
    if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified:
        raise UnsafeURL(f"blocked address {ip}")


def validate_url(url: str, resolver=socket.getaddrinfo) -> str:
    u = urlparse(url)
    if u.scheme not in ("https",):
        raise UnsafeURL("only https URLs are allowed")
    if not u.hostname or u.username or u.password:
        raise UnsafeURL("host missing or credentials in URL")
    host = u.hostname
    try:
        _check_ip(host)  # literal IPs (incl. decimal/IPv6 forms normalised by ipaddress)
        return url
    except ValueError:
        pass
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        raise UnsafeURL("internal hostname")
    try:
        infos = resolver(host, None)
    except OSError as e:
        raise UnsafeURL("hostname does not resolve") from e
    for info in infos:
        _check_ip(info[4][0])  # every resolved address must be public (blocks DNS-to-internal)
    return url


def browser_execution_allowed() -> tuple[bool, str]:
    """Cloud browser automation requires an isolated runtime. A Playwright context in the API process is not isolation."""
    if settings.isolated_browser_runtime_url:
        return True, "isolated runtime configured"
    return False, "BLOCKED: no isolated browser runtime configured (REDEEM_ISOLATED_BROWSER_URL). Shared-process browsing is refused."
