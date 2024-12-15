from pydantic import BaseModel, Field


class UvicornConfig(BaseModel):
    """Configuration for Uvicorn server."""
    host: str = Field(default="127.0.0.1", description="The host to run the server on")    
    port: int = Field(default=8000, description="Port to bind to")
    reload: bool = Field(default=True, description="Enable auto-reload")
    workers: int = Field(default=1, description="Number of worker processes")
    log_level: str = Field(default="info", description="Logging level")
