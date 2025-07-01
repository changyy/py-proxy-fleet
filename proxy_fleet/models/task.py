"""
Data models for HTTP tasks and results.
"""

from enum import Enum
from typing import Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator


class TaskStatus(str, Enum):
    """HTTP task status states."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class HttpMethod(str, Enum):
    """Supported HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class HttpTask(BaseModel):
    """HTTP request task configuration."""
    
    # Basic request info
    url: str = Field(..., description="Target URL for the HTTP request")
    method: HttpMethod = Field(default=HttpMethod.GET, description="HTTP method")
    headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="Request headers")
    data: Optional[Union[str, bytes, Dict[str, Any]]] = Field(default=None, description="Request body data")
    params: Optional[Dict[str, str]] = Field(default_factory=dict, description="URL parameters")
    
    # Task configuration
    task_id: Optional[str] = Field(default=None, description="Unique task identifier")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, ge=0, description="Delay between retries in seconds")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now, description="Task creation timestamp")
    priority: int = Field(default=5, ge=1, le=10, description="Task priority (1=highest, 10=lowest)")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    @validator('url')
    def validate_url(cls, v):
        """Validate URL format."""
        if not v or not v.strip():
            raise ValueError("URL cannot be empty")
        
        url = v.strip()
        if not url.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        
        return url
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.dict()


class TaskResult(BaseModel):
    """HTTP task execution result."""
    
    # Task reference
    task_id: Optional[str] = Field(default=None, description="Original task identifier")
    url: str = Field(..., description="Request URL")
    method: HttpMethod = Field(..., description="HTTP method used")
    
    # Execution details
    status: TaskStatus = Field(..., description="Task execution status")
    proxy_used: Optional[str] = Field(default=None, description="Proxy server used (host:port)")
    attempt_count: int = Field(default=1, ge=1, description="Number of attempts made")
    
    # Timing information
    started_at: datetime = Field(..., description="Task start timestamp")
    completed_at: Optional[datetime] = Field(default=None, description="Task completion timestamp")
    response_time: Optional[float] = Field(default=None, ge=0, description="Response time in seconds")
    
    # Response details
    status_code: Optional[int] = Field(default=None, description="HTTP response status code")
    response_headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="Response headers")
    response_data: Optional[Union[str, bytes]] = Field(default=None, description="Response body")
    response_size: Optional[int] = Field(default=None, ge=0, description="Response size in bytes")
    
    # Error information
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    error_type: Optional[str] = Field(default=None, description="Error type/category")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    @property
    def is_success(self) -> bool:
        """Check if task was successful."""
        return self.status == TaskStatus.SUCCESS
    
    @property
    def duration(self) -> Optional[float]:
        """Get task duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def mark_completed(self, status: TaskStatus, error_message: Optional[str] = None):
        """Mark task as completed with given status."""
        self.completed_at = datetime.now()
        self.status = status
        if error_message:
            self.error_message = error_message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.dict()
    
    @classmethod
    def from_task(cls, task: HttpTask, status: TaskStatus = TaskStatus.PENDING) -> "TaskResult":
        """Create TaskResult from HttpTask."""
        return cls(
            task_id=task.task_id,
            url=task.url,
            method=task.method,
            status=status,
            started_at=datetime.now()
        )
