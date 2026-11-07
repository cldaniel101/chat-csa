"""Gera, de forma interativa, o hash da senha do painel administrativo."""

from __future__ import annotations

import getpass

from chat_csa.server.auth import hash_password


def main() -> None:
    password = getpass.getpass("Nova senha administrativa: ")
    confirmation = getpass.getpass("Confirme a senha: ")
    if password != confirmation:
        raise SystemExit("As senhas não coincidem.")
    try:
        print(hash_password(password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
