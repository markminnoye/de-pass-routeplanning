"""Central configuration. Fails fast on missing/invalid values; nothing is hardcoded.

Sources, in order: environment variables, then a `.env` file in the repo root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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
    traffic: Traffic = "historical"
    dwell_base_s: int = 30
    dwell_per_student_s: int = 10
    cache_dir: Path | None = DEFAULT_CACHE_DIR
    reference_date: date | None = None  # weekday used for departAt; None = next weekday
    lead_time_min: int = 60  # departAt = target_arrival - lead_time (only for traffic profile)

    def reference_arrival(self, target_arrival: time) -> datetime:
        """Timezone-aware datetime of the school arrival on the reference weekday."""
        day = self.reference_date or next_weekday(datetime.now(BRUSSELS).date())
        if day.weekday() >= 5:
            raise ConfigError(f"referentiedatum {day} valt in het weekend")
        return datetime.combine(day, target_arrival, tzinfo=BRUSSELS)

    def reference_departure(self, target_arrival: time) -> datetime:
        return self.reference_arrival(target_arrival) - timedelta(minutes=self.lead_time_min)


def next_weekday(today: date) -> date:
    day = today + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def load_settings(env_path: Path = DEFAULT_ENV_PATH, **overrides) -> Settings:
    env = {**read_env_file(env_path), **os.environ}
    traffic = env.get("BUSROUTES_TRAFFIC", "historical")
    if traffic not in ("historical", "live"):
        raise ConfigError(f"BUSROUTES_TRAFFIC moet 'historical' of 'live' zijn, niet '{traffic}'")
    ref = env.get("BUSROUTES_REFERENCE_DATE")
    try:
        reference_date = date.fromisoformat(ref) if ref else None
    except ValueError as exc:
        raise ConfigError(f"BUSROUTES_REFERENCE_DATE ongeldig: {ref}") from exc
    values = {
        "api_key": load_key(env_path),
        "traffic": traffic,
        "dwell_base_s": int(env.get("BUSROUTES_DWELL_BASE_S", 30)),
        "dwell_per_student_s": int(env.get("BUSROUTES_DWELL_PER_STUDENT_S", 10)),
        "reference_date": reference_date,
    }
    values.update(overrides)
    return Settings(**values)
