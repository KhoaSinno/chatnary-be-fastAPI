from contextlib import contextmanager
import psycopg
from .settings import settings


DSN = f"host={settings.pg_host} port={settings.pg_port} dbname={settings.pg_db} user={settings.pg_user} password={settings.pg_password}"


@contextmanager
def get_conn():
    with psycopg.connect(DSN) as conn:
        yield conn