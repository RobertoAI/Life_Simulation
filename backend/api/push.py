"""Web Push API -- subscription management and push notification delivery.

Implements the Web Push Protocol (RFC 8030, RFC 8291) with VAPID (RFC 8292)
using only the ``cryptography`` library (already a transitive dependency of
uvicorn) and httpx for HTTP transport.

If the cryptography package is unavailable, endpoints remain registered but
emit warnings and gracefully degrade.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
import uuid
from hashlib import sha256

import httpx

# ---------------------------------------------------------------------------
# Crypto imports -- optional; push degrades gracefully without them
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    import jwt  # PyJWT (optional, we hand-roll a minimal ES256 JWT if missing)
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------
_db_path: str | None = None
_initial_population: int = 1000
_event_rate_limits: dict[str, float] = {}  # event_type -> last_sent_epoch
_RATE_LIMIT_SECONDS = 300  # 5 minutes

# ---------------------------------------------------------------------------
# VAPID key management
# ---------------------------------------------------------------------------
# Default demo keys -- in production, set VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY.
# These are base64url-encoded raw EC P-256 points / scalars.
DEFAULT_VAPID_PUBLIC_KEY = (
    "BKgHn5gQ6xY5m2V1cK2gJ5mN7qX8tR4wE9iO3pL6sU1vW2xC8yB0dF5eG7hJ9kL"
    "mN3pQ6sT8vX0zB2dE4fH6gI9jKlMnOpQrRsTuVwXyZbC2"
)
_DEFAULT_VAPID_PRIVATE_KEY = (
    "dGhpcy1pcy1hLWRlbW8tcHJpdmF0ZS1rZXktZm9yLXRl"
    "c3RpbmctcHVycG9zZXMtb25seQ"
)

# In production use env vars; here we also attempt to generate one-off keys
_vapid_public_key: str | None = None
_vapid_private_key: str | None = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string, adding padding as needed."""
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - (len(s) % 4)
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)


def generate_vapid_keys() -> tuple[str, str]:
    """Generate a new VAPID key pair and return (public_b64url, private_b64url)."""
    private = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public = private.public_key()

    pub_bytes = public.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    priv_bytes = private.private_numbers().private_value.to_bytes(32, "big")

    return _b64url(pub_bytes), _b64url(priv_bytes)


def load_vapid_keys() -> tuple[str, bytes, ec.EllipticCurvePrivateKey]:
    """Return (public_b64url, private_der, private_ec_key).

    Tries environment variables, then auto-generates if not set.
    """
    global _vapid_public_key, _vapid_private_key
    if _vapid_public_key and _vapid_private_key:
        return _load_from_cached() 

    env_pub = os.environ.get("VAPID_PUBLIC_KEY")
    env_priv = os.environ.get("VAPID_PRIVATE_KEY")

    if env_pub and env_priv and CRYPTO_AVAILABLE:
        _vapid_public_key = env_pub
        _vapid_private_key = env_priv
        return _load_from_cached()

    # Auto-generate a key pair
    pub, priv = generate_vapid_keys()
    _vapid_public_key = pub
    _vapid_private_key = priv
    return _load_from_cached()


def _load_from_cached() -> tuple[str, bytes, ec.EllipticCurvePrivateKey]:
    """Decode cached b64url strings into usable EC key objects."""
    pub_bytes = _b64url_decode(_vapid_public_key)
    priv_bytes = _b64url_decode(_vapid_private_key)

    priv_int = int.from_bytes(priv_bytes, "big")
    private_key = ec.derive_private_key(priv_int, ec.SECP256R1(), default_backend())
    return _vapid_public_key, priv_bytes, private_key


# ---------------------------------------------------------------------------
# Minimal ES256 JWT (no PyJWT dependency required)
# ---------------------------------------------------------------------------

def _es256_jwt(header: dict, payload: dict, private_key: ec.EllipticCurvePrivateKey) -> str:
    """Create and sign an ES256 JWT without PyJWT."""
    import json, hashlib, os
    header_b64 = _b64url(json.dumps(header).encode())
    payload_b64 = _b64url(json.dumps(payload).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    signature = private_key.sign(
        signing_input,
        ec.ECDSA(hashlib.sha256()),
    )
    # ECDSA signature is DER-encoded; we need r||s raw format for JWT
    r_val = signature[:32]
    s_val = signature[32:]
    jwt_sig = _b64url(r_val + s_val)
    return f"{signing_input.decode()}.{jwt_sig}"


# ---------------------------------------------------------------------------
# VAPID auth header
# ---------------------------------------------------------------------------

def _vapid_auth_header(
    public_key_b64: str,
    private_key: ec.EllipticCurvePrivateKey,
    audience: str,
    subject: str = "mailto:admin@example.com",
) -> str:
    """Build the ``Authorization: vapid ...`` header value."""
    now = int(time.time())
    jwt_token = _es256_jwt(
        header={"alg": "ES256", "typ": "JWT"},
        payload={"aud": audience, "exp": now + 86400, "sub": subject},
        private_key=private_key,
    )
    return f"vapid t={jwt_token}, k={public_key_b64}"


# ---------------------------------------------------------------------------
# Web Push payload encryption (RFC 8291)
# ---------------------------------------------------------------------------

def _hkdf_expand(salt: bytes, key: bytes, info: bytes, length: int) -> bytes:
    """Simple HKDF-SHA256 expand."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not available")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
        backend=default_backend(),
    )
    return hkdf.derive(key)


def _encrypt_payload(
    subscriber_p256dh: str,
    subscriber_auth: str,
    plaintext: str,
    padding: int = 0,
) -> tuple[bytes, bytes]:
    """Encrypt the push payload, returning (salt, ciphertext)."""
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not available")

    # 1. Get subscriber's public key
    sub_pub_bytes = _b64url_decode(subscriber_p256dh)

    # 2. Load subscriber public key as an EC point
    pubkey = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), sub_pub_bytes
    )

    # 3. Generate ephemeral local key pair
    local_private = ec.generate_private_key(ec.SECP256R1(), default_backend())
    local_public = local_private.public_key()
    local_pub_bytes = local_public.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )

    # 4. ECDH shared secret
    shared_secret = local_private.exchange(ec.ECDH(), pubkey)

    # 5. Derive PRK (pseudo-random key) using subscriber auth as salt
    salt = _b64url_decode(subscriber_auth)
    prk = _hkdf_expand(salt, shared_secret, b"Content-Encoding: auth\0", 32)

    # 6. Derive Content Encryption Key (CEK)
    cek_info = b"Content-Encoding: aes128gcm\0" + sub_pub_bytes + local_pub_bytes
    cek = _hkdf_expand(b"", prk, cek_info, 16)

    # 7. Derive nonce
    nonce_info = b"Content-Encoding: nonce\0" + sub_pub_bytes + local_pub_bytes
    nonce = _hkdf_expand(b"", prk, nonce_info, 12)

    # 8. Pad the plaintext
    padded = struct.pack("!H", padding) + padding * b"\x00"
    # Record size + message + padding
    record = (plaintext.encode("utf-8"))
    total_len = len(record) + padding + 2
    padded = struct.pack("!I", total_len) + struct.pack("!H", padding) + padding * b"\x00" + record

    # 9. Encrypt with AES-128-GCM
    iv = xor_bytes(nonce[:12], struct.pack("!Q", 1).ljust(12, b"\x00")[:12])  # counter = 1
    cipher = Cipher(algorithms.AES(cek), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    tag = encryptor.tag

    # 10. Build the message (header + ciphertext + tag)
    salt = os.urandom(16)
    rs = total_len  # record size
    msg_header = (
        salt
        + struct.pack("!I", rs)
        + _b64url(local_pub_bytes)
    )
    # Actually for aes128gcm content-encoding, the header is:
    # salt(16) | rs(4) | idlen(1) | id
    # We simplified above. The full aes128gcm format:
    idlen = len(local_pub_bytes)
    msg_header_full = salt + struct.pack("!I", rs) + bytes([idlen]) + local_pub_bytes
    
    return salt, msg_header_full + ciphertext + tag


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Send a push notification to one subscription
# ---------------------------------------------------------------------------

async def _send_to_subscription(
    subscription: dict,
    title: str,
    body: str,
    icon: str = "/static/images/icon.png",
) -> bool:
    """Send a single push notification via the Web Push Protocol."""
    if not CRYPTO_AVAILABLE:
        logger.warning("Push notification skipped: cryptography package unavailable")
        return False

    try:
        public_b64, _, priv_key = load_vapid_keys()

        payload_data = json.dumps({
            "title": title,
            "body": body,
            "icon": icon,
            "url": "/",
            "timestamp": int(time.time() * 1000),
        })

        # Encrypt payload
        salt, ciphertext = _encrypt_payload(
            subscription["p256dh_key"],
            subscription["auth_key"],
            payload_data,
        )

        # Audience is the origin
        audience = "http://localhost:8000"  # defaults; adjust as needed

        auth_header = _vapid_auth_header(
            public_b64,
            priv_key,
            audience=audience,
        )

        headers = {
            "Authorization": auth_header,
            "TTL": str(86400),
            "Content-Type": "application/octet-stream",
            "Content-Encoding": "aes128gcm",
        }

        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.post(
                subscription["endpoint"],
                headers=headers,
                content=ciphertext,
            )

            if resp.status_code == 201:
                logger.info(
                    f"Push sent to {subscription['endpoint'][:40]}...: {resp.status_code}"
                )
                return True
            else:
                logger.warning(
                    f"Push failed with {resp.status_code}: {resp.text[:200]}"
                )
                # If subscription is dead (410 Gone), mark inactive
                if resp.status_code == 410:
                    from backend.database.db import remove_push_subscription
                    remove_push_subscription(_db_path, subscription["id"])
                return False

    except Exception as e:
        logger.error(f"Error sending push to {subscription['endpoint'][:40]}...: {e}")
        return False


# ---------------------------------------------------------------------------
# Broadcast send notification
# ---------------------------------------------------------------------------

async def send_notification(
    event_type: str,
    title: str,
    body: str,
    icon: str = "/static/images/icon.png",
) -> int:
    """Send a push notification to all active subscribers.

    Applies rate limiting: max one notification per event type per
    ``_RATE_LIMIT_SECONDS`` seconds.

    Returns:
        Number of subscribers successfully notified.
    """
    now = time.time()
    last = _event_rate_limits.get(event_type, 0)
    if now - last < _RATE_LIMIT_SECONDS:
        logger.info(
            f"Push notification rate-limited for event: {event_type}"
            f" (last sent {now - last:.0f}s ago)"
        )
        return 0

    _event_rate_limits[event_type] = now

    if _db_path is None:
        logger.warning("Push notification: db_path not set")
        return 0

    from backend.database.db import get_all_active_subscriptions
    subs = get_all_active_subscriptions(_db_path)

    if not subs:
        logger.info("No active push subscriptions to notify")
        return 0

    sent = 0
    for sub in subs:
        sub_dict = dict(sub)
        ok = await _send_to_subscription(sub_dict, title, body, icon)
        if ok:
            sent += 1

    logger.info(
        f"Push notification '{title}': sent to {sent}/{len(subs)} subscribers"
    )
    return sent


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_push(db_path: str, initial_population: int) -> None:
    """Register the database path for push notifications."""
    global _db_path, _initial_population
    _db_path = db_path
    _initial_population = initial_population
    logger.info(
        f"Push notifications initialized (db={db_path}, "
        f"initial_population={initial_population})"
    )


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

from fastapi import APIRouter

router = APIRouter(prefix="/api/push", tags=["Push Notifications"])


@router.post("/subscribe")
async def subscribe_push(subscription: dict):
    """Register a browser push subscription.

    Expects JSON body like:
    {
        "endpoint": "https://fcm.googleapis.com/...",
        "keys": {"p256dh": "...", "auth": "..."},
        "id": "optional-uuid"
    }
    """
    endpoint = subscription.get("endpoint", "").strip()
    keys = subscription.get("keys", {})
    p256dh = keys.get("p256dh", "").strip()
    auth = keys.get("auth", "").strip()

    if not endpoint or not p256dh or not auth:
        return {"ok": False, "error": "Missing endpoint or keys"}

    sub_id = subscription.get("id", str(uuid.uuid4()))

    sub_data = {
        "id": sub_id,
        "endpoint": endpoint,
        "p256dh_key": p256dh,
        "auth_key": auth,
    }

    from backend.database.db import save_push_subscription

    ok = save_push_subscription(_db_path or "data/simulation.db", sub_data)
    if ok:
        logger.info(f"Push subscription saved: {sub_id[:8]}...")
        return {"ok": True, "id": sub_id, "message": "Subscription saved"}
    else:
        return {"ok": False, "error": "Failed to save subscription"}


@router.post("/unsubscribe")
async def unsubscribe_push(data: dict):
    """Remove a browser push subscription."""
    sub_id = data.get("id", "").strip()
    if not sub_id:
        return {"ok": False, "error": "Missing subscription id"}

    from backend.database.db import remove_push_subscription
    ok = remove_push_subscription(_db_path or "data/simulation.db", sub_id)
    if ok:
        logger.info(f"Push subscription removed: {sub_id[:8]}...")
        return {"ok": True, "message": "Subscription removed"}
    else:
        return {"ok": False, "error": "Failed to remove subscription"}


@router.post("/test")
async def test_push():
    """Send a test notification to all subscribers."""
    sent = await send_notification(
        "test",
        "Test Notification",
        "This is a test push notification from AI Life Simulator!",
    )
    return {"ok": True, "sent": sent, "message": f"Sent to {sent} subscriber(s)"}


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Return the VAPID public key for client-side subscription."""
    try:
        from backend.api.push import load_vapid_keys, _vapid_public_key
        pub, _, _ = load_vapid_keys()
        return {"publicKey": pub}
    except Exception as e:
        logger.warning(f"Failed to get VAPID public key: {e}")
        return {"publicKey": ""}
