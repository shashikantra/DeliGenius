# migrations/env.py
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from deli_rag.config.settings import get_env
from deli_rag.db.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_env().database_url)
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()