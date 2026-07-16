import os
import subprocess
from datetime import date

import pytest
from app.auth import create_session_cookie
from app.config import settings
from app.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FIELD_NAME,
    UNSAFE_METHODS,
    create_csrf_tokens,
)
from app.database import Base, get_db
from app.main import app
from app.models import FuelEntry, Group, GroupSubscription, User, UserGroup, Vehicle
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite://")
_USE_POSTGRES = TEST_DATABASE_URL.startswith("postgresql")


def _run_alembic_upgrade() -> None:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        env={
            **os.environ,
            "DATABASE_URL": TEST_DATABASE_URL,
            "ENV": "development",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join(
            part for part in (result.stderr, result.stdout) if part
        ).strip()
        raise RuntimeError(detail or "alembic upgrade head failed")


if _USE_POSTGRES:
    test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
else:
    test_engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _set_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


class CsrfAsyncClient(AsyncClient):
    async def request(self, method: str, url, **kwargs):
        if method.upper() in UNSAFE_METHODS:
            kwargs, signed_token = _with_csrf(kwargs)
            if signed_token is not None:
                self.cookies.delete(CSRF_COOKIE_NAME)
                self.cookies.set(CSRF_COOKIE_NAME, signed_token)
        return await super().request(method, url, **kwargs)


def _with_csrf(kwargs: dict) -> tuple[dict, str | None]:
    token, signed_token = create_csrf_tokens()
    data = kwargs.get("data")
    if isinstance(data, dict):
        data = {**data, CSRF_FIELD_NAME: token}
    elif isinstance(data, list):
        data = [*data, (CSRF_FIELD_NAME, token)]
    elif data is None:
        data = {CSRF_FIELD_NAME: token}
    else:
        return kwargs, None

    kwargs["data"] = data
    return kwargs, signed_token


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    if _USE_POSTGRES:
        _run_alembic_upgrade()
    else:
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
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with CsrfAsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_cookie(db):
    def _set(client, user_id: int, active_group_id: int | None = None) -> None:
        from app.services.sessions import create_user_session

        session_id = create_user_session(db, user_id)
        db.commit()
        cookie_value = create_session_cookie(
            user_id, active_group_id, session_id=session_id
        )
        client.cookies.set(settings.SESSION_COOKIE_NAME, cookie_value)

    return _set


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
def create_test_group(db, create_test_user):
    def _create(
        name: str = "Test Farm",
        invite_code: str = "FARM-TEST1",
        created_by: int | None = None,
    ):
        if created_by is None:
            created_by = create_test_user(
                email=f"owner-{invite_code.lower()}@test.com",
                name="Group Owner",
            ).id
        group = Group(name=name, invite_code=invite_code, created_by=created_by)
        db.add(group)
        db.commit()
        db.refresh(group)
        return group

    return _create


def ensure_group_subscription_tier(
    db, group_id: int, tier: str = "free", status: str = "active"
) -> GroupSubscription:
    sub = (
        db.query(GroupSubscription)
        .filter(GroupSubscription.group_id == group_id)
        .first()
    )
    if sub is None:
        sub = GroupSubscription(
            group_id=group_id,
            tier=tier,
            status=status,
        )
        db.add(sub)
    else:
        sub.tier = tier
        sub.status = status
    group = db.query(Group).filter(Group.id == group_id).one()
    group.subscription_tier = tier
    db.commit()
    db.refresh(sub)
    return sub


@pytest.fixture
def set_group_tier(db):
    def _set(group_id: int, tier: str = "pro") -> GroupSubscription:
        return ensure_group_subscription_tier(db, group_id, tier=tier)

    return _set


@pytest.fixture
def create_test_user_group(db):
    def _create(
        user_id: int,
        group_id: int,
        role: str = "contributor",
    ) -> UserGroup:
        ug = UserGroup(user_id=user_id, group_id=group_id, role=role)
        db.add(ug)
        db.commit()
        db.refresh(ug)
        return ug

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


@pytest.fixture
def create_test_fuel_entry(db):
    def _create(
        vehicle_id: int,
        group_id: int,
        user_id: int,
        fuel_amount_l: float = 50.0,
        usage_reading: float = 100.0,
        entry_date: date | None = None,
        notes: str | None = None,
    ) -> FuelEntry:
        if entry_date is None:
            entry_date = date.today()
        entry = FuelEntry(
            vehicle_id=vehicle_id,
            group_id=group_id,
            user_id=user_id,
            fuel_amount_l=fuel_amount_l,
            usage_reading=usage_reading,
            notes=notes,
            entry_date=entry_date,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    return _create


@pytest.fixture
def auth_group(
    client,
    create_test_user,
    create_test_group,
    create_test_user_group,
    auth_cookie,
):
    def _create(*, role: str = "admin"):
        return create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role=role,
        )

    return _create


def create_authenticated_group(
    client,
    create_test_user,
    create_test_group,
    create_test_user_group,
    auth_cookie,
    *,
    role: str = "admin",
):
    user = create_test_user()
    group = create_test_group(created_by=user.id)
    create_test_user_group(user.id, group.id, role=role)
    auth_cookie(client, user.id, group.id)
    return user, group
