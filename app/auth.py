import logging
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if not isinstance(plain_password, str) or not plain_password:
            return False

        if not isinstance(hashed_password, str) or not hashed_password:
            return False

        password_bytes_len = len(plain_password.encode("utf-8"))
        if password_bytes_len > 72:
            logger.warning(
                "Senha recebida excede 72 bytes no login. bytes_len=%s",
                password_bytes_len,
            )
            return False

        return pwd_context.verify(plain_password, hashed_password)

    except Exception as e:
        logger.exception("Erro ao verificar senha: %s", e)
        return False


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("Senha inválida")

    password_bytes_len = len(password.encode("utf-8"))
    if password_bytes_len > 72:
        raise ValueError("Senha não pode exceder 72 bytes para bcrypt")

    return pwd_context.hash(password)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": subject,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )