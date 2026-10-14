import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "postgresql://monitor:monitor@localhost:5432/monitor")
    )
    mqtt_host: str = field(default_factory=lambda: _env("MQTT_HOST", "localhost"))
    mqtt_port: int = field(default_factory=lambda: int(_env("MQTT_PORT", "1883")))
    mqtt_user: str | None = field(default_factory=lambda: _env("MQTT_USER") or None)
    mqtt_password: str | None = field(default_factory=lambda: _env("MQTT_PASSWORD") or None)
    backfill_days: float = field(default_factory=lambda: float(_env("BACKFILL_DAYS", "3")))
    static_dir: str | None = field(default_factory=lambda: _env("STATIC_DIR") or None)
    vapid_private_key: str | None = field(default_factory=lambda: _env("VAPID_PRIVATE_KEY") or None)
    vapid_public_key: str | None = field(default_factory=lambda: _env("VAPID_PUBLIC_KEY") or None)
    vapid_subject: str = field(default_factory=lambda: _env("VAPID_SUBJECT", "https://vue.umut-aslan.dev"))
    fault_cooldown_s: float = field(default_factory=lambda: float(_env("FAULT_COOLDOWN_S", "120")))
