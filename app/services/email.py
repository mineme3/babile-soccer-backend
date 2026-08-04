"""Email service for sending password reset and notification emails."""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    """Send a password reset email with the reset link."""
    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP not configured — skipping email send. Reset token: %s", reset_token)
        return False

    reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"

    subject = "Babile Sport — Password Reset Request"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0;padding:0;background-color:#121212;font-family:Arial,sans-serif;">
        <div style="max-width:480px;margin:40px auto;background-color:#1A1A1A;border-radius:16px;border:1px solid #2E2E2E;overflow:hidden;">
            <div style="background-color:#00A86B;padding:24px;text-align:center;">
                <h1 style="color:#ffffff;margin:0;font-size:20px;font-weight:800;">Babile Sport</h1>
            </div>
            <div style="padding:32px;">
                <h2 style="color:#ffffff;font-size:18px;margin:0 0 16px;">Password Reset Request</h2>
                <p style="color:#A0A0A0;font-size:14px;line-height:1.6;margin:0 0 24px;">
                    We received a request to reset your password. Click the button below to set a new password.
                </p>
                <a href="{reset_url}" style="display:inline-block;background-color:#00A86B;color:#ffffff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">
                    Reset Password
                </a>
                <p style="color:#808080;font-size:12px;line-height:1.6;margin:24px 0 0;">
                    This link expires in 1 hour. If you didn't request this, you can safely ignore this email.
                </p>
            </div>
            <div style="padding:16px 32px;border-top:1px solid #2E2E2E;text-align:center;">
                <p style="color:#808080;font-size:11px;margin:0;">&copy; 2026 Babile Sport. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("Password reset email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send password reset email to %s: %s", to_email, e)
        return False
