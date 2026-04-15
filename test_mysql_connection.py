from sqlalchemy import create_engine, text
from app.config import settings


def main():
    print("Testando conexão MySQL...")
    print("DATABASE_URL carregada com sucesso.")

    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT DATABASE() AS db, USER() AS user, 1 AS ok"))
            row = result.fetchone()
            print("Conexão OK!")
            print(row)

    except Exception as e:
        print("Erro ao conectar no MySQL:")
        print(repr(e))


if __name__ == "__main__":
    main()