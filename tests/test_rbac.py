
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.database import Base, get_db
from app.models.models import User
from app.services.security import hash_password
from app.services.auth_dependencies import get_current_user, require_role


@pytest.fixture
def rbac_client():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    TestingSessionLocal = sessionmaker(bind=engine)

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    users = [
        User(
            username="admin",
            email="admin@rbac.com",
            password_hash=hash_password("Admin@12345"),
            role="admin",
            is_active=True
        ),
        User(
            username="attendee",
            email="attendee@rbac.com",
            password_hash=hash_password("Test@12345"),
            role="attendee",
            is_active=True
        ),
        User(
            username="organiser",
            email="organiser@rbac.com",
            password_hash=hash_password("Organiser@12345"),
            role="organiser",
            is_active=True
        ),
        User(
            username="staff",
            email="staff@rbac.com",
            password_hash=hash_password("Staff@12345"),
            role="gate_staff",
            is_active=True
        )
    ]

    db.add_all(users)
    db.commit()

    app = FastAPI()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db

    app.dependency_overrides[get_current_user] = lambda: db.query(User).filter(
        User.username == "attendee"
    ).first()

    @app.get("/admin-test")
    def admin_test(user=__import__("fastapi").Depends(require_role("admin"))):
        return {"message": "Admin access granted"}

    @app.get("/organiser-test")
    def organiser_test(user=__import__("fastapi").Depends(require_role("organiser"))):
        return {"message": "Organiser access granted"}

    @app.get("/staff-test")
    def staff_test(user=__import__("fastapi").Depends(require_role("gate_staff"))):
        return {"message": "Staff access granted"}

    with TestClient(app) as client:
        yield client, db

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_attendee_denied_admin_access(rbac_client):
    client, db = rbac_client

    response = client.get("/admin-test")

    assert response.status_code == 403


def test_attendee_denied_organiser_access(rbac_client):
    client, db = rbac_client

    response = client.get("/organiser-test")

    assert response.status_code == 403


def test_attendee_denied_gate_staff_access(rbac_client):
    client, db = rbac_client

    response = client.get("/staff-test")

    assert response.status_code == 403
