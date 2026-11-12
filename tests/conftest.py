"""Test setup: a separate test database, a fake browser (client), and ready-made logins."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  (loads all tables)
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password

# 1. Use billing_test, never the real billing database
real_url = get_settings().database_url
base_url, _, db_name = real_url.rpartition("/")
TEST_DATABASE_URL = f"{base_url}/{db_name}_test"
assert TEST_DATABASE_URL.endswith("_test"), "Safety lock: tests must use a *_test database"

engine = create_engine(TEST_DATABASE_URL)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# 2. Create all tables once, before any test runs
@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# 3. Empty every table after each test, so tests don't affect each other
@pytest.fixture(autouse=True)
def clean_tables():
    yield
    table_names = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


# 4. A fake browser that calls our API, connected to the test database
@pytest.fixture
def client():
    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# 5. Ready-made logins
def _login_headers(client: TestClient, email: str, role: str) -> dict:
    session = TestingSession()
    session.add(User(email=email, full_name=role.title(), role=role, hashed_password=hash_password("Password123")))
    session.commit()
    session.close()

    response = client.post("/auth/login", json={"email": email, "password": "Password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client):
    return _login_headers(client, "admin@test.com", "admin")


@pytest.fixture
def viewer_headers(client):
    return _login_headers(client, "viewer@test.com", "viewer")