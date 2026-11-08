#!/usr/bin/env python3
"""Envia o aviso de revisão a partir do resumo do scrape."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

try:
    from chat_csa.update_notification import (
        UpdateNotificationError,
        load_scrape_summary,
        send_update_notification,
    )
except ImportError:  # pragma: no cover - conveniência para execução local
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from chat_csa.update_notification import (
        UpdateNotificationError,
        load_scrape_summary,
        send_update_notification,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envia aviso sobre mudanças no portal CSA.")
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--panel-url", required=True)
    parser.add_argument("--run-url", default="")
    args = parser.parse_args(argv)

    # Localmente lê o .env; no GitHub Actions as mesmas chaves entram como
    # secrets no ambiente do step.
    load_dotenv()
    try:
        summary = load_scrape_summary(args.summary_json)
        sent = send_update_notification(
            summary,
            panel_url=args.panel_url,
            run_url=args.run_url,
        )
    except UpdateNotificationError as exc:
        print(f"[erro] {exc}", file=sys.stderr)
        return 1

    if sent:
        print("[ok] Aviso de revisão enviado.")
    else:
        print("[=] Nenhuma mudança; aviso não enviado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
