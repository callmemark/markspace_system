# utils.py
from django.core.mail import send_mail
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.conf import settings

signer = TimestampSigner()

def generate_verification_token(account):
    return signer.sign(str(account.id))

def verify_token(token, max_age=86400):  # 24 hours
    try:
        account_id = signer.unsign(token, max_age=max_age)
        return account_id
    except (BadSignature, SignatureExpired):
        return None

def send_verification_email(account):
    token = generate_verification_token(account)
    verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"  # frontend handles finalization
    send_mail(
        'Verify your email address',
        f'Click the link to verify your account: {verification_url}',
        settings.DEFAULT_FROM_EMAIL,
        [account.email],
        fail_silently=False,
    )