from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate
from app.utils.security import hash_password, verify_password


class AuthService:
    """Service handling user registration, credential verification, and user lookup."""

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Fetch user by unique email address."""
        result = await db.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """Fetch user by primary key ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @classmethod
    async def register_user(cls, db: AsyncSession, user_in: UserCreate) -> User:
        """
        Register a new user account.
        Raises HTTP 409 if the email is already in use.
        """
        normalized_email = user_in.email.lower().strip()
        existing_user = await cls.get_user_by_email(db, normalized_email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address already exists.",
            )

        new_user = User(
            name=user_in.name.strip(),
            email=normalized_email,
            password_hash=hash_password(user_in.password),
            is_active=True,
        )
        db.add(new_user)
        await db.flush()
        await db.refresh(new_user)
        return new_user

    @classmethod
    async def authenticate_user(
        cls, db: AsyncSession, email: str, password: str
    ) -> User:
        """
        Authenticate user with email and plaintext password.
        Raises HTTP 401 if credentials are invalid or user is inactive.
        """
        user = await cls.get_user_by_email(db, email)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive.",
            )

        return user
