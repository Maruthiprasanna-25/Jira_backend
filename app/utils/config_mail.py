import os
from fastapi_mail import ConnectionConfig
from dotenv import load_dotenv
load_dotenv()

conf = ConnectionConfig(
    MAIL_USERNAME=os.environ["MAIL_USERNAME"],
    MAIL_PASSWORD=os.environ["MAIL_PASSWORD"],
    MAIL_FROM=os.environ["MAIL_FROM"],
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",

    # New field names (FastAPI-Mail >= 2.x)
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,

    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)
