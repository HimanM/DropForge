from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SESSION_TTL = 60 * 60 * 24 * 7
PASSWORD_MIN_LENGTH = 12
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1


def validate_password(password: str) -> None:
    encoded = password.encode("utf-8")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(encoded) > 1024:
        raise ValueError("Password is too long.")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _hash_secret(secret: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def _verify_secret(secret: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            secret.encode("utf-8"),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class Session:
    token_hash: str
    csrf_token: str
    expires_at: int


class AuthStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS secrets (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                """
            )
        if os.name != "nt":
            self.path.chmod(0o600)

    def is_provisioned(self) -> bool:
        with self._db() as db:
            row = db.execute("SELECT 1 FROM secrets WHERE name = 'password'").fetchone()
        return row is not None

    def provision(self, password: str, recovery_code: str) -> bool:
        validate_password(password)
        if len(recovery_code) < 20:
            raise ValueError("Recovery code must be at least 20 characters.")
        with self._db() as db:
            if db.execute("SELECT 1 FROM secrets WHERE name = 'password'").fetchone():
                return False
            db.executemany(
                "INSERT INTO secrets(name, value) VALUES (?, ?)",
                (
                    ("password", _hash_secret(password)),
                    ("recovery", _hash_secret(recovery_code)),
                ),
            )
        return True

    def verify_password(self, password: str) -> bool:
        with self._db() as db:
            row = db.execute("SELECT value FROM secrets WHERE name = 'password'").fetchone()
        return row is not None and _verify_secret(password, row[0])

    def create_session(self) -> tuple[str, Session]:
        token = secrets.token_urlsafe(32)
        session = Session(
            token_hash=_token_hash(token),
            csrf_token=secrets.token_urlsafe(24),
            expires_at=int(time.time()) + SESSION_TTL,
        )
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            db.execute(
                "INSERT INTO sessions(token_hash, csrf_token, expires_at) VALUES (?, ?, ?)",
                (session.token_hash, session.csrf_token, session.expires_at),
            )
        return token, session

    def get_session(self, token: str) -> Session | None:
        token_hash = _token_hash(token)
        with self._db() as db:
            row = db.execute(
                "SELECT csrf_token, expires_at FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if row[1] <= int(time.time()):
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                return None
        return Session(token_hash=token_hash, csrf_token=row[0], expires_at=row[1])

    def delete_session(self, token: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    def change_password(self, current_password: str, new_password: str) -> bool:
        validate_password(new_password)
        with self._db() as db:
            row = db.execute("SELECT value FROM secrets WHERE name = 'password'").fetchone()
            if row is None or not _verify_secret(current_password, row[0]):
                return False
            db.execute(
                "UPDATE secrets SET value = ? WHERE name = 'password'",
                (_hash_secret(new_password),),
            )
            db.execute("DELETE FROM sessions")
        return True

    def reset_password(self, recovery_code: str, new_password: str) -> str | None:
        validate_password(new_password)
        with self._db() as db:
            row = db.execute("SELECT value FROM secrets WHERE name = 'recovery'").fetchone()
            if row is None or not _verify_secret(recovery_code, row[0]):
                return None
            next_recovery = secrets.token_urlsafe(24)
            db.execute(
                "UPDATE secrets SET value = ? WHERE name = 'password'",
                (_hash_secret(new_password),),
            )
            db.execute(
                "UPDATE secrets SET value = ? WHERE name = 'recovery'",
                (_hash_secret(next_recovery),),
            )
            db.execute("DELETE FROM sessions")
        return next_recovery

    def force_password(self, new_password: str) -> str:
        validate_password(new_password)
        next_recovery = secrets.token_urlsafe(24)
        with self._db() as db:
            db.execute(
                "INSERT INTO secrets(name, value) VALUES ('password', ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (_hash_secret(new_password),),
            )
            db.execute(
                "INSERT INTO secrets(name, value) VALUES ('recovery', ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (_hash_secret(next_recovery),),
            )
            db.execute("DELETE FROM sessions")
        return next_recovery
