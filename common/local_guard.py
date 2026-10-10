"""Loopback request guard shared by SpriteMotion's local web servers (standard library only).

A request is local when its Host header is 127.0.0.1:<port> or localhost:<port> (blocks DNS rebinding) and its
Origin header, when present, names the same host. A state-changing request can also be required to carry an Origin.
"""
from __future__ import annotations


def allowed_hosts(port: int) -> set[str]:
    return {f'127.0.0.1:{port}', f'localhost:{port}'}


def is_local(headers, port: int, require_origin: bool = False) -> bool:
    hosts = allowed_hosts(port)
    if headers.get('Host') not in hosts:
        return False
    origin = headers.get('Origin')
    if not origin:
        return not require_origin
    return origin in {'http://' + h for h in hosts}
