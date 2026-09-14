import hashlib
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.auth import (
    LocalAuthMiddleware,
    LocalAuthStore,
    _derive_password,
    create_auth_router,
)


def _auth_app(store: LocalAuthStore) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        LocalAuthMiddleware,
        store=store,
        enabled=True,
        allowed_origins=["http://127.0.0.1:5173"],
    )
    app.include_router(
        create_auth_router(
            store,
            enabled=True,
            cookie_secure=False,
            allowed_origins=["http://127.0.0.1:5173"],
        )
    )

    @app.get("/designs")
    def protected_designs() -> dict:
        return {"protected": True}

    return app


def _store(tmp_path: Path, clock=lambda: 1_000.0, **overrides) -> LocalAuthStore:
    return LocalAuthStore(
        tmp_path / "auth.db",
        session_ttl_seconds=overrides.get("session_ttl_seconds", 600),
        login_window_seconds=overrides.get("login_window_seconds", 60),
        login_max_failures=overrides.get("login_max_failures", 3),
        login_lock_seconds=overrides.get("login_lock_seconds", 30),
        clock=clock,
    )


def test_first_local_owner_setup_issues_hashed_revocable_session(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = TestClient(_auth_app(store), base_url="http://127.0.0.1")

    assert client.get("/auth/status").json() == {
        "enabled": True,
        "setup_required": True,
        "authenticated": False,
        "expires_at": None,
        "requires_email": False,
        "requires_username": False,
    }
    assert client.get("/designs").status_code == 401
    assert client.post("/auth/setup", json={"password": "too-short"}).status_code == 422

    password = "correct horse battery staple"
    setup = client.post("/auth/setup", json={"password": password})
    assert setup.status_code == 200
    cookie = setup.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert client.get("/designs").json() == {"protected": True}
    assert client.post("/auth/setup", json={"password": password}).status_code == 409

    raw_token = client.cookies.get("telecom_studio_session")
    with sqlite3.connect(store.path) as db:
        owner = db.execute("SELECT password_salt, password_hash FROM local_auth_owner").fetchone()
        session_hash = db.execute("SELECT token_hash FROM local_auth_sessions").fetchone()[0]
    assert owner is not None
    assert password.encode() not in owner
    assert session_hash == hashlib.sha256(raw_token.encode()).hexdigest()
    assert raw_token not in session_hash

    assert client.post("/auth/logout").status_code == 200
    assert client.get("/designs").status_code == 401


def test_local_registration_creates_profile_and_requires_email_for_login(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    client = TestClient(_auth_app(store), base_url="http://127.0.0.1")

    assert (
        client.post(
            "/auth/register",
            json={
                "email": "not-an-email",
                "display_name": "Alice Martin",
                "password": "a sufficiently long password",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "alice@example.com",
                "display_name": " A ",
                "password": "a sufficiently long password",
            },
        ).status_code
        == 422
    )

    response = client.post(
        "/auth/register",
        json={
            "email": "Alice.Circet@Example.COM",
            "display_name": "  Alice Martin  ",
            "password": "a sufficiently long password",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "setup_required": False,
        "authenticated": True,
        "requires_email": True,
        "requires_username": False,
        "profile": {
            "email": "Alice.Circet@example.com",
            "display_name": "Alice Martin",
        },
    }
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "someone-else@example.com",
                "display_name": "Someone Else",
                "password": "another sufficiently long password",
            },
        ).status_code
        == 409
    )

    assert client.post("/auth/logout").status_code == 200
    anonymous_status = client.get("/auth/status").json()
    assert anonymous_status["requires_email"] is True
    assert anonymous_status["requires_username"] is False
    assert "profile" not in anonymous_status
    assert "Alice.Circet@example.com" not in str(anonymous_status)
    assert (
        client.post(
            "/auth/login",
            json={"password": "a sufficiently long password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login",
            json={
                "email": "wrong-user@example.com",
                "password": "a sufficiently long password",
            },
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login",
            json={
                "email": "alice.circet@EXAMPLE.COM",
                "password": "a sufficiently long password",
            },
        ).status_code
        == 200
    )
    assert client.get("/auth/status").json()["profile"] == {
        "email": "Alice.Circet@example.com",
        "display_name": "Alice Martin",
    }
    assert client.get("/designs").status_code == 200


def test_legacy_password_only_owner_migrates_without_requiring_username(tmp_path: Path) -> None:
    database = tmp_path / "auth.db"
    salt = b"0123456789abcdef"
    password = "legacy sufficiently long password"
    with sqlite3.connect(database) as db:
        db.execute(
            """
            CREATE TABLE local_auth_owner (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        db.execute(
            "INSERT INTO local_auth_owner VALUES (1, ?, ?, 1000, 1000)",
            (salt, _derive_password(password.encode("utf-8"), salt)),
        )

    store = _store(tmp_path)
    client = TestClient(_auth_app(store), base_url="http://127.0.0.1")
    status = client.get("/auth/status").json()

    assert status["setup_required"] is False
    assert status["requires_email"] is False
    assert status["requires_username"] is False
    assert "profile" not in status
    assert client.post("/auth/login", json={"password": password}).status_code == 200
    assert client.get("/designs").status_code == 200
    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(local_auth_owner)").fetchall()}
    assert {
        "username",
        "username_normalized",
        "display_name",
        "email",
        "email_normalized",
    } <= columns


def test_username_owner_migrates_without_fake_email_and_keeps_session(tmp_path: Path) -> None:
    database = tmp_path / "auth.db"
    salt = b"0123456789abcdef"
    password = "legacy username owner password"
    existing_token = "existing-opaque-session-token"
    with sqlite3.connect(database) as db:
        db.execute(
            """
            CREATE TABLE local_auth_owner (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                username TEXT,
                username_normalized TEXT,
                display_name TEXT
            )
            """
        )
        db.execute(
            "INSERT INTO local_auth_owner VALUES (1, ?, ?, 1000, 1000, ?, ?, ?)",
            (
                salt,
                _derive_password(password.encode("utf-8"), salt),
                "Legacy.Owner",
                "legacy.owner",
                "Legacy Owner",
            ),
        )
        db.execute(
            """
            CREATE TABLE local_auth_sessions (
                token_hash TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER
            )
            """
        )
        db.execute(
            "INSERT INTO local_auth_sessions VALUES (?, 1000, 1600, NULL)",
            (hashlib.sha256(existing_token.encode("utf-8")).hexdigest(),),
        )

    store = _store(tmp_path)
    anonymous = TestClient(_auth_app(store), base_url="http://127.0.0.1")
    status = anonymous.get("/auth/status").json()
    assert status["requires_email"] is False
    assert status["requires_username"] is True
    assert "profile" not in status

    existing_session = TestClient(_auth_app(store), base_url="http://127.0.0.1")
    existing_session.cookies.set("telecom_studio_session", existing_token)
    assert existing_session.get("/auth/status").json()["profile"] == {
        "username": "Legacy.Owner",
        "display_name": "Legacy Owner",
    }

    response = anonymous.post(
        "/auth/login",
        json={"username": "LEGACY.OWNER", "password": password},
    )
    assert response.status_code == 200
    assert response.json()["profile"] == {
        "username": "Legacy.Owner",
        "display_name": "Legacy Owner",
    }
    assert "email" not in response.json()["profile"]
    token = anonymous.cookies.get("telecom_studio_session")

    restarted_store = _store(tmp_path)
    assert restarted_store.session_expiry(existing_token) == 1_600
    assert restarted_store.session_expiry(token) == 1_600
    with sqlite3.connect(database) as db:
        owner_email = db.execute(
            "SELECT email, email_normalized FROM local_auth_owner WHERE singleton_id = 1"
        ).fetchone()
    assert owner_email == (None, None)


def test_initial_setup_rejects_a_non_local_origin(tmp_path: Path) -> None:
    client = TestClient(_auth_app(_store(tmp_path)), base_url="http://example.test")

    response = client.post(
        "/auth/setup",
        json={"password": "a sufficiently long password"},
        headers={"origin": "http://example.test"},
    )

    assert response.status_code == 403
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "alice@example.com",
                "display_name": "Alice",
                "password": "a sufficiently long password",
            },
            headers={"origin": "http://example.test"},
        ).status_code
        == 403
    )


def test_cookie_authenticated_mutations_reject_a_foreign_origin(tmp_path: Path) -> None:
    client = TestClient(_auth_app(_store(tmp_path)), base_url="http://127.0.0.1")
    assert (
        client.post("/auth/setup", json={"password": "a sufficiently long password"}).status_code
        == 200
    )

    assert (
        client.post("/auth/logout", headers={"origin": "http://127.0.0.1:7999"}).status_code == 403
    )
    assert (
        client.post("/auth/logout", headers={"origin": "http://127.0.0.1:notaport"}).status_code
        == 403
    )
    assert client.get("/designs").status_code == 200
    assert (
        client.post("/auth/logout", headers={"origin": "http://127.0.0.1:5173"}).status_code == 200
    )


def test_session_expiry_is_enforced_server_side(tmp_path: Path) -> None:
    now = [1_000.0]
    store = _store(tmp_path, clock=lambda: now[0], session_ttl_seconds=300)
    client = TestClient(_auth_app(store), base_url="http://127.0.0.1")
    assert (
        client.post("/auth/setup", json={"password": "a sufficiently long password"}).status_code
        == 200
    )
    assert client.get("/designs").status_code == 200

    now[0] += 301

    assert client.get("/designs").status_code == 401
    assert client.get("/auth/status").json()["authenticated"] is False


def test_repeated_login_failures_are_throttled(tmp_path: Path) -> None:
    now = [1_000.0]
    store = _store(
        tmp_path,
        clock=lambda: now[0],
        login_max_failures=2,
        login_lock_seconds=30,
    )
    owner = TestClient(_auth_app(store), base_url="http://127.0.0.1")
    assert (
        owner.post("/auth/setup", json={"password": "a sufficiently long password"}).status_code
        == 200
    )
    owner.post("/auth/logout")

    assert owner.post("/auth/login", json={"password": "wrong-password-one"}).status_code == 401
    assert owner.post("/auth/login", json={"password": "wrong-password-two"}).status_code == 401
    assert (
        owner.post("/auth/login", json={"password": "a sufficiently long password"}).status_code
        == 429
    )
    now[0] += 31
    assert (
        owner.post("/auth/login", json={"password": "a sufficiently long password"}).status_code
        == 200
    )


def test_main_product_routes_require_auth_when_enabled(monkeypatch) -> None:
    from apps.api.telecom_studio_api.config import settings
    from apps.api.telecom_studio_api.main import app

    monkeypatch.setattr(settings, "auth_enabled", True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/health").status_code == 200
        response = client.get("/studio/summary")
        assert client.get("/designs/wf_missing/events/stream").status_code == 401
        assert client.get("/designs/wf_missing/artifacts/design.glb").status_code == 401
        assert client.get("/openapi.json").status_code == 401
    assert response.status_code == 401
