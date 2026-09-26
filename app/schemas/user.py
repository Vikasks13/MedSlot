from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Base fields shared by user models."""
    name: str = Field(..., min_length=2, max_length=100, description="Full name of user")
    email: EmailStr = Field(..., description="Unique email address")


class UserCreate(UserBase):
    """Schema for user registration request."""
    password: str = Field(
        ...,
        min_length=6,
        max_length=72,
        description="Password (between 6 and 72 characters)",
    )


class UserLogin(BaseModel):
    """Schema for user login request."""
    email: EmailStr
    password: str


class UserResponse(UserBase):
    """Schema for returning user data (excluding password hash)."""
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
