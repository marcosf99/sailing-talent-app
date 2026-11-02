import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5433")),
    database=os.environ["DB_NAME"],
)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine)


def probar_conexion():
    with engine.connect() as conexion:
        base = conexion.execute(
            text("SELECT current_database()")
        ).scalar_one()
        print(f"Conexión correcta con: {base}")

        resultado = conexion.execute(
            text("""
                SELECT 'Federaciones' AS tabla, COUNT(*) AS total
                FROM public.federacion_autonomica
                UNION ALL
                SELECT 'Clubes', COUNT(*) FROM public.club
                UNION ALL
                SELECT 'Clases', COUNT(*) FROM public.clase
            """)
        )

        for tabla, total in resultado:
            print(f"{tabla}: {total}")


if __name__ == "__main__":
    try:
        probar_conexion()
    finally:
        engine.dispose()