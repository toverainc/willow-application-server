from logging import getLogger

from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine

from app.const import DB_URL
from app.db.models import WillowConfigTable, WillowConfigType
from app.internal.config import WillowConfig


log = getLogger("WAS")

connect_args = {"check_same_thread": False}
engine = create_engine(DB_URL, echo=True, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def migrate_user_config(config):
    config = WillowConfig.parse_obj(config)
    log.debug(f"config: {config}")

    with Session(engine) as session:
        for k, v in iter(config):
            db_config = WillowConfigTable(
                config_type=WillowConfigType.config,
                config_name=k,
            )
            if v is not None:
                db_config.config_value = str(v)
            session.add(db_config)

        try:
            session.commit()
        except IntegrityError as e:
            # TODO avoid users thinking something is wrong here
            log.warning(e)
            session.rollback()
