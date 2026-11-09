import os

from sqlalchemy import URL, create_engine


def crear_engine():
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["CLOUDSQL_DB_USER"],
        password=os.environ["CLOUDSQL_DB_PASSWORD"],
        host=os.getenv("CLOUDSQL_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("CLOUDSQL_DB_PORT", "5433")),
        database=os.environ["CLOUDSQL_DB_NAME"],
    )

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )