
from app.database.database import SessionLocal
from app.models.models import User
from app.services.security import hash_password

db = SessionLocal()

test_users = [
    {
        "username": "admin",
        "email": "admin@eventsphere.com",
        "password": "Admin@12345",
        "role": "admin"
    },
    {
        "username": "organiser",
        "email": "organiser@eventsphere.com",
        "password": "Organiser@12345",
        "role": "organiser"
    },
    {
        "username": "staff",
        "email": "staff@eventsphere.com",
        "password": "Staff@12345",
        "role": "gate_staff"
    }
]

try:
    for data in test_users:
        user = db.query(User).filter(
            User.email == data["email"]
        ).first()

        if user:
            user.username = data["username"]
            user.password_hash = hash_password(data["password"])
            user.role = data["role"]
            user.is_active = True
            print(f"{data['role']} account updated.")
        else:
            user = User(
                username=data["username"],
                email=data["email"],
                password_hash=hash_password(data["password"]),
                role=data["role"],
                is_active=True
            )
            db.add(user)
            print(f"{data['role']} account created.")

    db.commit()
    print("All test accounts are ready!")

finally:
    db.close()
