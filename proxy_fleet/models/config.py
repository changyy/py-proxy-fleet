"""
Configuration models for the proxy fleet.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FleetConfig(BaseModel):
    """Configuration for the proxy fleet manager."""

    # File paths
    proxy_file: str = Field(
        default="proxies.json", description="Path to proxy configuration file"
    )
    output_dir: str = Field(
        default="output", description="Directory for storing request results"
    )
    log_file: Optional[str] = Field(default=None, description="Log file path")

    # Health checking
    health_check_interval: int = Field(
        default=300, ge=30, description="Health check interval in seconds"
    )
    health_check_timeout: int = Field(
        default=10, ge=1, description="Health check timeout in seconds"
    )
    health_check_urls: List[str] = Field(
        default_factory=lambda: ["https://ipinfo.io/json", "https://www.google.com"],
        description="URLs for health checking proxies",
    )

    # Concurrency settings
    max_concurrent_requests: int = Field(
        default=20, ge=1, description="Maximum concurrent requests"
    )
    max_concurrent_health_checks: int = Field(
        default=10, ge=1, description="Maximum concurrent health checks"
    )

    # Failure handling
    max_recent_failures: int = Field(
        default=5, ge=1, description="Max failures before marking proxy unhealthy"
    )
    failure_window_minutes: int = Field(
        default=1, ge=1, description="Time window for recent failure tracking"
    )
    unhealthy_retry_interval: int = Field(
        default=600,
        ge=60,
        description="Retry interval for unhealthy proxies in seconds",
    )

    # Request settings
    default_timeout: int = Field(
        default=30, ge=1, description="Default request timeout in seconds"
    )
    default_retries: int = Field(default=3, ge=0, description="Default retry attempts")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        description="Default User-Agent header",
    )

    # Output settings
    save_response_data: bool = Field(
        default=True, description="Whether to save response data to files"
    )
    max_response_size: int = Field(
        default=10485760, ge=1024, description="Maximum response size to save (bytes)"
    )
    compress_output: bool = Field(
        default=False, description="Whether to compress output files"
    )

    model_config = ConfigDict()

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v):
        """Ensure output directory exists."""
        output_path = Path(v)
        output_path.mkdir(parents=True, exist_ok=True)
        return str(output_path)

    @field_validator("health_check_urls")
    @classmethod
    def validate_health_check_urls(cls, v):
        """Validate health check URLs."""
        if not v:
            raise ValueError("At least one health check URL is required")

        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"Invalid health check URL: {url}")

        return v

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.dict()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FleetConfig":
        """Create instance from dictionary."""
        return cls(**data)

    @classmethod
    def load_from_file(cls, file_path: str) -> "FleetConfig":
        """Load configuration from JSON file."""
        import json

        config_path = Path(file_path)
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        else:
            # Return default config and save it
            config = cls()
            config.save_to_file(file_path)
            return config

    def save_to_file(self, file_path: str):
        """Save configuration to JSON file."""
        import json

        config_path = Path(file_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
