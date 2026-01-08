import logging
from .config_mail import conf
from fastapi_mail import FastMail, MessageSchema, MessageType

logger = logging.getLogger(__name__)

async def send_reset_email(email_to: str, reset_link: str):
    """
    Sends a password reset email using FastAPI-Mail.
    
    Args:
        email_to: Recipient email address
        reset_link: The password reset URL
    """

    message = MessageSchema(
        subject="Reset Your Password",
        recipients=[email_to],
        body=f"""
        Click the link to reset your password:<br>
        <a href="{reset_link}">Reset Password</a>
        """,
        subtype=MessageType.html,
    )

    try:
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info("📧 EMAIL SENT SUCCESSFULLY")

    except Exception as e:
        logger.error(f"❌ EMAIL FAILED: {e}")
