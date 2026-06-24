"""Error tracking (Sentry) initialization.

A no-op unless ``SENTRY_DSN`` is configured, so it is safe to call from both the
API process and the arq worker on startup. Import failures of the optional
``sentry_sdk`` dependency are swallowed (the app must still boot without it).
"""

from loguru import logger

from app.config import settings

_initialized = False


def init_sentry(component: str) -> None:
    """Initialize Sentry for a process. `component` tags events (api | worker)."""
    global _initialized
    if _initialized or not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        )
        sentry_sdk.set_tag("component", component)
        _initialized = True
        logger.info(f"Sentry initialized for {component} (env={settings.sentry_environment})")
    except Exception as e:  # never block startup on telemetry
        logger.warning(f"Sentry init skipped: {e}")
