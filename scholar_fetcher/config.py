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


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines) so we avoid an extra dependency.

    Existing environment variables win; lines without '=' or starting with '#'
    are ignored. Surrounding quotes on the value are stripped.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_api_key(dotenv_path: str | None = None) -> str:
    """Return the SerpAPI key, loading a .env file if present.

    Looks for .env in the given path, else next to the project root.
    Raises ValueError with an actionable message if the key is missing.
    """
    env_file = Path(dotenv_path) if dotenv_path else Path(__file__).resolve().parent.parent / ".env"
    _load_dotenv(env_file)

    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        raise ValueError(
            "SERPAPI_API_KEY is not set. Add it to your environment or to a .env "
            "file (see .env.example), e.g.  SERPAPI_API_KEY=your_key_here"
        )
    return key
