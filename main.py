from fastapi import FastAPI, HTTPException, Query
from typing import Optional, List
from models import (
    SessionCreate, SessionEnd, SessionResponse,
    SensorReading, ActuatorCommand, EventLog,
    SensorStatsResponse, EventResponse,
    SensorReadingResponse, ActuatorCommandResponse
)
from database import db

app = FastAPI(
    title="Robot Telemetry API",
    description="API для телеметрии",
    version="1.0.0"
)

# --- Lifecycle ---
@app.on_event("startup")
async def startup():
    db.connect()
    db.init_schema()

@app.on_event("shutdown")
async def shutdown():
    db.close()

# --- Health ---
@app.get("/health", tags=["Health"])
async def health():
    """Проверка работоспособности API."""
    return {"status": "ok"}

# --- Sessions ---
@app.post("/sessions", response_model=SessionResponse, status_code=201, tags=["Sessions"])
async def create_session(payload: SessionCreate):
    session_id = db.create_session(payload.variant_id)
    session = db.get_session(session_id)
    return session

@app.get("/sessions", response_model=List[SessionResponse], tags=["Sessions"])
async def list_sessions(limit: int = Query(100, ge=1, le=1000)):
    sessions = db.list_sessions(limit=limit)
    return sessions

@app.get("/sessions/{session_id}", response_model=SessionResponse, tags=["Sessions"])
async def get_session(session_id: int):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session

@app.post("/sessions/{session_id}/end", response_model=SessionResponse, tags=["Sessions"])
async def end_session(session_id: int, payload: SessionEnd):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if session["status"] != "running":
        raise HTTPException(status_code=400, detail="Session already ended")
     
    db.end_session(session_id, payload.status)
    return db.get_session(session_id)

@app.post("/sessions/{session_id}/sensors", status_code=201, tags=["Logging"])
async def log_sensor(session_id: int, payload: SensorReading):

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
     
    db.log_sensor(session_id, payload.sensor_type, payload.value, payload.unit)
    return {"message": "Sensor reading logged"}

@app.post("/sessions/{session_id}/actuators", status_code=201, tags=["Logging"])
async def log_actuator(session_id: int, payload: ActuatorCommand):

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
     
    db.log_command(session_id, payload.actuator_type, payload.command, payload.status)
    return {"message": "Actuator command logged"}

@app.post("/sessions/{session_id}/events", status_code=201, tags=["Logging"])
async def log_event(session_id: int, payload: EventLog):

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
     
    db.log_event(session_id, payload.event_type, payload.severity, payload.message)
    return {"message": "Event logged"}

@app.get("/sessions/{session_id}/sensors/{sensor_type}/stats", response_model=SensorStatsResponse, tags=["Analytics"])
async def get_sensor_stats(session_id: int, sensor_type: str):

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
     
    stats = db.sensor_stats(session_id, sensor_type)
    if not stats or stats["count"] == 0:
        raise HTTPException(status_code=404, detail=f"No data for sensor {sensor_type}")
    return stats

@app.get("/sessions/{session_id}/events", response_model=List[EventResponse], tags=["Analytics"])
async def get_events(session_id: int, severity: Optional[str] = Query(None, regex="^(info|warning|error)$")):

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
     
    events = db.list_events(session_id, severity)
    return events

@app.get("/sessions/{session_id}/sensors", response_model=List[SensorReadingResponse], tags=["Analytics"])
async def get_sensor_readings(
    session_id: int,
    sensor_type: Optional[str] = Query(None, description="Фильтр по типу сенсора, например: IR_1")
):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    readings = db.list_sensor_readings(session_id, sensor_type)
    if not readings:
        raise HTTPException(status_code=404, detail="No sensor readings found")
    return readings

@app.get("/sessions/{session_id}/actuators", response_model=List[ActuatorCommandResponse], tags=["Analytics"])
async def get_actuator_commands(
    session_id: int,
    actuator_type: Optional[str] = Query(None, description="Фильтр по типу актуатора, например: Motor_L")
):

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    commands = db.list_actuator_commands(session_id, actuator_type)
    if not commands:
        raise HTTPException(status_code=404, detail="No actuator commands found")
    return commands