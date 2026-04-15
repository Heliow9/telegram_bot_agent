import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.auth import verify_password, create_access_token
from app.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    password_len = (
        len(payload.password.encode("utf-8"))
        if isinstance(payload.password, str)
        else None
    )

    logger.info(
        "Tentativa de login | email=%s | password_bytes_len=%s",
        payload.email,
        password_len,
    )

    user = (
        db.query(User)
        .filter(User.email == payload.email, User.is_active.is_(True))
        .first()
    )

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha inválidos",
        )

    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user