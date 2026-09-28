import pytest
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app
from app.routes.items import get_db


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def client(db_path):
    def _get_db_override():
        conn = get_connection(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
