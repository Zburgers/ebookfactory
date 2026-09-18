"""Small database boundary used by health and readiness checks."""

from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class DatabaseCheck:
    """Sanitized result of a database connectivity check."""

    status: str
    reason: str | None = None


class Database:
    """Lazily manages the SQLAlchemy engine for one configured URL."""

    def __init__(self, url: str | None) -> None:
        self.url = url
        self._engine: Engine | None = None

    def check(self) -> DatabaseCheck:
        """Run a minimal `SELECT 1` check without exposing connection details."""

        if not self.url:
            return DatabaseCheck("missing_configuration", "DATABASE_URL is not configured")
        try:
            if self._engine is None:
                self._engine = create_engine(self.url, pool_pre_ping=True)
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - sanitize all driver failures
            return DatabaseCheck("unavailable", type(exc).__name__)
        return DatabaseCheck("ok")

    def session(self) -> Session:
        """Open a short-lived ORM session for one API transaction."""

        if not self.url:
            raise RuntimeError("DATABASE_URL is not configured")
        if self._engine is None:
            self._engine = create_engine(self.url, pool_pre_ping=True)
        return sessionmaker(self._engine, expire_on_commit=False)()

    def close(self) -> None:
        """Dispose the connection pool if a readiness check created one."""

        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
