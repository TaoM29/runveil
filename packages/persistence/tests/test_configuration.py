import pytest
from runveil_persistence.database import database_url


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
