from sqlalchemy import text

from app import bootstrap
from app.db.session import engine


def test_bootstrap_prepares_the_store_and_checkpoint_tables_and_can_repeat():
    bootstrap.main()
    bootstrap.main()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT to_regclass('public.checkpoints')")) == "checkpoints"
