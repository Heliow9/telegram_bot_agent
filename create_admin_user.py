from app.db import SessionLocal
from app.models import User
from app.auth import hash_password


def main():
    db = SessionLocal()

    # ===== CONFIG DO ADMIN =====
    name = "Admin"
    email = "admin@aposta.com"
    password = "123456"  # depois troca isso no dashboard
    # ==========================

    print("🔍 Verificando se usuário já existe...")

    existing = db.query(User).filter(User.email == email).first()

    if existing:
        print("⚠️ Usuário já existe:")
        print(f"ID: {existing.id} | Email: {existing.email}")
        db.close()
        return

    print("🛠️ Criando novo usuário admin...")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    print("✅ Usuário criado com sucesso!")
    print(f"ID: {user.id}")
    print(f"Email: {user.email}")

    db.close()


if __name__ == "__main__":
    main()