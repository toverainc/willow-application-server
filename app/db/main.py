from logging import getLogger

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from app.db.models import WillowClientTable, WillowConfigNamespaceType, WillowConfigTable, WillowConfigType
from app.internal.config import WillowConfig, WillowNvsConfig, WillowNvsWas, WillowNvsWifi
from app.settings import get_settings


log = getLogger("WAS")

settings = get_settings()

connect_args = {}
if settings.db_url.find("sqlite://") != -1:
    connect_args["check_same_thread"] = False

engine = create_engine(settings.db_url, echo=False, connect_args=connect_args)


def convert_str_or_none(input):
    """ Convert value to str or None

    We're saving values of different type in the config_value field of WillowConfigTable
    We therefore need to cast the value to str.
    Casting None to str would result in "None" being save in the database.
    This is a helper function to avoid that.
    """
    if input is None:
        return None
    else:
        return str(input)


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


def get_devices_db():
    devices = []
    with Session(engine) as session:
        stmt = select(WillowClientTable)
        records = session.exec(stmt)

        for record in records:
            devices.append(record.model_dump())

    return devices


def get_nvs_db():
    config = WillowNvsConfig()
    config_was = WillowNvsWas()
    config_wifi = WillowNvsWifi()

    with Session(engine) as session:
        stmt = select(WillowConfigTable).where(WillowConfigTable.config_type == WillowConfigType.nvs)
        records = session.exec(stmt)

        for record in records:
            if record.config_namespace == WillowConfigNamespaceType.WAS:
                setattr(config_was, record.config_name, record.config_value)

            elif record.config_namespace == WillowConfigNamespaceType.WIFI:
                setattr(config_wifi, record.config_name, record.config_value)

        config.WAS = config_was
        config.WIFI = config_wifi

    return config.model_dump(exclude_none=True)


def migrate_user_config(config):
    config = WillowConfig.parse_obj(config)
    log.debug(f"config: {config}")

    with Session(engine) as session:
        for k, v in iter(config):
            db_config = WillowConfigTable(
                config_type=WillowConfigType.config,
                config_name=k,
                config_value=convert_str_or_none(v)
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


def migrate_user_client_config(clients):
    log.debug(f"clients: {clients}")

    with Session(engine) as session:
        for client in iter(clients):
            db_client = WillowClientTable(
                label=client["label"],
                mac_addr=client["mac_addr"]
            )
            session.add(db_client)

        try:
            session.commit()
        except IntegrityError as e:
            # TODO avoid users thinking something is wrong here
            log.warning(e)
            session.rollback()


def migrate_user_nvs(config):
    config = WillowNvsConfig.parse_obj(config)
    log.debug(f"config: {config}")
    log.debug(f"WAS: {config.WAS}")
    log.debug(f"WIFI: {config.WIFI}")

    with Session(engine) as session:
        for k, v in iter(config.WAS):
            log.debug(f"WAS: k={k} v={v}")
            db_config = WillowConfigTable(
                config_type=WillowConfigType.nvs,
                config_name=k,
                config_namespace=WillowConfigNamespaceType.WAS,
                config_value=str(v),
            )
            session.add(db_config)

        for k, v in iter(config.WIFI):
            log.debug(f"WIFI: k={k} v={v}")
            db_config = WillowConfigTable(
                config_type=WillowConfigType.nvs,
                config_name=k,
                config_namespace=WillowConfigNamespaceType.WIFI,
                config_value=str(v),
            )
            session.add(db_config)

        try:
            session.commit()
        except IntegrityError as e:
            # TODO avoid users thinking something is wrong here
            log.warning(e)
            session.rollback()


def save_client_config_to_db(clients):
    log.debug(f"save_client_config_to_db: {clients}")

    with Session(engine) as session:
        for client in iter(clients):
            stmt = select(WillowClientTable).where(WillowClientTable.mac_addr == client["mac_addr"])
            record = session.exec(stmt).first()

            if record is None:
                record = WillowClientTable(
                    label=client["label"],
                    mac_addr=client["mac_addr"]
                )

            else:
                if record.label == client["label"] and record.mac_addr == client["mac_addr"]:
                    continue
                record.label = client["label"]
                record.mac_addr = client["mac_addr"]

            session.add(record)

        try:
            session.commit()
        except IntegrityError as e:
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
                    config_value=convert_str_or_none(value)
                )

            else:
                if record.config_value == convert_str_or_none(value):
                    continue

                record.config_value = convert_str_or_none(value)

            session.add(record)

        try:
            session.commit()
            session.refresh(record)
        except IntegrityError as e:
            log.warning(e)
            session.rollback()


def save_nvs_to_db(config):
    config = WillowNvsConfig.parse_obj(config)
    log.debug(f"save_nvs_to_db: {config}")

    with Session(engine) as session:
        for name, value in iter(config.WAS):
            stmt = select(WillowConfigTable).where(
                WillowConfigTable.config_type == WillowConfigType.nvs,
                WillowConfigTable.config_name == name,
                WillowConfigTable.config_namespace == WillowConfigNamespaceType.WAS,
            )
            record = session.exec(stmt).first()

            if record is None:
                record = WillowConfigTable(
                    config_type=WillowConfigType.nvs,
                    config_name=name,
                    config_namespace=WillowConfigNamespaceType.WAS,
                    config_value=str(value),
                )

            else:
                if record.config_value == str(value):
                    continue
                record.config_value = str(value)

            session.add(record)

        for name, value in iter(config.WIFI):
            stmt = select(WillowConfigTable).where(
                WillowConfigTable.config_type == WillowConfigType.nvs,
                WillowConfigTable.config_name == name,
                WillowConfigTable.config_namespace == WillowConfigNamespaceType.WIFI,
            )
            record = session.exec(stmt).first()

            if record is None:
                record = WillowConfigTable(
                    config_type=WillowConfigType.nvs,
                    config_name=name,
                    config_namespace=WillowConfigNamespaceType.WIFI,
                    config_value=str(value),
                )

            else:
                if record.config_value == str(value):
                    continue
                record.config_value = str(value)

            session.add(record)

        try:
            session.commit()
            session.refresh(record)
        except IntegrityError as e:
            log.warning(e)
            session.rollback()
