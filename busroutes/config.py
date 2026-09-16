"""Central configuration. Fails fast on missing/invalid values; nothing is hardcoded.

Sources, in order: environment variables, then a `.env` file in the repo root.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from busroutes.ordering import OrderingStrategy
from busroutes.tomtom import Traffic

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "tomtom"
BRUSSELS = ZoneInfo("Europe/Brussels")


class ConfigError(RuntimeError):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_key(env_path: Path = DEFAULT_ENV_PATH) -> str:
    """TOMTOM_API_KEY from the environment or .env. Raises ConfigError if missing."""
    key = os.environ.get("TOMTOM_API_KEY", "").strip() or read_env_file(env_path).get(
        "TOMTOM_API_KEY", ""
    )
    if not key:
        raise ConfigError(
            "TOMTOM_API_KEY ontbreekt. Kopieer .env.example naar .env en vul de key in."
        )
    return key


@dataclass(frozen=True)
class Settings:
    api_key: str
    reference_date: date  # the school day departAt is anchored to; never "today"
    traffic: Traffic = "historical"
    ordering: OrderingStrategy = "matrix"
    dwell_base_s: int = 30
    dwell_per_student_s: int = 10
    cache_dir: Path | None = DEFAULT_CACHE_DIR
    lead_time_min: int = 60  # departAt = target_arrival - lead_time (only for traffic profile)
    data_dir: Path = REPO_ROOT / "docs" / "samples"

    def reference_arrival(self, target_arrival: time) -> datetime:
        """Timezone-aware datetime of the school arrival on the reference weekday."""
        if self.reference_date.weekday() >= 5:
            raise ConfigError(f"referentiedatum {self.reference_date} valt in het weekend")
        return datetime.combine(self.reference_date, target_arrival, tzinfo=BRUSSELS)

    def reference_departure(self, target_arrival: time) -> datetime:
        return self.reference_arrival(target_arrival) - timedelta(minutes=self.lead_time_min)


def next_weekday(today: date) -> date:
    day = today + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def resolve_data_dir(
    cli_data: Path | None = None,
    cli_samples: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """`--data` wins, then `--samples`, then BUSROUTES_DATA_DIR, then docs/samples."""
    if cli_data is not None:
        return Path(cli_data)
    if cli_samples is not None:
        return Path(cli_samples)
    source = os.environ if env is None else env
    raw = str(source.get("BUSROUTES_DATA_DIR", "") or "").strip()
    if raw:
        return Path(raw)
    return REPO_ROOT / "docs" / "samples"


def load_settings(env_path: Path = DEFAULT_ENV_PATH, **overrides) -> Settings:
    env = {**read_env_file(env_path), **os.environ}
    traffic = env.get("BUSROUTES_TRAFFIC", "historical")
    if traffic not in ("historical", "live"):
        raise ConfigError(f"BUSROUTES_TRAFFIC moet 'historical' of 'live' zijn, niet '{traffic}'")
    ordering = env.get("BUSROUTES_ORDERING", "matrix")
    if ordering not in ("haversine", "matrix"):
        raise ConfigError(
            f"BUSROUTES_ORDERING moet 'haversine' of 'matrix' zijn, niet '{ordering}'"
        )
    cache_dir_raw = env.get("BUSROUTES_CACHE_DIR", "").strip()
    values = {
        "api_key": load_key(env_path),
        "reference_date": _reference_date(env.get("BUSROUTES_REFERENCE_DATE")),
        "traffic": traffic,
        "ordering": ordering,
        "dwell_base_s": int(env.get("BUSROUTES_DWELL_BASE_S", 30)),
        "dwell_per_student_s": int(env.get("BUSROUTES_DWELL_PER_STUDENT_S", 10)),
        "cache_dir": Path(cache_dir_raw) if cache_dir_raw else DEFAULT_CACHE_DIR,
        "data_dir": resolve_data_dir(env=env),
    }
    values.update(overrides)
    if values.get("reference_date") is None:
        raise ConfigError(
            "referentiedatum ontbreekt: zet BUSROUTES_REFERENCE_DATE=YYYY-MM-DD of geef "
            "--reference-date mee. Zonder vaste datum schuift departAt elke dag mee, "
            "vervalt de TomTom-cache dagelijks en zijn scenario's niet vergelijkbaar. "
            f"Voorstel: {next_weekday(datetime.now(BRUSSELS).date())}."
        )
    return Settings(**values)


def _reference_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigError(f"BUSROUTES_REFERENCE_DATE ongeldig: {raw}") from exc
