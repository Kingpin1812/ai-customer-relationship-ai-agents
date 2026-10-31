from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings


@lru_cache
def get_checkpointer() -> PostgresSaver:
    pool = ConnectionPool(
        get_settings().checkpoint_conninfo,
        min_size=1,
        max_size=8,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    saver = PostgresSaver(pool)  # type: ignore[arg-type]  # accepts a pool at runtime
    saver.setup()
    return saver
