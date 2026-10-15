#!/usr/bin/env python3
"""G1-T01 exact-domain CONNECT proxy; network access is NEVER direct.

Deployment is PARKED. A future reviewed activation runs the proxy on a
container connected to one internal client network + one egress network.
Runtime/Executor/direct only join their own internal networks. No plaintext
request bodies, tokens or headers are logged or terminated in the proxy.
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import sys
from typing import Callable

PORT = 3128
UPSTREAM_PORT = 443
READ_LIMIT = 8192
MAX_HEADERS = 24
MAX_SIMULTANEOUS = 8
CONNECT_TIMEOUT = 12
IDLE_TIMEOUT = 300
DOMAIN_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
# Precise hostnames, not suffix/wildcard matching.
ROLE_DOMAINS = {
    "provider": frozenset({"chatgpt.com", "auth.openai.com", "api.openai.com"}),
    "github": frozenset({"github.com", "api.github.com",
                          "codeload.github.com", "uploads.github.com"}),
}
RESPONSE_BAD = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
RESPONSE_GATEWAY = b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
RESPONSE_OK = b"HTTP/1.1 200 Connection Established\r\n\r\n"


class ProxyStop(ValueError):
    """Policy refusal with a fixed reason, never raw headers/tokens."""


def parse_authority(start: bytes, allowed: frozenset[str]) -> str:
    """Only CONNECT exact-public-host:443, no IP literals, other HTTP methods."""
    if len(start) > 1024 or not start.endswith(b"\r\n"):
        raise ProxyStop("invalid_request_line")
    try:
        method, target, version = start[:-2].decode("ascii").split(" ")
    except (UnicodeError, ValueError) as exc:
        raise ProxyStop("invalid_request_line") from exc
    if method != "CONNECT" or version != "HTTP/1.1":
        raise ProxyStop("connect_only")
    if target.count(":") != 1:
        raise ProxyStop("invalid_authority")
    raw_host, raw_port = target.split(":")
    if raw_port != str(UPSTREAM_PORT):
        raise ProxyStop("tls_port_only")
    host = raw_host.lower()
    if (
        host != raw_host or host not in allowed
        or DOMAIN_RE.fullmatch(host) is None
        or host.endswith(".local")
    ):
        raise ProxyStop("domain_not_allowlisted")
    return host


def safe_addresses(rows: list[tuple]) -> list[str]:
    """Reject the WHOLE DNS response if any address is not globally routable.

    This also prevents DNS rebinding via an accepted public answer plus an
    RFC1918 loopback/link-local side address. Connect to the verified IP
    instead of resolving the hostname a second time.
    """
    addresses: list[str] = []
    if not rows or len(rows) > 64:
        raise ProxyStop("dns_result_unavailable")
    for row in rows:
        if not isinstance(row, tuple) or len(row) < 5 or len(row[4]) < 1:
            raise ProxyStop("dns_result_invalid")
        try:
            address = ipaddress.ip_address(row[4][0])
        except (ValueError, TypeError) as exc:
            raise ProxyStop("dns_result_invalid") from exc
        # ipaddress.is_global is True for some multicast prefixes on
        # certain Python versions. Multicast/reserved/unspecified are never
        # acceptable remote HTTPS origins, even if is_global says True.
        if (not address.is_global or address.is_multicast
                or address.is_reserved or address.is_unspecified):
            raise ProxyStop("nonpublic_destination_denied")
        addresses.append(str(address))
    return list(dict.fromkeys(addresses))


async def resolve_public(host: str) -> str:
    loop = asyncio.get_running_loop()
    rows = await asyncio.wait_for(
        loop.getaddrinfo(host, UPSTREAM_PORT, family=socket.AF_INET,
                         type=socket.SOCK_STREAM),
        timeout=CONNECT_TIMEOUT,
    )
    return safe_addresses(rows)[0]


async def read_connect(reader: asyncio.StreamReader,
                       allowed: frozenset[str]) -> str:
    start = await asyncio.wait_for(reader.readline(), timeout=CONNECT_TIMEOUT)
    host = parse_authority(start, allowed)
    consumed = len(start)
    seen_host = False
    for _ in range(MAX_HEADERS):
        line = await asyncio.wait_for(reader.readline(), timeout=CONNECT_TIMEOUT)
        consumed += len(line)
        if consumed > READ_LIMIT or not line:
            raise ProxyStop("headers_too_large_or_truncated")
        if line == b"\r\n":
            if not seen_host:
                raise ProxyStop("host_header_missing")
            return host
        if b":" not in line or not line.endswith(b"\r\n"):
            raise ProxyStop("header_invalid")
        key, value = line[:-2].split(b":", 1)
        if key.lower() == b"host":
            if seen_host or value.strip().decode("ascii", "replace").lower() != (
                host + ":" + str(UPSTREAM_PORT)
            ):
                raise ProxyStop("host_header_mismatch")
            seen_host = True
        elif key.lower() in {b"proxy-authorization", b"authorization"}:
            # No proxy credentials needed; never accept an upstream bearer
            # on the proxy negotiation request itself.
            raise ProxyStop("credential_header_not_allowed")
    raise ProxyStop("too_many_headers")


def tls_client_hello_sni(record: bytes) -> str:
    """Reject SNI swapping on shared public IPs; pass TLS bytes unchanged.

    Only one bounded TLS ClientHello record is accepted. ECH/fragmented
    handshakes fail closed rather than opening an unverified tunnel.
    """
    if len(record) < 9 or record[0] != 22 or record[1] != 3:
        raise ProxyStop("tls_client_hello_required")
    length = int.from_bytes(record[3:5], "big")
    if not 4 <= length <= 16384 or length != len(record) - 5:
        raise ProxyStop("tls_record_size_invalid")
    body = memoryview(record)[5:]
    if body[0] != 1 or int.from_bytes(body[1:4], "big") != len(body) - 4:
        raise ProxyStop("tls_client_hello_invalid")
    pos = 4

    def read(n: int) -> bytes:
        nonlocal pos
        if n < 0 or pos + n > len(body):
            raise ProxyStop("tls_client_hello_truncated")
        data = bytes(body[pos:pos + n])
        pos += n
        return data

    read(2 + 32)  # legacy version and random
    read(int.from_bytes(read(1), "big"))   # session ID
    read(int.from_bytes(read(2), "big"))   # cipher suites
    read(int.from_bytes(read(1), "big"))   # compression methods
    ext_size = int.from_bytes(read(2), "big")
    ext_end = pos + ext_size
    if ext_end != len(body):
        raise ProxyStop("tls_extensions_invalid")
    names = []
    while pos < ext_end:
        ext_kind = int.from_bytes(read(2), "big")
        ext_data = read(int.from_bytes(read(2), "big"))
        if ext_kind != 0:
            continue
        if len(ext_data) < 5 or int.from_bytes(ext_data[:2], "big") != len(ext_data) - 2:
            raise ProxyStop("tls_sni_extension_invalid")
        # Only one DNS SNI hostname, no IP, unknown name types or padding.
        index = 2
        while index < len(ext_data):
            if index + 3 > len(ext_data):
                raise ProxyStop("tls_sni_extension_invalid")
            kind = ext_data[index]
            size = int.from_bytes(ext_data[index + 1:index + 3], "big")
            index += 3
            if kind != 0 or size == 0 or index + size > len(ext_data):
                raise ProxyStop("tls_sni_extension_invalid")
            try:
                names.append(ext_data[index:index + size].decode("ascii"))
            except UnicodeDecodeError as exc:
                raise ProxyStop("tls_sni_not_ascii") from exc
            index += size
    if pos != ext_end or len(names) != 1:
        raise ProxyStop("tls_sni_missing_or_multiple")
    return names[0]


async def forward(reader: asyncio.StreamReader,
                  writer: asyncio.StreamWriter) -> None:
    while True:
        buf = await asyncio.wait_for(reader.read(65536), timeout=IDLE_TIMEOUT)
        if not buf:
            return
        writer.write(buf)
        await asyncio.wait_for(writer.drain(), timeout=IDLE_TIMEOUT)


async def tunnel(client_reader: asyncio.StreamReader,
                 client_writer: asyncio.StreamWriter,
                 allowed: frozenset[str]) -> None:
    upstream_writer: asyncio.StreamWriter | None = None
    connected = False
    try:
        hostname = await read_connect(client_reader, allowed)
        destination = await resolve_public(hostname)
        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(destination, UPSTREAM_PORT),
            timeout=CONNECT_TIMEOUT,
        )
        client_writer.write(RESPONSE_OK)
        await client_writer.drain()
        connected = True
        # Read and verify the TLS ClientHello SNI before forwarding any
        # application bytes. HTTP CONNECT host alone is not a true domain
        # allowlist on multi-tenant CDN IPs.
        header = await asyncio.wait_for(client_reader.readexactly(5),
                                        timeout=CONNECT_TIMEOUT)
        record_length = int.from_bytes(header[3:5], "big")
        if not 4 <= record_length <= 16384:
            raise ProxyStop("tls_record_size_invalid")
        hello = header + await asyncio.wait_for(
            client_reader.readexactly(record_length), timeout=CONNECT_TIMEOUT,
        )
        if tls_client_hello_sni(hello) != hostname:
            raise ProxyStop("tls_sni_does_not_match_connect")
        upstream_writer.write(hello)
        await upstream_writer.drain()
        a = asyncio.create_task(forward(client_reader, upstream_writer))
        b = asyncio.create_task(forward(upstream_reader, client_writer))
        done, pending = await asyncio.wait({a, b}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            try:
                task.result()
            except (OSError, ConnectionError, asyncio.TimeoutError):
                pass
    except (ProxyStop, OSError, ConnectionError, asyncio.TimeoutError,
            UnicodeError, ValueError, asyncio.IncompleteReadError):
        if not connected:
            client_writer.write(RESPONSE_BAD if upstream_writer is None
                                else RESPONSE_GATEWAY)
            try:
                await client_writer.drain()
            except (OSError, ConnectionError):
                pass
    finally:
        if upstream_writer is not None:
            upstream_writer.close()
            try:
                await upstream_writer.wait_closed()
            except (OSError, ConnectionError):
                pass
        client_writer.close()
        try:
            await client_writer.wait_closed()
        except (OSError, ConnectionError):
            pass


async def serve(role: str) -> None:
    if role not in ROLE_DOMAINS:
        raise ProxyStop("unknown_or_unconfigured_egress_role")
    pool = asyncio.Semaphore(MAX_SIMULTANEOUS)

    async def bounded(reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter) -> None:
        async with pool:
            await tunnel(reader, writer, ROLE_DOMAINS[role])

    server = await asyncio.start_server(
        bounded, host="0.0.0.0", port=PORT, limit=READ_LIMIT,
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    # Do not print credentials, request lines or addresses to standard logs.
    try:
        asyncio.run(serve(os.getenv("G1_EGRESS_ROLE", "")))
    except ProxyStop:
        print("STOP_G1_EGRESS_PROXY_SCOPE", file=sys.stderr)
        raise SystemExit(2)
