from alembic import context

from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F403 - registers every table on Base.metadata

target_metadata = Base.metadata


def include_name(name, type_, parent_names) -> bool:
    # LangGraph owns and migrates its own checkpoint tables.
    return not (type_ == "table" and name and name.startswith("checkpoint"))


def run_migrations_offline() -> None:
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, include_name=include_name
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
