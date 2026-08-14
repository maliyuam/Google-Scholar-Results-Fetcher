"""Tests for API-key loading. Previously this module had no tests at all."""

import pytest

from scholar_fetcher.config import get_api_key, scholar_enabled, _load_dotenv


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Never read, and never leak into, the developer's real key."""
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_ENABLED", raising=False)
    monkeypatch.delenv("OTHER_KEY", raising=False)


def _env_file(tmp_path, text, encoding="utf-8"):
    path = tmp_path / ".env"
    path.write_text(text, encoding=encoding)
    return str(path)


def test_reads_a_plain_key(tmp_path):
    assert get_api_key(_env_file(tmp_path, "SERPAPI_API_KEY=abc123\n")) == "abc123"


def test_environment_wins_over_the_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "from-env")
    assert get_api_key(_env_file(tmp_path, "SERPAPI_API_KEY=from-file\n")) == "from-env"


def test_quoted_values_are_unquoted(tmp_path):
    assert get_api_key(_env_file(tmp_path, 'SERPAPI_API_KEY="abc123"\n')) == "abc123"


def test_utf8_bom_does_not_hide_the_key(tmp_path):
    """A BOM became part of the first key's name, so the key read as missing."""
    assert get_api_key(_env_file(tmp_path, "SERPAPI_API_KEY=abc123\n", "utf-8-sig")) == "abc123"


def test_export_prefix_is_understood(tmp_path):
    """`export FOO=bar` is a standard .env idiom; the key parsed as 'export FOO'."""
    assert get_api_key(_env_file(tmp_path, "export SERPAPI_API_KEY=abc123\n")) == "abc123"


def test_inline_comment_is_not_part_of_the_key(tmp_path):
    assert get_api_key(_env_file(tmp_path, "SERPAPI_API_KEY=abc123  # my key\n")) == "abc123"


def test_hash_inside_a_quoted_value_is_kept(tmp_path):
    assert get_api_key(_env_file(tmp_path, 'SERPAPI_API_KEY="ab#c123"\n')) == "ab#c123"


def test_line_starting_with_equals_does_not_raise(tmp_path):
    """An empty variable name made os.environ.setdefault raise ValueError, which
    the GUI then showed as if it were the friendly missing-key message."""
    path = _env_file(tmp_path, "=oops\nSERPAPI_API_KEY=abc123\n")
    assert get_api_key(path) == "abc123"


def test_missing_key_raises_an_actionable_error(tmp_path):
    with pytest.raises(ValueError, match="SERPAPI_API_KEY"):
        get_api_key(_env_file(tmp_path, "# nothing here\n"))


def test_unedited_placeholder_is_rejected(tmp_path):
    """The placeholder shipped in .env.example passed the non-empty check, so an
    unedited .env produced an enabled form and a misleading 'No results found'."""
    path = _env_file(tmp_path, "SERPAPI_API_KEY=your_serpapi_api_key_here\n")
    with pytest.raises(ValueError, match="placeholder"):
        get_api_key(path)


def test_whitespace_only_key_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        get_api_key(_env_file(tmp_path, "SERPAPI_API_KEY=   \n"))


def test_missing_dotenv_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "abc123")
    assert get_api_key(str(tmp_path / "does-not-exist")) == "abc123"


# --- the Scholar spend guard -----------------------------------------------


def test_scholar_is_off_by_default(tmp_path):
    """Off unless switched on. A hosted app with a key would otherwise let every
    visitor spend the owner's paid quota."""
    assert scholar_enabled(_env_file(tmp_path, "SERPAPI_API_KEY=abc123\n")) is False


def test_scholar_stays_off_even_when_a_valid_key_is_present(tmp_path):
    """Having a key is not consent to expose the source publicly."""
    path = _env_file(tmp_path, "SERPAPI_API_KEY=a-real-looking-key\n")
    assert get_api_key(path) == "a-real-looking-key"
    assert scholar_enabled(path) is False


def test_scholar_can_be_switched_on_from_the_dotenv(tmp_path):
    path = _env_file(tmp_path, "SERPAPI_API_KEY=abc123\nSCHOLAR_ENABLED=1\n")
    assert scholar_enabled(path) is True


def test_scholar_accepts_the_usual_spellings_of_on(tmp_path, monkeypatch):
    for value in ("1", "true", "TRUE", "yes", "on", " On "):
        monkeypatch.setenv("SCHOLAR_ENABLED", value)
        assert scholar_enabled(str(tmp_path / "none")) is True, value


def test_scholar_rejects_anything_else(tmp_path, monkeypatch):
    for value in ("0", "false", "no", "off", "", "maybe"):
        monkeypatch.setenv("SCHOLAR_ENABLED", value)
        assert scholar_enabled(str(tmp_path / "none")) is False, value


def test_loader_ignores_blank_and_comment_lines(tmp_path):
    _load_dotenv.__doc__  # module-level import smoke check
    text = "\n# comment\n\nSERPAPI_API_KEY=abc123\nnot-a-pair\n"
    assert get_api_key(_env_file(tmp_path, text)) == "abc123"
