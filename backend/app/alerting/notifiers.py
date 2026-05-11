import json
import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from app.config import settings
from app.security import is_url_allowed

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self):
        self.webhook_url = settings.SLACK_WEBHOOK_URL

    async def send(self, event: dict) -> bool:
        if not self.webhook_url:
            return False
        severity_colors = {"critical": "#ff0000", "warning": "#ffaa00", "info": "#36a64f"}
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*[{event.get('severity', 'warning').upper()}]* {event.get('rule_name', 'Alert')}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Status:* {event.get('status', 'firing')}"},
                    {"type": "mrkdwn", "text": f"*Value:* {event.get('value', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Threshold:* {event.get('threshold', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Message:* {event.get('message', '')}"},
                ],
            },
        ]
        try:
            if not is_url_allowed(self.webhook_url):
                logger.warning("Slack webhook URL blocked by SSRF protection")
                return False
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self.webhook_url,
                    json={"attachments": [{"color": severity_colors.get(event.get("severity", "warning"), "#ffaa00"), "blocks": blocks}]},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error("Slack notification failed: %s", e)
            return False


class EmailNotifier:
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_addr = settings.ALERT_EMAIL_FROM
        self.to_addrs = settings.ALERT_EMAIL_TO

    async def send(self, event: dict) -> bool:
        if not self.host or not self.to_addrs:
            return False
        try:
            msg = MIMEText(
                f"Alert: {event.get('rule_name')}\n"
                f"Status: {event.get('status')}\n"
                f"Severity: {event.get('severity')}\n"
                f"Value: {event.get('value')}\n"
                f"Threshold: {event.get('threshold')}\n"
                f"Message: {event.get('message')}\n"
            )
            msg["Subject"] = f"[DevOps Monitor] {event.get('severity', 'warning').upper()}: {event.get('rule_name')}"
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(self.to_addrs)

            with smtplib.SMTP(self.host, self.port) as server:
                if self.user:
                    server.starttls()
                    server.login(self.user, self.password)
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            return True
        except Exception as e:
            logger.error("Email notification failed: %s", e)
            return False


class WebhookNotifier:
    def __init__(self):
        self.url = settings.ALERT_WEBHOOK_URL

    async def send(self, event: dict) -> bool:
        if not self.url:
            return False
        try:
            if not is_url_allowed(self.url):
                logger.warning("Alert webhook URL blocked by SSRF protection")
                return False
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self.url, json=event)
                return resp.status_code < 400
        except Exception as e:
            logger.error("Webhook notification failed: %s", e)
            return False
