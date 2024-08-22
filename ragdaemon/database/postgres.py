import os
from functools import cache
from typing import Optional

from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
    class_mapper,
    Mapped,
    mapped_column,
)

from ragdaemon.utils import EMBEDDING_DIMENSIONS


load_dotenv()


class Base(DeclarativeBase):
    def to_dict(self, exclude: list[str] = []) -> dict:
        result = {}
        for key in class_mapper(self.__class__).columns.keys():
            if key not in exclude:
                result[key] = getattr(self, key)
        return result


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id: Mapped[str] = mapped_column(primary_key=True)  # Checksum of the document
    embedding: Mapped[Vector] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    chunks: Mapped[Optional[str]]
    calls: Mapped[Optional[str]]
    summary: Mapped[Optional[str]]


@cache
def get_database_url(sync: bool = False) -> str:
    database = "ragdaemon"
    host = os.environ.get("RAGDAEMON_DB_ENDPOINT", None)
    port = os.environ.get("RAGDAEMON_DB_PORT", 5432)
    username = os.environ.get("RAGDAEMON_DB_USERNAME", None)
    password = os.environ.get("RAGDAEMON_DB_PASSWORD", None)

    if host is None or username is None or password is None:
        raise ValueError("Missing ragdaemon environment variables: cannot use PGDB.")

    if sync:
        sync_string = "+psycopg2"
    else:
        sync_string = "+asyncpg"

    return f"postgresql{sync_string}://{username}:{password}@{host}:{port}/{database}"


@cache
def get_database_engine() -> AsyncEngine:
    url = get_database_url()
    return create_async_engine(url, echo=False)


@cache
def get_database_engine_sync() -> Engine:
    url = get_database_url(sync=True)
    return create_engine(url, echo=False)


def get_database_session() -> async_sessionmaker[AsyncSession]:
    engine = get_database_engine()
    return async_sessionmaker(autocommit=False, bind=engine, class_=AsyncSession)


def get_database_session_sync() -> sessionmaker[Session]:
    engine = get_database_engine_sync()
    return sessionmaker(autocommit=False, bind=engine, class_=Session)


if __name__ == "__main__":
    if input(
        "Migrating will clear the database. ALL DATA WILL BE LOST. Proceed (Y/n)? "
    ).lower().strip() in [
        "",
        "y",
    ]:
        SessionLocal = get_database_session_sync()
        # Check if vector extension is installed
        with SessionLocal() as session:
            query = text("SELECT * FROM pg_extension WHERE extname = 'vector'")
            result = session.execute(query).fetchone()
            if result is None:
                try:
                    session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                except Exception as e:
                    raise Exception(
                        f"""\
Failed to install pgvector extension: {e}
1. Install `pgvector` on your device: https://github.com/pgvector/pgvector
2. Enable the `vector` extension to the ragdaemon database: 
https://github.com/pgvector/pgvector-python?tab=readme-ov-file#sqlalchemy 
"""
                    )
        engine = get_database_engine_sync()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        print("PGDB migrated successfully.")
