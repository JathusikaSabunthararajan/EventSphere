
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.services.auth_dependencies import require_role

from app.services.auth_dependencies import get_current_user

from app.database.database import get_db
from app.models.models import User
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse
)
from app.services.security import (
    hash_password,
    verify_password,
    create_access_token
)

from app.services.auth_dependencies import get_current_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# User Registration
@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    user_data: UserRegister,
    db: Session = Depends(get_db)
):

    # Check existing email
    existing_user = db.query(User).filter(
        User.email == user_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email is already registered."
        )

    # Check existing username
    existing_username = db.query(User).filter(
        User.username == user_data.username
    ).first()

    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username is already taken."
        )

    if len(user_data.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 8 characters."
        )

    # Public registration only creates attendee accounts.
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role="attendee"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# User Login
@router.post(
    "/login",
    response_model=TokenResponse
)
def login_user(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.email == login_data.email
    ).first()

    if not user or not verify_password(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive."
        )

    access_token = create_access_token({
        "sub": str(user.id),
        "role": user.role
    })

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=UserResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user


@router.get("/admin-check")
def admin_check(
    current_user: User = Depends(require_role("admin"))
):
    return {
        "message": "Admin access granted!",
        "username": current_user.username,
        "role": current_user.role
    }

@router.get("/organiser-check")
def organiser_check(
    current_user: User = Depends(require_role("organiser"))
):
    return {
        "message": "Organiser access granted!",
        "username": current_user.username,
        "role": current_user.role
    }


@router.get("/staff-check")
def staff_check(
    current_user: User = Depends(require_role("gate_staff"))
):
    return {
        "message": "Gate Staff access granted!",
        "username": current_user.username,
        "role": current_user.role
    }

# Get currently logged-in user
@router.get("/me")
def get_my_profile(
    current_user: User = Depends(get_current_user)
):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role
    }
