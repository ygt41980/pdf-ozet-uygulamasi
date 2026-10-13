import base64
import hashlib
import os
import secrets
from datetime import date

from supabase import create_client

GUNLUK_LIMIT = 10


def sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])


def pkce_uret():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def kota_kullan(user_id):
    """True: hak var ve düşüldü. False: günlük limit doldu."""
    r = sb().rpc("kota_kullan_atomik", {
        "p_user_id": user_id,
        "p_day": date.today().isoformat(),
        "p_limit": GUNLUK_LIMIT,
    }).execute()
    return bool(r.data) 