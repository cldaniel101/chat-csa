#!/usr/bin/env python3
"""Sonda diagnóstica de conectividade e fingerprinting HTTP contra o portal CSA/UEFS.

Testa:
1. Resolução DNS e tempo de abertura TCP (porta 443).
2. Resposta HTTP com diferentes assinaturas de User-Agent e cabeçalhos.
3. Diagnóstico de bloqueio por IP/GeoIP versus bloqueio por WAF/Camada 7.
"""

from __future__ import annotations

import json
import socket
import sys
import time

import httpx

TARGET_URL = "https://csa.uefs.br/index.php/sisu261/inicial"
TARGET_HOST = "csa.uefs.br"
TARGET_PORT = 443

USER_AGENTS = {
    "empty": "",
    "curl_default": "curl/8.5.0",
    "python_httpx_default": None,  # Padrão httpx
    "chat_csa_bot": "chat-csa-ingester/1.0 (projeto de extensao UEFS; leitura apenas)",
    "chrome_real_browser": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def test_tcp_handshake(host: str, port: int, timeout: float = 5.0) -> dict:
    """Mede a resolução DNS e a latência de abertura de conexão TCP pura."""
    t0 = time.perf_counter()
    try:
        ip = socket.gethostbyname(host)
        dns_time = time.perf_counter() - t0
    except Exception as exc:
        return {"ok": False, "step": "dns", "error": str(exc)}

    t1 = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
        tcp_time = time.perf_counter() - t1
        sock.close()
        return {
            "ok": True,
            "ip": ip,
            "dns_latency_ms": round(dns_time * 1000, 2),
            "tcp_connect_ms": round(tcp_time * 1000, 2),
        }
    except Exception as exc:
        sock.close()
        return {
            "ok": False,
            "ip": ip,
            "dns_latency_ms": round(dns_time * 1000, 2),
            "step": "tcp_connect",
            "error": str(exc),
        }


def test_http_fingerprint(url: str, ua_name: str, ua_string: str | None) -> dict:
    """Executa requisição GET com a assinatura de headers especificada."""
    headers = {}
    if ua_string is not None:
        headers["User-Agent"] = ua_string
    if ua_name == "chrome_real_browser":
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })

    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=8.0, verify=True, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            server_header = resp.headers.get("server", "desconhecido")
            return {
                "ok": resp.status_code == 200,
                "status_code": resp.status_code,
                "latency_ms": elapsed_ms,
                "server": server_header,
                "content_length": len(resp.content),
                "has_waf_banner": "Web Application Firewall" in resp.text or resp.status_code == 403,
            }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": elapsed_ms,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main():
    print(f"=== Diagnóstico de Egress e Fingerprint: {TARGET_HOST} ===")
    tcp_res = test_tcp_handshake(TARGET_HOST, TARGET_PORT)
    print("TCP / DNS:", json.dumps(tcp_res, indent=2))

    http_results = {}
    for name, ua in USER_AGENTS.items():
        print(f"Testando UA: {name} ...")
        http_results[name] = test_http_fingerprint(TARGET_URL, name, ua)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": TARGET_URL,
        "tcp_probe": tcp_res,
        "http_probes": http_results,
    }
    print("\n=== Resumo dos Resultados ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
