import os

from sqlalchemy import URL, create_engine


def crear_engine():
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(os.getenv("SUPABASE_DB_PORT", "5432")),
        database=os.getenv("SUPABASE_DB_NAME", "postgres"),
    )

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 10,
            "sslmode": "require",
        },
    )