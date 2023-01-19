from pydantic import BaseSettings


class Settings(BaseSettings):
    FIRESTORE_PROJECT_ID: str
    FIRESTORE_COLLECTION: str


settings = Settings()
