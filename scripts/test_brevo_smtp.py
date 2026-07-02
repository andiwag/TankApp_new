#!/usr/bin/env python3
"""Test Brevo SMTP credentials outside Northflank.

Uses the same env var names as Tankly (see .env.beta.example).

Loads MAIL_* from the project .env file automatically.

Example (PowerShell):
  $env:TEST_MAIL_TO = "you@gmail.com"
  python scripts/test_brevo_smtp.py

Optional overrides:
  MAIL_SERVER (default: smtp-relay.brevo.com)
  MAIL_PORT   (default: 587)
"""

from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    mail_server = os.environ.get("MAIL_SERVER", "smtp-relay.brevo.com").strip()
    mail_port = int(os.environ.get("MAIL_PORT", "587"))
    mail_username = _require("MAIL_USERNAME")
    mail_password = _require("MAIL_PASSWORD")
    mail_from = _require("MAIL_FROM")
    mail_to = _require("TEST_MAIL_TO")

    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = mail_to
    message["Subject"] = "Tankly SMTP test"
    message.set_content(
        "If you receive this, Brevo SMTP login and sender are working.\n"
    )

    print(f"Connecting to {mail_server}:{mail_port} ...")
    try:
        with smtplib.SMTP(mail_server, mail_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            print("Logging in ...")
            smtp.login(mail_username, mail_password)
            print("Sending test message ...")
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        print("SMTP authentication failed.", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        print(
            "\nCheck MAIL_USERNAME (Brevo SMTP login) and MAIL_PASSWORD (SMTP key, not API key).",
            file=sys.stderr,
        )
        sys.exit(1)
    except smtplib.SMTPException as exc:
        print("SMTP error.", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        print(
            "\nIf login worked, verify MAIL_FROM in Brevo (Senders & IP → Senders).",
            file=sys.stderr,
        )
        sys.exit(1)

    print("OK")
    print(f"Sent from {mail_from} to {mail_to}")
    print("Check your inbox and Brevo transactional logs.")


if __name__ == "__main__":
    main()
