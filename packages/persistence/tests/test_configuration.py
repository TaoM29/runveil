import pytest
from runveil_persistence.database import create_engine, database_url


@pytest.mark.parametrize(
    "value",
    ["", "invalid-secret", "sqlite:///test.db", "postgresql+psycopg://user:secret@host:invalid/db"],
)
def test_invalid_url_is_rejected_without_exposing_input(value: str) -> None:
    with pytest.raises(ValueError) as error:
        database_url(value)
    assert "secret" not in str(error.value)


def test_database_url_requires_explicit_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="must be set"):
        database_url()


@pytest.mark.asyncio
async def test_rds_tls_options_reach_psycopg_without_connecting() -> None:
    url = database_url(
        "postgresql+psycopg://runtime:fake%40password@db.example.invalid:5432/runveil"
        "?sslmode=verify-full&sslrootcert=/run/certs/rds.pem"
    )
    engine = create_engine(url)
    try:
        _, options = engine.dialect.create_connect_args(engine.url)
        assert options["sslmode"] == "verify-full"
        assert options["sslrootcert"] == "/run/certs/rds.pem"
        assert options["host"] == "db.example.invalid"
        assert options["password"] == "fake@password"
    finally:
        await engine.dispose()
