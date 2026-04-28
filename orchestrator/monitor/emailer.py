"""Email delivery backends for workflow monitor notifications."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from .models import EmailConfig


@dataclass(frozen=True)
class SendResult:
    """Result of a monitor email delivery attempt."""

    sent: bool
    preview: str = ""


class SmtpEmailSender:
    """SMTP email sender for headless monitor notifications."""

    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def send(self, message: EmailMessage, *, dry_run: bool = False) -> SendResult:
        if dry_run:
            return SendResult(sent=False, preview=message.as_string())

        username = _read_env(self.config.username_env, "username")
        password = _read_env(self.config.password_env, "password")
        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as smtp:
            if self.config.use_starttls:
                smtp.starttls()
            if username is not None or password is not None:
                smtp.login(username or "", password or "")
            smtp.send_message(message)
        return SendResult(sent=True)


def _read_env(env_name: str | None, label: str) -> str | None:
    if env_name is None:
        return None
    value = os.environ.get(env_name)
    if value is None:
        raise ValueError(f"required SMTP credential for {label} is not set")
    return value
