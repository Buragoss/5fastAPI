from pydantic import BaseModel, Field
from typing import Optional, Literal, List

# --- Запросы ---
class SessionCreate(BaseModel):
    variant_id: int = Field(..., ge=1, le=24, description="Номер варианта ЛР1 (1-24)")

class SessionEnd(BaseModel):
    status: Literal["completed", "error"] = "completed"

class SensorReading(BaseModel):
    sensor_type: str = Field(..., min_length=1, max_length=50, description="Тип сенсора (ir_0, altitude, battery_soc и т.д.)")
    value: float
    unit: str = Field("", max_length=20, description="Единица измерения")

class ActuatorCommand(BaseModel):
    actuator_type: str = Field(..., min_length=1, max_length=50, description="Тип актуатора (motor_left, thrust, gripper и т.д.)")
    command: float
    status: str = Field("sent", max_length=20)

class EventLog(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=50)
    severity: Literal["info", "warning", "error"]
    message: str = Field(..., min_length=1, max_length=500)

class SessionResponse(BaseModel):
    id: int
    variant_id: int
    started_at: str
    ended_at: Optional[str]
    status: str

class SensorStatsResponse(BaseModel):
    count: int
    avg: Optional[float]
    min: Optional[float]
    max: Optional[float]

class EventResponse(BaseModel):
    id: int
    session_id: int
    timestamp: str
    event_type: str
    severity: str
    message: str

class SensorReadingResponse(BaseModel):
    id: int
    sensor_type: str
    timestamp: str
    value: float
    unit: Optional[str]

class ActuatorCommandResponse(BaseModel):
    id: int
    actuator_type: str
    timestamp: str
    command: float
    status: Optional[str]