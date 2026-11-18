import os
import re
import secrets
import smtplib
import socket
import ssl
import time
import logging
from typing import List, Optional
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from dotenv import load_dotenv
from flask import render_template, url_for
from flask_mail import Message

load_dotenv()

# Configure logging
log = logging.getLogger(__name__)
# Set log level from environment variable or default to WARNING
log_level = os.getenv('LOGGING', 'WARNING').upper()
if log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
    log_level = 'WARNING'
log.setLevel(getattr(logging, log_level, logging.WARNING))

# Email configuration
class Config:
    # Email server configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 465))  # Default to port 465 with SSL
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'false').lower() in ['true', '1', 't']
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'true').lower() in ['true', '1', 't']
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@familytree.com')
    MAIL_TIMEOUT = 30  # 30 seconds timeout
    MAIL_DEBUG = True  # Enable debug output
    MAIL_ASCII_ATTACHMENTS = False  # Handle non-ASCII attachments properly
    MAIL_SUPPRESS_SEND = False  # Actually send emails
    
    # Application configuration
    APP_NAME = os.getenv('APP_NAME', 'FamilyTreesPE')
    OPS_URL = os.getenv('OPS_URL', 'http://localhost:5566')

class EmailPublisher:
    """
    Email Publisher class to handle the creation and 
    sending of email messages with support for both 
    plain text and HTML formats.
    """
    def __init__(self, email_sender: str, email_password: str):
        """
        Initialize the EmailPublisher with the sender's email and password.
        
        Args:
            email_sender (str): The sender's email address.
            email_password (str): The sender's email password.
        """
        self.email_sender = email_sender
        self.email_password = email_password
        
    def _create_email(self, 
        subject: str, 
        text: str, 
        html: str, 
        recipients: List[str],
        attached_file: Optional[str] = None
    ) -> MIMEMultipart:
        """
        Create an email message with both plain text 
        and HTML formats
        
        Args:
            subject (str): The subject of the email.
            text (str): The plain text content of the email.
            html (str): The HTML content of the email.
            recipients (List[str]): List of recipient email addresses.
            
        Returns:
            MIMEMultipart: The created email message object.
        """
        # Create the root message
        msg = MIMEMultipart('mixed')
        msg['From'] = self.email_sender
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject
        msg.preamble = 'This is a multi-part message in MIME format.'

        # Create the alternative part for text and HTML
        msg_alternative = MIMEMultipart('alternative')
        
        # Add text part
        part1 = MIMEText(text, 'plain')
        msg_alternative.attach(part1)
        
        # Add HTML part
        part2 = MIMEText(html, 'html')
        msg_alternative.attach(part2)
        
        # Attach the alternative part to the root message
        msg.attach(msg_alternative)
        
        # Add attached file if provided
        if attached_file and os.path.exists(attached_file):
            log.debug(f"Attached file: {attached_file}")
            try:
                with open(attached_file, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    # Use only the base name of the file in the attachment
                    filename = os.path.basename(attached_file)
                    part.add_header("Content-Disposition", 
                                 f"attachment; filename=\"{filename}\"")
                    msg.attach(part)
            except Exception as e:
                log.error(f"Error attaching file: {str(e)}")
        
        return msg

    def publish_email(self, subject: str, text: str, html: str,
                      recipients: List[str] = [],
                      attached_file: Optional[str] = None):
        """
        Send email to multiple recipients
        
        Args:
            subject (str): The subject of the email.
            text (str): The plain text content of the email.
            html (str): The HTML content of the email.
            recipients (List[str]): List of recipient email addresses.
            
        Returns:
            bool: True if the email was sent successfully, False otherwise.
        """
        try:
            # Create email message object
            msg = self._create_email(subject, text, html, 
                            recipients, attached_file)
            
            # Create secure SSL connection
            context = ssl.create_default_context()
            context.load_default_certs()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            
            # Send email
            with smtplib.SMTP_SSL(Config.MAIL_SERVER, Config.MAIL_PORT, context=context) as smtp:
                try:
                    smtp.login(self.email_sender, self.email_password)
                    smtp.sendmail(self.email_sender, 
                        recipients, 
                        msg.as_string())
                    return True
                except smtplib.SMTPAuthenticationError as e:
                    log.error(f'publish_email(): Login failed: {str(e)}')
                    return False
                except Exception as e:
                    log.error(f'publish_email(): Error sending email: {str(e)}')
                    return False
        except Exception as e:
            log.error(f'publish_email(): General error: {str(e)}')
            return False

def validate_email(email):
    """
    Check if email is legitimate.
    
    Args:
        email (str): The email address to validate.
        
    Returns:
        bool: True if the email is legitimate, False otherwise.
    """
    pattern = r"^[a-zA-Z0-9-_.]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-z]{2,}$"

    if re.match(pattern, email):
        return True
    return False

def generate_verification_token():
    """
    Generate a secure random token for email verification
    
    Returns:
        str: A secure random token
    """
    return secrets.token_urlsafe(32)


# Used when a catalog file cannot be read. Kept in both languages so the
# instruction mail stays bilingual even if localization files are missing.
_MEMBERSHIP_COPY_FALLBACK = {
    "繁中": {
        "subject": "請先向家族管理員登記後再訂閱",
        "heading": "訂閱前請先完成家族登記",
        "intro": "您以這個電子郵件地址申請訂閱本家族通訊。",
        "action": "此地址尚未登記為本家族成員。請先聯絡對應的家族管理員，提供您的電子郵件地址與個人資料完成登記，之後才能訂閱。",
        "admin_label": "家族管理員：",
        "admin_unknown": "請向您的家族管理員登記。伺服器尚未設定管理員信箱。",
        "ignore": "若您並未提出此申請，請忽略這封信。",
        "closing": "祝安好",
    },
    "US": {
        "subject": "Register with your family Admin before subscribing",
        "heading": "Register before you subscribe",
        "intro": "You asked to subscribe to this family journal with the email address below.",
        "action": "This address is not registered as a member of this family. Contact the family Admin and register your email address together with your personal information before subscribing.",
        "admin_label": "Family Admin:",
        "admin_unknown": "Please register with your family Admin. This server has no admin email configured.",
        "ignore": "If you did not ask to subscribe, you can ignore this email.",
        "closing": "Best regards",
    },
}
_MEMBERSHIP_COPY_KEYS = {
    "subject": "SUB_NONMEMBER_SUBJECT",
    "heading": "SUB_NONMEMBER_HEADING",
    "intro": "SUB_NONMEMBER_INTRO",
    "action": "SUB_NONMEMBER_ACTION",
    "admin_label": "SUB_NONMEMBER_ADMIN",
    "admin_unknown": "SUB_NONMEMBER_ADMIN_UNKNOWN",
    "ignore": "SUB_NONMEMBER_IGNORE",
    "closing": "SUB_NONMEMBER_CLOSING",
}


def _membership_copy():
    """Traditional Chinese and English strings for the non-member email."""
    catalogs = {}
    try:
        from funcUtils import load_ops_L10N
        catalogs = load_ops_L10N() or {}
    except Exception as exc:
        log.error("Could not load localization for the membership email: %s", exc)

    localized = {}
    for lang, fallbacks in _MEMBERSHIP_COPY_FALLBACK.items():
        catalog = catalogs.get(lang) or {}
        localized[lang] = {}
        for field, key in _MEMBERSHIP_COPY_KEYS.items():
            value = catalog.get(key)
            if isinstance(value, str) and value.strip():
                localized[lang][field] = value
            else:
                localized[lang][field] = fallbacks[field]
    subject = f"{localized['繁中']['subject']} / {localized['US']['subject']}"
    return subject, localized["繁中"], localized["US"]


def send_membership_instruction_email(mail, email, admin_email=None):
    """Tell a non-member to register with the family Admin. The body is bilingual."""
    admin_email = (admin_email or "").strip()
    try:
        subject, zh, en = _membership_copy()
        html = render_template(
            "email/register_first.html",
            email=email,
            admin_email=admin_email,
            app_name=Config.APP_NAME,
            zh=zh,
            en=en,
        )
        msg = Message(
            subject=subject,
            recipients=[email],
            html=html,
            sender=Config.MAIL_DEFAULT_SENDER,
        )
        return _send_mail(mail, msg)
    except Exception as exc:
        log.error("Failed to prepare membership instruction email: %s", exc, exc_info=True)
        return False


def send_verification_email(mail, email, token, is_subscribe=True):
    """Send the subscribe or unsubscribe confirmation mail."""
    action = "subscribe" if is_subscribe else "unsubscribe"
    subject = f"Please confirm that you want to {action} to {Config.APP_NAME}"
    try:
        verification_url = url_for(
            "verify_email",
            email=email,
            token=token,
            action=action,
            _external=True,
            _scheme="https" if "https" in Config.OPS_URL else "http",
        )
    except Exception as exc:
        log.error("Failed to generate verification URL: %s", exc)
        return False
    try:
        html = render_template(
            "email/verification.html",
            action=action,
            verification_url=verification_url,
            app_name=Config.APP_NAME,
            email=email,
        )
        msg = Message(
            subject=subject,
            recipients=[email],
            html=html,
            sender=Config.MAIL_DEFAULT_SENDER,
        )
        return _send_mail(mail, msg)
    except Exception as exc:
        log.error("Failed to prepare verification email: %s", exc, exc_info=True)
        return False


def send_email(mail, emails, subject, html):
    """Send one HTML message through Flask-Mail."""
    try:
        msg = Message(
            subject=subject,
            recipients=emails,
            html=html,
            sender=Config.MAIL_DEFAULT_SENDER,
        )
        return _send_mail(mail, msg)
    except Exception as exc:
        log.error("Failed to prepare email: %s", exc, exc_info=True)
        return False


def send_newsletter(mail, emails, blob):
    """Render the newsletter template and send it."""
    try:
        html = render_template(
            "email/newsletter.html",
            header=blob.get("header", ""),
            t1=blob.get("t1", ""),
            t1_articles=blob.get("t1_articles", []),
            t2=blob.get("t2", ""),
            t2_title=blob.get("t2_title", ""),
            t2_content=blob.get("t2_content", ""),
            t2_image=blob.get("t2_image", ""),
            t2_image_alt=blob.get("t2_image_alt", ""),
            t2_author=blob.get("t2_author", ""),
            t2_source=blob.get("t2_source", ""),
            t2_src_url=blob.get("t2_src_url", ""),
            t3=blob.get("t3", ""),
            t3_articles=blob.get("t3_articles", []),
            ft_url=blob.get("ft_url", ""),
            ops_svr=blob.get("ops_svr", ""),
            motto_btn=blob.get("motto_btn", ""),
            motto=blob.get("motto", ""),
            t4_greeting=blob.get("t4_greeting", ""),
            t4_team=blob.get("t4_team", ""),
            title=blob.get("title", "Newsletter"),
            author_label=blob.get("author_label", "Author:"),
            source_label=blob.get("source_label", "Source:"),
        )
        msg = Message(
            subject=blob.get("title", "Newsletter"),
            recipients=emails,
            html=html,
            sender=Config.MAIL_DEFAULT_SENDER,
        )
        return _send_mail(mail, msg)
    except Exception as exc:
        log.error("Failed to prepare newsletter: %s", exc, exc_info=True)
        return False


def _send_mail(mail, msg, max_retries=3):
    """Send via Flask-Mail, retrying network failures."""
    for attempt in range(max_retries):
        try:
            with mail.connect() as conn:
                conn.send(msg)
                return True
        except smtplib.SMTPAuthenticationError as exc:
            log.error("SMTP authentication error: %s", exc)
            return False
        except (smtplib.SMTPException, socket.timeout, socket.gaierror, OSError) as exc:
            log.error("Email send attempt %s failed: %s", attempt + 1, exc)
            if attempt == max_retries - 1:
                return False
            time.sleep((2 ** attempt) * 2)
        except Exception as exc:
            log.error("Unexpected email error: %s", exc, exc_info=True)
            if attempt == max_retries - 1:
                return False
            time.sleep((2 ** attempt) * 2)
    return False

if __name__ == "__main__":
    # Initialize EmailPublisher
    publisher = EmailPublisher(Config.MAIL_USERNAME, 
                             Config.MAIL_PASSWORD
                             )
    
    # Set email subject and recipients
    subject = 'Test Email'
    recipients = ["mkaoy2k@me.com"]
    text = "This is a test email"
    html = r"""
    <style>
        .publish-message {
            font-size: 24px;
            font-weight: bold;
            color: #1f77b4;
        }
    </style>
    <div class="publish-message">
    <p>Your article has been approved and published:</p>
    </div>
    """
    # Send email
    if publisher.publish_email(subject, text, html, recipients):
        log.info("Email sent successfully")
    else:
        log.error("Failed to send email")
    