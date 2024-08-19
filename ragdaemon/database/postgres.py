import os
from functools import cache
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker, class_mapper

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
    # embedding: Mapped[List[Float]]
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
        engine = get_database_engine_sync()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        print("PGDB migrated successfully.")
