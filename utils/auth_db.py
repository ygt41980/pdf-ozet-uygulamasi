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
    c = sb()
    bugun = date.today().isoformat()
    r = (c.table("usage").select("count")
         .eq("user_id", user_id).eq("day", bugun).execute())
    n = r.data[0]["count"] if r.data else 0
    if n >= GUNLUK_LIMIT:
        return False
    c.table("usage").upsert(
        {"user_id": user_id, "day": bugun, "count": n + 1},
        on_conflict="user_id,day",
    ).execute()
    return True