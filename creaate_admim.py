from app.db import SessionLocal
from app.models import User
from app.auth import hash_password


def main():
    db = SessionLocal()

    email = "admin@aposta.com"
    password = "123456"
    name = "Administrador"

    exists = db.query(User).filter(User.email == email).first()
    if exists:
        print("Usuário já existe.")
        db.close()
        return

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()

    print(f"Usuário criado com sucesso: {email}")


if __name__ == "__main__":
    main()