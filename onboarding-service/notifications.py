"""
Notification helpers — email (Resend) and Slack webhook.
All functions are fire-and-forget: log errors, never raise.
"""

import logging
import os

import httpx
import resend

logger = logging.getLogger("onboarding-service.notifications")

# ── Config ────────────────────────────────────────────────────────────────────
resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "onboarding@resend.dev")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
CALENDLY_URL = os.getenv("CALENDLY_URL", "https://calendly.com")


# ── Slack ─────────────────────────────────────────────────────────────────────

def send_slack_notification(name: str, email: str, url: str, request_id: str):
    """Post a new-request alert to the configured Slack channel."""
    if not SLACK_WEBHOOK_URL:
        logger.info("SLACK_WEBHOOK_URL not set — skipping Slack notification")
        return
    try:
        httpx.post(
            SLACK_WEBHOOK_URL,
            json={
                "text": (
                    f":new: *New demo request*\n"
                    f"*Name:* {name}\n"
                    f"*Email:* {email}\n"
                    f"*URL:* {url}\n"
                    f"*ID:* `{request_id}`"
                )
            },
            timeout=5,
        )
        logger.info(f"Slack notification sent for request {request_id}")
    except Exception as e:
        logger.warning(f"Slack notification failed: {e}")


# ── Client acknowledgment email ──────────────────────────────────────────────

def send_client_ack_email(name: str, email: str, url: str):
    """Send the 'we received your request' email to the client."""
    if not resend.api_key:
        logger.warning("RESEND_API_KEY not set — skipping client ack email")
        return
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": email,
            "subject": "We received your request",
            "html": f"""
<div style="font-family:'Space Grotesk',system-ui,sans-serif;max-width:560px;margin:0 auto;padding:40px 32px;background:#020617;color:#e2e8f0;border-radius:16px">
  <p style="font-size:13px;color:#6366f1;font-weight:600;letter-spacing:0.05em;margin-bottom:24px">HYPERFLEX</p>

  <h1 style="font-size:22px;font-weight:700;margin-bottom:12px;color:#f8fafc">We're building your demo, {name}.</h1>

  <p style="color:#94a3b8;line-height:1.7;margin-bottom:8px">
    We're reviewing <strong style="color:#e2e8f0">{url}</strong> and putting together a custom voice AI agent for your store.
  </p>
  <p style="color:#94a3b8;line-height:1.7">
    Expect a private test link in your inbox within <strong style="color:#e2e8f0">1–2 hours</strong>.
  </p>

  <div style="border-top:1px solid #1e293b;margin:32px 0"></div>

  <p style="color:#94a3b8;margin-bottom:16px">Want to chat while you wait? Book a free 20-min call.</p>

  <a href="{CALENDLY_URL}"
     style="display:inline-block;padding:14px 28px;background:#6366f1;color:white;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px">
    Book a Call
  </a>

  <p style="margin-top:48px;font-size:12px;color:#475569">— Hyperflex</p>
</div>"""
        })
        logger.info(f"Client ack email sent to {email}")
    except Exception as e:
        logger.error(f"Client ack email failed: {e}")


# ── Admin notification email ─────────────────────────────────────────────────

def send_admin_notification_email(name: str, email: str, url: str, request_id: str):
    """Notify the admin about a new request."""
    if not resend.api_key or not ADMIN_EMAIL:
        logger.warning("RESEND_API_KEY or ADMIN_EMAIL not set — skipping admin email")
        return
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": ADMIN_EMAIL,
            "subject": f"New demo request — {name}",
            "html": f"""
<div style="font-family:'Space Grotesk',system-ui,sans-serif;padding:32px;max-width:480px">
  <h2 style="margin-bottom:20px;font-size:18px">New Request</h2>
  <table style="border-collapse:collapse;width:100%">
    <tr><td style="padding:8px 12px;font-weight:600;color:#64748b;width:80px">Name</td><td style="padding:8px 12px">{name}</td></tr>
    <tr><td style="padding:8px 12px;font-weight:600;color:#64748b">Email</td><td style="padding:8px 12px">{email}</td></tr>
    <tr><td style="padding:8px 12px;font-weight:600;color:#64748b">URL</td><td style="padding:8px 12px">{url}</td></tr>
    <tr><td style="padding:8px 12px;font-weight:600;color:#64748b">ID</td><td style="padding:8px 12px;font-size:12px;color:#94a3b8">{request_id}</td></tr>
  </table>
</div>"""
        })
        logger.info(f"Admin notification sent for request {request_id}")
    except Exception as e:
        logger.error(f"Admin notification email failed: {e}")


# ── Delivery email (agent ready) ─────────────────────────────────────────────

def send_delivery_email(name: str, email: str, test_url: str, calendly_booked: bool = False):
    """Send the 'your agent is ready' email to the client."""
    if not resend.api_key:
        logger.warning("RESEND_API_KEY not set — skipping delivery email")
        return

    calendly_block = ""
    if not calendly_booked:
        calendly_block = f"""
  <div style="border-top:1px solid #1e293b;margin:32px 0"></div>
  <h2 style="font-size:16px;font-weight:600;margin-bottom:8px;color:#f8fafc">Want this on your real store?</h2>
  <p style="color:#94a3b8;line-height:1.7;margin-bottom:16px">We handle the entire setup. Book a free 20-min call.</p>
  <a href="{CALENDLY_URL}"
     style="display:inline-block;padding:14px 28px;background:#1e293b;border:1px solid #334155;color:#e2e8f0;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px">
    Book a Call
  </a>"""

    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": email,
            "subject": "Your voice AI demo is ready",
            "html": f"""
<div style="font-family:'Space Grotesk',system-ui,sans-serif;max-width:560px;margin:0 auto;padding:40px 32px;background:#020617;color:#e2e8f0;border-radius:16px">
  <p style="font-size:13px;color:#6366f1;font-weight:600;letter-spacing:0.05em;margin-bottom:24px">HYPERFLEX</p>

  <h1 style="font-size:22px;font-weight:700;margin-bottom:12px;color:#f8fafc">Your demo is ready, {name}.</h1>

  <p style="color:#94a3b8;line-height:1.7">
    Your custom voice AI agent is live. Tap the orb, ask it about products, and watch it work.
  </p>

  <a href="{test_url}"
     style="display:inline-block;margin:28px 0;padding:18px 36px;background:#6366f1;color:white;border-radius:12px;text-decoration:none;font-weight:700;font-size:16px">
    Try Your Demo
  </a>
  {calendly_block}
  <p style="margin-top:48px;font-size:12px;color:#475569">— Hyperflex</p>
</div>"""
        })
        logger.info(f"Delivery email sent to {email}")
    except Exception as e:
        logger.error(f"Delivery email failed: {e}")
