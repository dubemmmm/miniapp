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
    Send a transactional email via Resend.

    Sends from DEFAULT_FROM_EMAIL (a verified sender on the Resend-verified
    offplan.cwlagos.com domain) with Reply-To set to DEFAULT_REPLY_TO_EMAIL,
    so replies land in a real monitored inbox even though the technical
    sender has to stay on the authenticated domain.

    Returns:
        (success: bool, provider_message_id: str | None, error: str | None)

    Never raises — returns the error string instead so callers can handle it.
    """
    api_key = settings.RESEND_API_KEY
    from_email = settings.DEFAULT_FROM_EMAIL
    reply_to = settings.DEFAULT_REPLY_TO_EMAIL

    if not api_key:
        return False, None, 'RESEND_API_KEY is not configured'

    try:
        import resend
        from resend.exceptions import ResendError

        resend.api_key = api_key

        params = {
            'from': from_email,
            'to': [recipient_email],
            'subject': subject,
            'text': body_text,
        }
        if reply_to:
            params['reply_to'] = reply_to
        if body_html:
            params['html'] = body_html

        response = resend.Emails.send(params)
        return True, response.get('id'), None

    except ResendError as exc:
        return False, None, exc.message
    except Exception as exc:
        return False, None, str(exc)
