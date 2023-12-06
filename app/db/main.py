from logging import getLogger

from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine, select

from app.const import DB_URL
from app.db.models import WillowConfigTable, WillowConfigType
from app.internal.config import WillowConfig


log = getLogger("WAS")

connect_args = {"check_same_thread": False}
engine = create_engine(DB_URL, echo=True, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_config_db():
    config = WillowConfig()

    with Session(engine) as session:
        stmt = select(WillowConfigTable).where(
            WillowConfigTable.config_type == WillowConfigType.config,
            WillowConfigTable.config_value is not None
        )
        records = session.exec(stmt)

        for record in records:
            setattr(config, record.config_name, record.config_value)

    return config.model_dump(exclude_none=True)


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


def save_config_to_db(config):
    config = WillowConfig.parse_obj(config)
    log.debug(f"save_config_to_db: {config}")

    with Session(engine) as session:
        for name, value in iter(config):
            stmt = select(WillowConfigTable).where(
                WillowConfigTable.config_type == WillowConfigType.config,
                WillowConfigTable.config_name == name,
            )
            record = session.exec(stmt).first()

            if record is None:
                record = WillowConfigTable(
                    config_type=WillowConfigType.config,
                    config_name=name,
                )
                # we need to cast to str here as we're saving different types (bool, int, str)
                # casting None to str would save "None" in the db
                if value is None:
                    record.config_value = None
                else:
                    record.config_value = str(value)

            else:
                if record.config_value == str(value):
                    continue

                # we need to cast to str here as we're saving different types (bool, int, str)
                # casting None to str would save "None" in the db
                if value is None:
                    record.config_value = None
                else:
                    record.config_value = str(value)

            session.add(record)

        try:
            session.commit()
            session.refresh(record)
        except IntegrityError as e:
            log.warning(e)
            session.rollback()
