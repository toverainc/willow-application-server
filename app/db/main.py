from sqlmodel import SQLModel, create_engine

from app.const import DB_URL
from app.db.models import WillowConfigTable


connect_args = {"check_same_thread": False}
engine = create_engine(DB_URL, echo=True, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
