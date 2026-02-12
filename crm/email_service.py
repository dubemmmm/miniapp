"""
Provider-agnostic email sending layer.
Currently backed by SendGrid. Swap the implementation here without touching callers.
"""
import os
from pathlib import Path
from string import Template
from django.conf import settings

# Template directory relative to this file
TEMPLATE_DIR = Path(__file__).parent / 'email_templates'


def render_template(template_name: str, context: dict) -> str:
    """
    Load a .txt template from email_templates/ and substitute context vars.
    Uses Python's string.Template (${var} or $var syntax).
    """
    path = TEMPLATE_DIR / f'{template_name}.txt'
    with open(path, 'r') as f:
        content = f.read()
    # Use safe_substitute so missing keys don't raise errors
    return Template(content).safe_substitute(context)


def send_transactional_email(
    recipient_email: str,
    subject: str,
    body_text: str,
    body_html: str = None,
) -> tuple[bool, str | None, str | None]:
    """
    Send a transactional email via SendGrid.

    Returns:
        (success: bool, provider_message_id: str | None, error: str | None)

    Never raises — returns the error string instead so callers can handle it.
    """
    api_key = settings.SENDGRID_API_KEY
    from_email = settings.DEFAULT_FROM_EMAIL

    if not api_key:
        return False, None, 'SENDGRID_API_KEY is not configured'

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Content

        sg = sendgrid.SendGridAPIClient(api_key=api_key)

        mail = Mail(
            from_email=from_email,
            to_emails=recipient_email,
            subject=subject,
            plain_text_content=body_text,
        )
        if body_html:
            mail.add_content(Content('text/html', body_html))

        response = sg.send(mail)

        # SendGrid returns message ID in the X-Message-Id header
        message_id = response.headers.get('X-Message-Id', '')
        return True, message_id, None

    except Exception as exc:
        return False, None, str(exc)
