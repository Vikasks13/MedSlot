from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.services.auth_service import AuthService
from app.utils.rate_limit import auth_rate_limiter
from app.utils.security import create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration",
    description="Register a new user account with unique email address.",
)
async def signup(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Register a new user."""
    return await AuthService.register_user(db, user_in)


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="User Login (JSON)",
    description="Authenticate with email & password, returning a JWT access token.",
    dependencies=[Depends(auth_rate_limiter)],
)
async def login_json(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Authenticate via JSON payload and return JWT token."""
    user = await AuthService.authenticate_user(
        db, email=credentials.email, password=credentials.password
    )
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")


@router.post(
    "/login/token",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="User Login (OAuth2 Form)",
    description="OAuth2-compatible token endpoint for Swagger UI Authorize button (username is email).",
    include_in_schema=True,
    dependencies=[Depends(auth_rate_limiter)],
)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Authenticate via standard form-encoded credentials for Swagger UI."""
    user = await AuthService.authenticate_user(
        db, email=form_data.username, password=form_data.password
    )
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User Profile",
    description="Retrieve details of the currently authenticated user using JWT Bearer token.",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return authenticated user profile."""
    return current_user
