
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base, get_db
from app.models.models import User
from app.routers.auth import router as auth_router


# Create a separate in-memory test database
@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(test_db):
    test_app = FastAPI()
    test_app.include_router(auth_router)

    def override_get_db():
        yield test_db

    test_app.dependency_overrides[get_db] = override_get_db

    with TestClient(test_app) as test_client:
        yield test_client

    test_app.dependency_overrides.clear()


@pytest.fixture
def admin_user(test_db):
    from app.services.security import hash_password

    user = User(
        username="admin",
        email="admin@test.com",
        password_hash=hash_password("Admin@12345"),
        role="admin",
        is_active=True
    )

    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    return user


@pytest.fixture
def attendee_user(test_db):
    from app.services.security import hash_password

    user = User(
        username="attendee",
        email="attendee@test.com",
        password_hash=hash_password("Test@12345"),
        role="attendee",
        is_active=True
    )

    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    return user


def test_user_registration(client):
    response = client.post(
        "/auth/register",
        json={
            "username": "newuser",
            "email": "newuser@test.com",
            "password": "Test@12345",
            "role": "attendee"
        }
    )

    assert response.status_code == 201
    assert response.json()["username"] == "newuser"
    assert response.json()["role"] == "attendee"


def test_duplicate_email_registration(client):
    client.post(
        "/auth/register",
        json={
            "username": "user1",
            "email": "duplicate@test.com",
            "password": "Test@12345"
        }
    )

    response = client.post(
        "/auth/register",
        json={
            "username": "user2",
            "email": "duplicate@test.com",
            "password": "Test@12345"
        }
    )

    assert response.status_code == 400


def test_successful_login(client, attendee_user):
    response = client.post(
        "/auth/login",
        json={
            "email": "attendee@test.com",
            "password": "Test@12345"
        }
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_invalid_password(client, attendee_user):
    response = client.post(
        "/auth/login",
        json={
            "email": "attendee@test.com",
            "password": "WrongPassword123"
        }
    )

    assert response.status_code == 401


def test_protected_profile_without_token(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_admin_access_denied_for_attendee(client, attendee_user):
    login_response = client.post(
        "/auth/login",
        json={
            "email": "attendee@test.com",
            "password": "Test@12345"
        }
    )

    token = login_response.json()["access_token"]

    response = client.get(
        "/auth/admin-check",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_admin_access_allowed(client, admin_user):
    login_response = client.post(
        "/auth/login",
        json={
            "email": "admin@test.com",
            "password": "Admin@12345"
        }
    )

    token = login_response.json()["access_token"]

    response = client.get(
        "/auth/admin-check",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
