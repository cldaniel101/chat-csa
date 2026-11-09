#!/usr/bin/env python3
"""Valida o preview publicado sem registrar ou exibir credenciais.

As verificações públicas cobrem saúde, frontend, CORS e bloqueio das rotas
administrativas. Quando o usuário e ``CHAT_CSA_SMOKE_ADMIN_PASSWORD`` estão
presentes, o script também valida login, TTL e reutilização da sessão em um
novo cliente HTTP, equivalente a recarregar o painel.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass

import httpx

PASSWORD_ENV = "CHAT_CSA_SMOKE_ADMIN_PASSWORD"


class ValidationError(RuntimeError):
    """Falha de uma verificação do ambiente publicado."""


@dataclass(frozen=True)
class PreviewConfig:
    api_url: str
    web_url: str
    origin: str
    expected_ttl: int
    admin_username: str


def _status(response: httpx.Response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise ValidationError(f"{label}: esperado HTTP {expected}, recebido HTTP {response.status_code}.")


def validate_public(client: httpx.Client, config: PreviewConfig) -> list[str]:
    """Executa verificações que não dependem de credenciais."""
    results: list[str] = []

    health = client.get(f"{config.api_url}/health")
    _status(health, 200, "Healthcheck da API")
    try:
        health_data = health.json()
    except ValueError as exc:
        raise ValidationError("Healthcheck da API não devolveu JSON válido.") from exc
    if health_data.get("status") != "ok":
        raise ValidationError("Healthcheck da API não informou status ok.")
    results.append("API saudável")

    frontend = client.get(config.web_url)
    _status(frontend, 200, "Frontend")
    if "text/html" not in frontend.headers.get("content-type", ""):
        raise ValidationError("Frontend não devolveu HTML.")
    results.append("frontend acessível")

    protected = client.get(f"{config.api_url}/kb/list")
    _status(protected, 401, "Acesso administrativo sem token")
    results.append("rota administrativa bloqueada sem token")

    invalid_login = client.post(
        f"{config.api_url}/auth/login",
        json={
            "username": f"preview-audit-{uuid.uuid4().hex[:12]}",
            "password": "invalid-preview-audit-password",
        },
    )
    _status(invalid_login, 401, "Login inválido")
    results.append("login inválido rejeitado")

    cors_headers = {
        "Origin": config.origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    preflight = client.options(f"{config.api_url}/auth/login", headers=cors_headers)
    _status(preflight, 200, "Preflight CORS")
    if preflight.headers.get("access-control-allow-origin") != config.origin:
        raise ValidationError("CORS não autorizou a origem esperada do frontend.")

    rejected_origin = "https://origem-invalida.example"
    rejected = client.options(
        f"{config.api_url}/auth/login",
        headers={**cors_headers, "Origin": rejected_origin},
    )
    if rejected.headers.get("access-control-allow-origin") == rejected_origin:
        raise ValidationError("CORS autorizou uma origem externa não esperada.")
    results.append("CORS restrito à origem configurada")

    return results


def validate_authenticated(client: httpx.Client, config: PreviewConfig, password: str) -> list[str]:
    """Valida login e sessão sem imprimir senha ou token."""
    login = client.post(
        f"{config.api_url}/auth/login",
        json={"username": config.admin_username, "password": password},
    )
    _status(login, 200, "Login administrativo")
    try:
        payload = login.json()
    except ValueError as exc:
        raise ValidationError("Login administrativo não devolveu JSON válido.") from exc

    token = str(payload.get("access_token") or "")
    if not token:
        raise ValidationError("Login administrativo não devolveu token de sessão.")
    if payload.get("expires_in") != config.expected_ttl:
        raise ValidationError(
            "TTL da sessão diverge do esperado: "
            f"esperado {config.expected_ttl}s, recebido {payload.get('expires_in')!r}."
        )

    headers = {"Authorization": f"Bearer {token}"}
    current = client.get(f"{config.api_url}/auth/me", headers=headers)
    _status(current, 200, "Sessão autenticada")

    # Um novo cliente não compartilha cookies ou estado em memória e simula a
    # recarga completa do painel reutilizando apenas o token assinado.
    with httpx.Client(timeout=30, follow_redirects=True) as reloaded_client:
        reloaded = reloaded_client.get(f"{config.api_url}/auth/me", headers=headers)
    _status(reloaded, 200, "Sessão após recarga")

    return [
        "login administrativo válido",
        f"TTL de sessão confirmado em {config.expected_ttl}s",
        "sessão reutilizada após recarga",
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valida o preview publicado do Chat CSA.")
    parser.add_argument(
        "--api-url",
        default="https://chat-csa-api-development.vercel.app",
    )
    parser.add_argument(
        "--web-url",
        default="https://chat-csa-web-development.vercel.app",
    )
    parser.add_argument(
        "--origin",
        default="https://chat-csa-web-development.vercel.app",
    )
    parser.add_argument("--expected-ttl", type=int, default=28800)
    parser.add_argument("--admin-username", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = PreviewConfig(
        api_url=args.api_url.rstrip("/"),
        web_url=args.web_url.rstrip("/"),
        origin=args.origin.rstrip("/"),
        expected_ttl=args.expected_ttl,
        admin_username=args.admin_username.strip(),
    )

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            results = validate_public(client, config)
            if config.admin_username:
                password = os.getenv(PASSWORD_ENV, "")
                if not password:
                    raise ValidationError(
                        f"Defina {PASSWORD_ENV} somente no ambiente local para validar o login real."
                    )
                results.extend(validate_authenticated(client, config, password))
    except (httpx.HTTPError, ValidationError) as exc:
        print(f"[falha] {exc}", file=sys.stderr)
        return 1

    for result in results:
        print(f"[ok] {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
