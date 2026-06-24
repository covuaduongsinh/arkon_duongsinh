"""
Application configuration loaded from environment variables.
"""


from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Infrastructure settings loaded from .env or environment.
    
    AI provider settings (embedding, LLM, vision) are NOT here —
    they are stored in the database and managed via Admin Portal.
    See: app/services/config_service.py and app/ai/registry.py
    """

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://arkon:arkon_secret@localhost:5432/arkon",
        description="PostgreSQL connection string (async)",
    )

    # --- Auth ---
    secret_key: str = Field(
        default="change-me-to-a-random-secret-string",
        description="Secret key for signing JWT tokens and encrypting config values",
    )
    default_admin_email: str = Field(
        default="admin@arkon.local",
        description="Email for the initial admin account (created on first startup)",
    )
    default_admin_password: str = Field(
        default="admin123",
        description="Password for the initial admin account",
    )
    mcp_token_pepper: str = Field(
        default="change-me-to-a-random-pepper",
        description=(
            "HMAC pepper used to hash MCP bearer tokens at rest. "
            "Rotating this invalidates every existing token — set once and keep stable."
        ),
    )
    require_secure_secrets: bool = Field(
        default=False,
        description=(
            "Opt-in hardening. When False (default), placeholder SECRET_KEY / "
            "MCP_TOKEN_PEPPER / DEFAULT_ADMIN_PASSWORD only log a loud warning so "
            "existing deployments keep booting. Set True (after setting real "
            "secrets) to make the app REFUSE to start with insecure defaults."
        ),
    )

    # --- MinIO ---
    minio_endpoint: str = Field(default="localhost:9000")
    minio_public_endpoint: str = Field(
        default="",
        description="Public-facing MinIO address used in presigned URLs (browser-accessible). "
                    "Defaults to minio_endpoint if not set. "
                    "In Docker: set to 'localhost:9000' so presigned URLs work from the browser.",
    )
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin123")
    minio_bucket: str = Field(default="arkon-files")
    minio_secure: bool = Field(default=False)
    minio_presign_expiry_hours: int = Field(default=24)

    # --- Error tracking (Sentry) ---
    sentry_dsn: str = Field(
        default="",
        description="Sentry DSN for backend + worker error tracking. Empty disables Sentry.",
    )
    sentry_environment: str = Field(
        default="production",
        description="Environment tag reported to Sentry (e.g. production, staging, dev).",
    )
    sentry_traces_sample_rate: float = Field(
        default=0.0,
        description="Sentry performance tracing sample rate (0.0–1.0). 0 disables tracing.",
    )

    # --- CORS ---
    cors_origins: str = Field(default="*")

    # --- Portal ---
    portal_base_url: str = Field(
        default="",
        description="Public base URL of the admin/portal frontend (e.g. "
                    "'https://kb.acme.local'). Used to build clickable links to "
                    "source documents in MCP search results. Empty → relative "
                    "'/wiki/source/<id>' paths.",
    )

    # --- Student / external self-signup (Roadmap A) ---
    enable_student_signup: bool = Field(
        default=False,
        description="Master switch for the public student self-signup endpoint. "
                    "Keep False until you intend to expose a public registration surface.",
    )
    student_signup_auto_activate: bool = Field(
        default=False,
        description="If True, self-registered students are active immediately. "
                    "If False (default), they stay inactive until an admin approves "
                    "(or email verification succeeds) — safer.",
    )
    student_department_name: str = Field(
        default="Students",
        description="Department new self-signup students are placed in (auto-created).",
    )
    signup_rate_limit_per_hour: int = Field(
        default=5,
        description="Max self-signup attempts per client IP per hour.",
    )

    # --- Redis (arq worker queue) ---
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="")
    redis_db: int = Field(default=0)
    worker_max_jobs: int = Field(default=3, description="Max concurrent ingestion jobs")
    worker_job_timeout: int = Field(default=1800, description="Job timeout in seconds")

    # --- MRP Pipeline ---
    mrp_auto_approve_plan: bool = Field(
        default=False,
        description="If True, compilation plans are auto-approved without human review",
    )
    mrp_multipass_writer_enabled: bool = Field(
        default=True,
        description="If True, REFINE uses multi-pass writer when source > budget; if False, falls back to single-pass with tiered selection",
    )
    auto_approve_extraction_threshold_tokens: int = Field(
        default=200_000,
        description="Doc <= this many tokens after extraction auto-proceeds. Larger docs pause at status='awaiting_approval' for human review.",
    )
    extraction_approval_ttl_hours: int = Field(
        default=24,
        description="Orphan sources stuck in 'awaiting_approval' longer than this are auto-deleted by cleanup cron.",
    )
    max_auto_recover_attempts: int = Field(
        default=3,
        description="Max times a source may be auto-flipped from stuck 'processing' back to 'error' before the retry API refuses further attempts. Prevents token-burning loops when the failure is deterministic (bad provider key, malformed file).",
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list."""
        value = self.cors_origins.strip()
        if value == "*":
            return ["*"]
        return [o.strip() for o in value.split(",") if o.strip()]


settings = Settings()
