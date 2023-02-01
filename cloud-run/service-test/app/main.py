from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore

from .schemas import ServiceConfig
from .config import settings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.post("/config")
def configure_service(config: ServiceConfig):
    db = firestore.Client(project=settings.FIRESTORE_PROJECT_ID)
    db.collection(settings.FIRESTORE_COLLECTION).document(config.name).set(
        {'down_until': datetime.now().timestamp() + timedelta(seconds=config.down_time_seconds).total_seconds()})

    return {"message": "Service configured successfully"}


@app.get("/{service_name}")
def get_service_status(service_name: str):
    db = firestore.Client(project=settings.FIRESTORE_PROJECT_ID)
    doc = db.collection(settings.FIRESTORE_COLLECTION).document(service_name).get()

    if doc.exists:
        time_posix = doc.to_dict().get("down_until", 0)

        if time_posix < datetime.now().timestamp():
            return {"status": "up"}

    raise HTTPException(status_code=503, detail="Service is down")
