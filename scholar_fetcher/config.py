"""Configuration and API-key loading.

The notebook read the key from google.colab.userdata, which only works in Colab.
Here we read SERPAPI_API_KEY from the environment, falling back to a local .env
file so the tool runs anywhere. No key is ever hardcoded or committed.
"""

import os
from pathlib import Path

# SerpAPI's Google Scholar engine returns at most 20 results per page; more than
# that is fetched by paginating with the `start` offset, not by raising `num`.
# (The old README's "200 per page" was incorrect.)
PAGE_SIZE = 20
DEFAULT_SLEEP = 2      # seconds between paged calls, to respect rate limits
DEFAULT_RETRIES = 3    # per-page retry attempts on transient failure

# Values that are obviously the unedited example, not a key. Checked because a
# non-empty placeholder used to pass validation and then fail as "no results".
_PLACEHOLDERS = {
    "your_serpapi_api_key_here",
    "your_serpapi_api_key",
    "your_api_key_here",
    "your_key_here",
    "changeme",
}


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines) so we avoid an extra dependency.

    Existing environment variables win; blank lines, comments, and lines without
    '=' are ignored. Handles the idioms a real .env file tends to contain: a
    UTF-8 BOM, an `export ` prefix, quoted values, and trailing ` # comments`
    (kept verbatim inside quotes, since a key may legitimately contain '#').
    """
    if not path.is_file():
        return

    # utf-8-sig: a BOM would otherwise become part of the first key's name, and
    # the key would read as missing while sitting plainly in the file.
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        name, _, value = line.partition("=")
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        if not name:
            continue  # '=value' would make setdefault raise ValueError

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()

        os.environ.setdefault(name, value)


def get_api_key(dotenv_path: str | None = None) -> str:
    """Return the SerpAPI key, loading a .env file if present.

    Looks for .env in the given path, else next to the project root.
    Raises ValueError with an actionable message if the key is missing or is
    still the placeholder from .env.example.
    """
    env_file = Path(dotenv_path) if dotenv_path else Path(__file__).resolve().parent.parent / ".env"
    _load_dotenv(env_file)

    key = (os.getenv("SERPAPI_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "SERPAPI_API_KEY is not set. Add it to your environment or to a .env "
            "file (see .env.example), e.g.  SERPAPI_API_KEY=your_key_here"
        )
    if key.casefold() in _PLACEHOLDERS:
        raise ValueError(
            f"SERPAPI_API_KEY is still the placeholder from .env.example. Edit "
            f"{env_file} and paste your own key from https://serpapi.com/manage-api-key"
        )
    return key
