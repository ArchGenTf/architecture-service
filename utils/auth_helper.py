import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import bcrypt
import jwt

logger = logging.getLogger("auth_helper")

# ─── Configuration ───────────────────────────────────────────────────────────

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "archgen_super_secure_secret_hash_key_12345!"
)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24   # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7


# ─── Password Hashing (native bcrypt — no passlib dependency) ────────────────

def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using bcrypt directly.
    Using bcrypt natively avoids passlib version conflicts on Windows with
    bcrypt >= 4.0.0, where passlib's ABI bindings may raise AttributeError.
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against a stored bcrypt hash.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


# ─── JWT Token Generation ────────────────────────────────────────────────────

def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generates a signed JWT access token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta if expires_delta
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """
    Generates a signed JWT refresh token with a longer expiry.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and validates a JWT token.
    Returns the payload dict on success, or None if invalid / expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired.")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"JWT decode error: {e}")
        return None
