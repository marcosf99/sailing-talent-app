import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def crear_engine(provider=None):
    provider = (
        provider or os.getenv("DB_PROVIDER", "cloudsql")
    ).strip().lower()

    if provider == "cloudsql":
        from database.cloudsql import crear_engine as crear
    elif provider == "supabase":
        from database.supabase import crear_engine as crear
    else:
        raise ValueError(
            f"Proveedor no válido: {provider}. "
            "Utiliza cloudsql o supabase."
        )

    return crear()


def crear_session_factory(engine):
    return sessionmaker(bind=engine)


def probar_conexion(engine):
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


def main():
    parser = argparse.ArgumentParser(
        description="Prueba la conexión a la base de datos."
    )
    parser.add_argument(
        "--db-provider",
        choices=["cloudsql", "supabase"],
        default=None,
        help="Tiene prioridad sobre DB_PROVIDER del archivo .env.",
    )
    args = parser.parse_args()

    provider = args.db_provider or os.getenv(
        "DB_PROVIDER", "cloudsql"
    )
    engine = crear_engine(provider)

    try:
        print(f"Proveedor seleccionado: {provider}")
        probar_conexion(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()