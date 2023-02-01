from pydantic import BaseModel


class ServiceConfig(BaseModel):
    name: str
    down_time_seconds: int
