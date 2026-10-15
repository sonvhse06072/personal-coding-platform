"""Source-only G1 egress policy tests. No real Internet/Docker/model usage."""
from __future__ import annotations

import asyncio
import importlib.util
import ipaddress
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deploy/g1/egress_connect_proxy.py"
spec = importlib.util.spec_from_file_location("g1_egress_test", SOURCE)
assert spec is not None and spec.loader is not None
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


def hello(host: str) -> bytes:
    """One complete synthetic TLS ClientHello with one unencrypted SNI."""
    name = host.encode("ascii")
    names = b"\x00" + len(name).to_bytes(2, "big") + name
    sni = len(names).to_bytes(2, "big") + names
    sni_extension = b"\x00\x00" + len(sni).to_bytes(2, "big") + sni
    handshakes = (
        b"\x03\x03" + bytes(range(32)) +
        b"\x00" +  # empty legacy session ID
        b"\x00\x02\x13\x01" +  # TLS AES cipher suite
        b"\x01\x00" +  # compression methods
        len(sni_extension).to_bytes(2, "big") + sni_extension
    )
    packet = b"\x01" + len(handshakes).to_bytes(3, "big") + handshakes
    return b"\x16\x03\x01" + len(packet).to_bytes(2, "big") + packet


def test_exact_host_role_allowlist_and_sni_parser():
    assert proxy.ROLE_DOMAINS == {
        "provider": frozenset({
            "chatgpt.com", "auth.openai.com", "api.openai.com",
        }),
        "github": frozenset({
            "github.com", "api.github.com", "codeload.github.com",
            "uploads.github.com",
        }),
    }
    for role, hosts in proxy.ROLE_DOMAINS.items():
        for host in hosts:
            line = f"CONNECT {host}:443 HTTP/1.1\r\n".encode()
            assert proxy.parse_authority(line, hosts) == host
            assert proxy.tls_client_hello_sni(hello(host)) == host
    assert "api.github.com" not in proxy.ROLE_DOMAINS["provider"]


@pytest.mark.parametrize("line,reason", [
    (b"GET https://chatgpt.com/ HTTP/1.1\r\n", "connect_only"),
    (b"CONNECT chatgpt.com:80 HTTP/1.1\r\n", "tls_port_only"),
    (b"CONNECT chatgpt.com:8443 HTTP/1.1\r\n", "tls_port_only"),
    (b"CONNECT localhost:443 HTTP/1.1\r\n", "domain_not_allowlisted"),
    (b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n", "domain_not_allowlisted"),
    (b"CONNECT 169.254.169.254:443 HTTP/1.1\r\n", "domain_not_allowlisted"),
    (b"CONNECT github.com:443 HTTP/1.1\r\n", "domain_not_allowlisted"),
    (b"CONNECT chatgpt.com.evil.com:443 HTTP/1.1\r\n",
     "domain_not_allowlisted"),
    (b"CONNECT CHATGPT.COM:443 HTTP/1.1\r\n", "domain_not_allowlisted"),
    (b"CONNECT chatgpt.com.:443 HTTP/1.1\r\n", "domain_not_allowlisted"),
    (b"CONNECT user@chatgpt.com:443 HTTP/1.1\r\n", "domain_not_allowlisted"),
    (b"CONNECT [::1]:443 HTTP/1.1\r\n", "invalid_authority"),
    (b"CONNECT chatgpt.com:443 HTTP/1.0\r\n", "connect_only"),
    (b"CONNECT chatgpt.com:443 HTTP/1.1\n", "invalid_request_line"),
])
def test_denied_authorities_do_not_establish_a_tunnel(line, reason):
    with pytest.raises(proxy.ProxyStop, match=reason):
        proxy.parse_authority(line, proxy.ROLE_DOMAINS["provider"])


@pytest.mark.parametrize("addr", [
    "127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.12",
    "169.254.169.254", "0.0.0.0", "100.64.0.1", "224.0.0.1",
    "255.255.255.255", "::1", "fc00::1",
])
def test_dns_rejects_non_public_ranges(addr):
    entry = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (addr, 443))]
    with pytest.raises(proxy.ProxyStop, match="nonpublic_destination_denied"):
        proxy.safe_addresses(entry)


def test_dns_mixed_public_and_private_answers_refused():
    # Cannot tunnel to public CDN IP while accepting metadata/private fallback.
    rows = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443)),
    ]
    with pytest.raises(proxy.ProxyStop, match="nonpublic_destination_denied"):
        proxy.safe_addresses(rows)
    assert proxy.safe_addresses(rows[:1]) == ["1.1.1.1"]


@pytest.mark.parametrize("change,reason", [
    (lambda r: r[:-1], "tls_record_size_invalid"),
    (lambda r: bytes([23]) + r[1:], "tls_client_hello_required"),
    (lambda r: r[:5] + bytes([2]) + r[6:], "tls_client_hello_invalid"),
    (lambda r: r[:3] + b"\xff\xff" + r[5:], "tls_record_size_invalid"),
    (lambda r: r.replace(b"chatgpt.com", b"chatgpt.con"),
     "tls_sni_missing_or_multiple"),
])
def test_tls_handshake_refuses_malformed_or_different_server_names(
    change, reason,
):
    with pytest.raises(proxy.ProxyStop):
        proxy.tls_client_hello_sni(change(hello("chatgpt.com")))


def test_valid_but_wrong_sni_cannot_be_accepted_as_a_connect_host():
    assert proxy.tls_client_hello_sni(hello("api.openai.com")) != "chatgpt.com"
    assert proxy.tls_client_hello_sni(hello("api.github.com")) != "github.com"


def test_no_auth_or_proxy_auth_in_connect_handshake():
    def test(raw):
        async def once():
            r = asyncio.StreamReader()
            r.feed_data(raw)
            r.feed_eof()
            return await proxy.read_connect(r, proxy.ROLE_DOMAINS["provider"])
        return asyncio.run(once())

    assert test(
        b"CONNECT chatgpt.com:443 HTTP/1.1\r\n"
        b"Host: chatgpt.com:443\r\n\r\n"
    ) == "chatgpt.com"
    for bad in (
        b"Host: api.github.com:443\r\n",
        b"Host: chatgpt.com:443\r\nAuthorization: Bearer abc\r\n",
        b"Host: chatgpt.com:443\r\nProxy-Authorization: Basic foo\r\n",
        b"Host: chatgpt.com:443\r\nHost: chatgpt.com:443\r\n",
    ):
        with pytest.raises(proxy.ProxyStop):
            test(b"CONNECT chatgpt.com:443 HTTP/1.1\r\n" + bad + b"\r\n")


def test_proxy_has_no_public_http_forwarding_or_secrets():
    source = SOURCE.read_text(encoding="utf-8")
    assert "open_connection(destination, UPSTREAM_PORT)" in source
    assert "getaddrinfo(host, UPSTREAM_PORT" in source
    assert "record_length <= 16384" in source
    assert "tls_client_hello_sni(hello) != hostname" in source
    assert "GITHUB_DELIVERY_TOKEN" not in source
    assert "OPENAI_API_KEY" not in source
    assert "os.system(" not in source
    assert "subprocess." not in source
