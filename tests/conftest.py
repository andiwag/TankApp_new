import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Group, User, Vehicle

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clean_tables(db):
    yield
    db.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def create_test_user(db):
    def _create(
        email: str = "test@example.com",
        name: str = "Test User",
        password_hash: str = "hashed_pw",
        password: str | None = None,
    ):
        if password is not None:
            from app.auth import hash_password
            password_hash = hash_password(password)
        user = User(email=email, name=name, password_hash=password_hash)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _create


@pytest.fixture
def create_test_group(db):
    def _create(
        name: str = "Test Farm",
        invite_code: str = "FARM-TEST1",
        created_by: int = 1,
    ):
        group = Group(name=name, invite_code=invite_code, created_by=created_by)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    return _create


@pytest.fixture
def create_test_vehicle(db):
    def _create(
        group_id: int = 1,
        name: str = "Test Tractor",
        vtype: str = "tractor",
        fuel_type: str = "diesel",
    ):
        vehicle = Vehicle(
            group_id=group_id,
            name=name,
            vtype=vtype,
            fuel_type=fuel_type,
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        return vehicle

    return _create
