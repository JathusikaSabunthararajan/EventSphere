
from pydantic import BaseModel, EmailStr


# User registration request
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "attendee"


# User login request
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# User details returned after registration
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str


# JWT token response
class TokenResponse(BaseModel):
    access_token: str
    token_type: str
