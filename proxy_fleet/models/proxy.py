"""
Data models for proxy server configuration and status tracking.
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator


class ProxyProtocol(str, Enum):
    """Supported proxy protocols."""
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class ProxyStatus(str, Enum):
    """Proxy server status states."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    TESTING = "testing"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class ProxyServer(BaseModel):
    """Proxy server configuration and status model."""
    
    host: str = Field(..., description="Proxy server hostname or IP address")
    port: int = Field(..., ge=1, le=65535, description="Proxy server port")
    protocol: ProxyProtocol = Field(default=ProxyProtocol.HTTP, description="Proxy protocol")
    username: Optional[str] = Field(default=None, description="Authentication username")
    password: Optional[str] = Field(default=None, description="Authentication password")
    
    # Status tracking
    status: ProxyStatus = Field(default=ProxyStatus.UNKNOWN, description="Current proxy status")
    last_check: Optional[datetime] = Field(default=None, description="Last health check timestamp")
    last_success: Optional[datetime] = Field(default=None, description="Last successful request timestamp")
    last_failure: Optional[datetime] = Field(default=None, description="Last failure timestamp")
    
    # Performance metrics
    success_count: int = Field(default=0, ge=0, description="Total successful requests")
    failure_count: int = Field(default=0, ge=0, description="Total failed requests")
    recent_failures: int = Field(default=0, ge=0, description="Failures in recent time window")
    average_response_time: Optional[float] = Field(default=None, ge=0, description="Average response time in seconds")
    
    # Configuration
    max_recent_failures: int = Field(default=5, ge=1, description="Max failures before marking unhealthy")
    failure_window_minutes: int = Field(default=1, ge=1, description="Time window for recent failure tracking")
    timeout_seconds: int = Field(default=30, ge=1, description="Request timeout in seconds")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    @validator('host')
    def validate_host(cls, v):
        """Validate hostname/IP address."""
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()
    
    @property
    def url(self) -> str:
        """Get the full proxy URL."""
        if self.username and self.password:
            return f"{self.protocol.value}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol.value}://{self.host}:{self.port}"
    
    @property
    def is_healthy(self) -> bool:
        """Check if proxy is currently healthy."""
        return self.status == ProxyStatus.HEALTHY
    
    @property
    def is_available(self) -> bool:
        """Check if proxy is available for use."""
        return self.status in [ProxyStatus.HEALTHY, ProxyStatus.UNKNOWN]
    
    def reset_recent_failures(self):
        """Reset recent failure count."""
        self.recent_failures = 0
    
    def record_success(self, response_time: Optional[float] = None):
        """Record a successful request."""
        now = datetime.now()
        self.last_success = now
        self.last_check = now
        self.success_count += 1
        self.status = ProxyStatus.HEALTHY
        
        if response_time is not None:
            if self.average_response_time is None:
                self.average_response_time = response_time
            else:
                # Simple moving average
                self.average_response_time = (self.average_response_time + response_time) / 2
    
    def record_failure(self):
        """Record a failed request."""
        now = datetime.now()
        self.last_failure = now
        self.last_check = now
        self.failure_count += 1
        self.recent_failures += 1
        
        # Mark unhealthy if too many recent failures
        if self.recent_failures >= self.max_recent_failures:
            self.status = ProxyStatus.UNHEALTHY
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = self.dict()
        # Convert datetime objects to ISO strings for JSON serialization
        for field in ['last_check', 'last_success', 'last_failure']:
            if field in data and data[field]:
                data[field] = data[field].isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProxyServer":
        """Create instance from dictionary."""
        # Convert datetime strings back to datetime objects
        for field in ['last_check', 'last_success', 'last_failure']:
            if field in data and data[field]:
                if isinstance(data[field], str):
                    data[field] = datetime.fromisoformat(data[field])
        return cls(**data)
