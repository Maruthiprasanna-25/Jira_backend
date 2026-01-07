from .config_mail import conf
from fastapi_mail import FastMail, MessageSchema, MessageType

async def send_reset_email(email_to: str, reset_link: str):

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
        print("📧 EMAIL SENT SUCCESSFULLY")

    except Exception as e:
        print("❌ EMAIL FAILED:", e)
