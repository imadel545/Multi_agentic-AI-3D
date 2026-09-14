import hashlib
import hmac
import secrets
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

SESSION_COOKIE = "telecom_studio_session"
_PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/auth/status",
        "/auth/register",
        "/auth/setup",
        "/auth/login",
        "/auth/logout",
    }
)
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LENGTH = 32


class PasswordRequest(BaseModel):
    password: SecretStr = Field(min_length=12, max_length=256)


class LoginRequest(PasswordRequest):
    email: str | None = Field(default=None, max_length=254)
    username: str | None = Field(default=None, max_length=128)


class RegistrationRequest(PasswordRequest):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        display_name = value.strip()
        if not 2 <= len(display_name) <= 80 or any(
            ord(character) < 32 for character in display_name
        ):
            raise ValueError("display name must contain 2 to 80 visible characters")
        return display_name


class LocalAuthStore:
    """Persistent single-owner credentials and revocable opaque sessions."""

    def __init__(
        self,
        path: Path,
        *,
        session_ttl_seconds: int,
        login_window_seconds: int,
        login_max_failures: int,
        login_lock_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self.session_ttl_seconds = session_ttl_seconds
        self.login_window_seconds = login_window_seconds
        self.login_max_failures = login_max_failures
        self.login_lock_seconds = login_lock_seconds
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def _migrate(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS local_auth_owner (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    username TEXT,
                    username_normalized TEXT,
                    display_name TEXT,
                    email TEXT,
                    email_normalized TEXT
                );
                CREATE TABLE IF NOT EXISTS local_auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_local_auth_sessions_expiry
                    ON local_auth_sessions(expires_at);
                CREATE TABLE IF NOT EXISTS local_auth_login_throttle (
                    throttle_key TEXT PRIMARY KEY,
                    window_started_at INTEGER NOT NULL,
                    failure_count INTEGER NOT NULL,
                    locked_until INTEGER
                );
                """
            )
            owner_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(local_auth_owner)")
            }
            if "username" not in owner_columns:
                db.execute("ALTER TABLE local_auth_owner ADD COLUMN username TEXT")
            if "username_normalized" not in owner_columns:
                db.execute("ALTER TABLE local_auth_owner ADD COLUMN username_normalized TEXT")
            if "display_name" not in owner_columns:
                db.execute("ALTER TABLE local_auth_owner ADD COLUMN display_name TEXT")
            if "email" not in owner_columns:
                db.execute("ALTER TABLE local_auth_owner ADD COLUMN email TEXT")
            if "email_normalized" not in owner_columns:
                db.execute("ALTER TABLE local_auth_owner ADD COLUMN email_normalized TEXT")

    def setup_required(self) -> bool:
        with self._connect() as db:
            return (
                db.execute("SELECT 1 FROM local_auth_owner WHERE singleton_id = 1").fetchone()
                is None
            )

    def create_owner(
        self,
        password: str,
        *,
        email: str | None = None,
        username: str | None = None,
        display_name: str | None = None,
    ) -> str:
        password_bytes = _validated_password(password)
        normalized_email = _normalize_email(email)
        if email is not None and normalized_email is None:
            raise ValueError("invalid_email")
        salt = secrets.token_bytes(16)
        password_hash = _derive_password(password_bytes, salt)
        now = int(self._clock())
        with self._connect() as db:
            try:
                db.execute(
                    """
                    INSERT INTO local_auth_owner (
                        singleton_id, password_salt, password_hash, created_at, updated_at,
                        username, username_normalized, display_name, email, email_normalized
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        salt,
                        password_hash,
                        now,
                        now,
                        username,
                        _normalize_username(username),
                        display_name,
                        email,
                        normalized_email,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("owner_already_configured") from exc
        return self._create_session(now)

    def login(
        self,
        password: str,
        email: str | None = None,
        username: str | None = None,
        throttle_key: str = "local_owner",
    ) -> str:
        now = int(self._clock())
        with self._connect() as db:
            throttle = db.execute(
                "SELECT * FROM local_auth_login_throttle WHERE throttle_key = ?",
                (throttle_key,),
            ).fetchone()
            if throttle and throttle["locked_until"] and throttle["locked_until"] > now:
                raise PermissionError("login_throttled")
            owner = db.execute(
                """
                SELECT password_salt, password_hash, email_normalized, username_normalized
                FROM local_auth_owner WHERE singleton_id = 1
                """
            ).fetchone()

        password_bytes = _validated_password(password)
        if owner is None:
            _derive_password(password_bytes, bytes(16))
            raise LookupError("owner_not_configured")
        candidate = _derive_password(password_bytes, owner["password_salt"])
        stored_email = owner["email_normalized"]
        stored_username = owner["username_normalized"]
        identity_matches = True
        if stored_email is not None:
            identity_matches = hmac.compare_digest(
                (_normalize_email(email) or "").encode("utf-8"),
                str(stored_email).encode("utf-8"),
            )
        elif stored_username is not None:
            identity_matches = hmac.compare_digest(
                (_normalize_username(username) or "").encode("utf-8"),
                str(stored_username).encode("utf-8"),
            )
        if not identity_matches or not hmac.compare_digest(candidate, owner["password_hash"]):
            self._record_failed_login(throttle_key, now)
            raise PermissionError("invalid_credentials")
        with self._connect() as db:
            db.execute(
                "DELETE FROM local_auth_login_throttle WHERE throttle_key = ?",
                (throttle_key,),
            )
        return self._create_session(now)

    def required_identity(self) -> tuple[bool, bool]:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT email_normalized, username_normalized FROM local_auth_owner
                WHERE singleton_id = 1
                """
            ).fetchone()
        requires_email = bool(row and row["email_normalized"])
        requires_username = bool(row and not requires_email and row["username_normalized"])
        return requires_email, requires_username

    def owner_profile(self) -> dict[str, str] | None:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT email, username, display_name FROM local_auth_owner
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None or not row["display_name"]:
            return None
        if row["email"]:
            return {"email": str(row["email"]), "display_name": str(row["display_name"])}
        if row["username"]:
            return {"username": str(row["username"]), "display_name": str(row["display_name"])}
        return None

    def session_expiry(self, token: str | None) -> int | None:
        if not token:
            return None
        now = int(self._clock())
        with self._connect() as db:
            row = db.execute(
                """
                SELECT expires_at FROM local_auth_sessions
                WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?
                """,
                (_token_hash(token), now),
            ).fetchone()
            db.execute(
                "DELETE FROM local_auth_sessions WHERE expires_at <= ? OR revoked_at IS NOT NULL",
                (now,),
            )
        return int(row["expires_at"]) if row else None

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as db:
            db.execute(
                "UPDATE local_auth_sessions SET revoked_at = ? WHERE token_hash = ?",
                (int(self._clock()), _token_hash(token)),
            )

    def _create_session(self, now: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO local_auth_sessions (token_hash, created_at, expires_at, revoked_at)
                VALUES (?, ?, ?, NULL)
                """,
                (_token_hash(token), now, now + self.session_ttl_seconds),
            )
        return token

    def _record_failed_login(self, throttle_key: str, now: int) -> None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM local_auth_login_throttle WHERE throttle_key = ?",
                (throttle_key,),
            ).fetchone()
            if row is None or now - row["window_started_at"] >= self.login_window_seconds:
                count = 1
                window_started_at = now
            else:
                count = int(row["failure_count"]) + 1
                window_started_at = int(row["window_started_at"])
            locked_until = (
                now + self.login_lock_seconds if count >= self.login_max_failures else None
            )
            db.execute(
                """
                INSERT INTO local_auth_login_throttle (
                    throttle_key, window_started_at, failure_count, locked_until
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(throttle_key) DO UPDATE SET
                    window_started_at = excluded.window_started_at,
                    failure_count = excluded.failure_count,
                    locked_until = excluded.locked_until
                """,
                (throttle_key, window_started_at, count, locked_until),
            )


class LocalAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        store: LocalAuthStore,
        enabled: bool | Callable[[], bool],
        allowed_origins: list[str],
        cookie_name: str = SESSION_COOKIE,
    ) -> None:
        super().__init__(app)
        self.store = store
        self.enabled = enabled
        self.allowed_origins = allowed_origins
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next):
        enabled = self.enabled() if callable(self.enabled) else self.enabled
        if (
            enabled
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and not _request_origin_allowed(request, self.allowed_origins)
        ):
            return Response(
                content='{"detail":"Origin is not allowed for authenticated mutations."}',
                status_code=403,
                media_type="application/json",
            )
        if not enabled or request.method == "OPTIONS" or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        expiry = self.store.session_expiry(request.cookies.get(self.cookie_name))
        if expiry is None:
            return Response(
                content='{"detail":"Authentication required."}',
                status_code=401,
                media_type="application/json",
            )
        request.state.auth_session_expires_at = expiry
        return await call_next(request)


def create_auth_router(
    store: LocalAuthStore,
    *,
    enabled: bool | Callable[[], bool],
    cookie_secure: bool,
    allowed_origins: list[str],
    cookie_name: str = SESSION_COOKIE,
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["local-auth"])

    @router.get("/status")
    def auth_status(request: Request) -> dict:
        auth_enabled = enabled() if callable(enabled) else enabled
        if not auth_enabled:
            return {"enabled": False, "setup_required": False, "authenticated": True}
        expiry = store.session_expiry(request.cookies.get(cookie_name))
        requires_email, requires_username = store.required_identity()
        payload = {
            "enabled": True,
            "setup_required": store.setup_required(),
            "authenticated": expiry is not None,
            "expires_at": expiry,
            "requires_email": requires_email,
            "requires_username": requires_username,
        }
        if expiry is not None:
            profile = store.owner_profile()
            if profile is not None:
                payload["profile"] = profile
        return payload

    @router.post("/register")
    def register_owner(
        payload: RegistrationRequest,
        request: Request,
        response: Response,
    ) -> dict:
        auth_enabled = enabled() if callable(enabled) else enabled
        if not auth_enabled:
            raise HTTPException(status_code=404, detail="Local authentication is disabled.")
        if not _is_local_setup_request(request, allowed_origins):
            raise HTTPException(
                status_code=403,
                detail="Initial registration is limited to local access.",
            )
        try:
            token = store.create_owner(
                payload.password.get_secret_value(),
                email=str(payload.email),
                display_name=payload.display_name,
            )
        except ValueError as exc:
            detail = (
                "The local owner is already configured."
                if str(exc) == "owner_already_configured"
                else str(exc)
            )
            raise HTTPException(status_code=409, detail=detail) from exc
        _set_session_cookie(
            response,
            token,
            store.session_ttl_seconds,
            cookie_secure,
            cookie_name,
        )
        return {
            "enabled": True,
            "setup_required": False,
            "authenticated": True,
            "requires_email": True,
            "requires_username": False,
            "profile": store.owner_profile(),
        }

    @router.post("/setup")
    def setup_owner(payload: PasswordRequest, request: Request, response: Response) -> dict:
        auth_enabled = enabled() if callable(enabled) else enabled
        if not auth_enabled:
            raise HTTPException(status_code=404, detail="Local authentication is disabled.")
        if not _is_local_setup_request(request, allowed_origins):
            raise HTTPException(status_code=403, detail="Initial setup is limited to local access.")
        try:
            token = store.create_owner(payload.password.get_secret_value())
        except ValueError as exc:
            detail = (
                "The local owner is already configured."
                if str(exc) == "owner_already_configured"
                else str(exc)
            )
            raise HTTPException(status_code=409, detail=detail) from exc
        _set_session_cookie(
            response,
            token,
            store.session_ttl_seconds,
            cookie_secure,
            cookie_name,
        )
        return {"enabled": True, "setup_required": False, "authenticated": True}

    @router.post("/login")
    def login(payload: LoginRequest, request: Request, response: Response) -> dict:
        auth_enabled = enabled() if callable(enabled) else enabled
        if not auth_enabled:
            raise HTTPException(status_code=404, detail="Local authentication is disabled.")
        try:
            token = store.login(
                payload.password.get_secret_value(),
                email=payload.email,
                username=payload.username,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=409,
                detail="The local owner is not configured.",
            ) from exc
        except PermissionError as exc:
            if str(exc) == "login_throttled":
                raise HTTPException(
                    status_code=429,
                    detail="Too many login attempts. Try again later.",
                ) from exc
            raise HTTPException(status_code=401, detail="Invalid credentials.") from exc
        _set_session_cookie(
            response,
            token,
            store.session_ttl_seconds,
            cookie_secure,
            cookie_name,
        )
        requires_email, requires_username = store.required_identity()
        result = {
            "enabled": True,
            "setup_required": False,
            "authenticated": True,
            "requires_email": requires_email,
            "requires_username": requires_username,
        }
        profile = store.owner_profile()
        if profile is not None:
            result["profile"] = profile
        return result

    @router.post("/logout")
    def logout(request: Request, response: Response) -> dict:
        store.revoke(request.cookies.get(cookie_name))
        response.delete_cookie(
            cookie_name,
            path="/",
            secure=cookie_secure,
            httponly=True,
            samesite="strict",
        )
        return {"authenticated": False}

    return router


def _validated_password(password: str) -> bytes:
    return password.encode("utf-8")


def _normalize_username(username: str | None) -> str | None:
    if username is None:
        return None
    normalized = username.strip().casefold()
    return normalized or None


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    try:
        normalized = validate_email(email.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        return None
    return normalized.casefold()


def _derive_password(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password,
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LENGTH,
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_session_cookie(
    response: Response,
    token: str,
    ttl: int,
    secure: bool,
    cookie_name: str,
) -> None:
    response.set_cookie(
        cookie_name,
        token,
        max_age=ttl,
        path="/",
        secure=secure,
        httponly=True,
        samesite="strict",
    )


def _is_local_setup_request(request: Request, allowed_origins: list[str]) -> bool:
    if request.url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return False
    return _request_origin_allowed(request, allowed_origins)


def _request_origin_allowed(request: Request, allowed_origins: list[str]) -> bool:
    origin = request.headers.get("origin")
    if origin is None or origin in allowed_origins:
        return True
    try:
        parsed = urlsplit(origin)
        request_host = request.url.hostname
        request_port = request.url.port or (443 if request.url.scheme == "https" else 80)
        origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return False
    return (
        parsed.scheme == request.url.scheme
        and parsed.hostname == request_host
        and origin_port == request_port
    )
