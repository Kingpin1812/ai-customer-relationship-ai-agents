"""Prepare the file store and checkpoint tables once, before several processes race to do it."""

from app.agents.checkpointer import get_checkpointer
from app.integrations.storage import get_storage


def main() -> None:
    get_storage()
    get_checkpointer()


if __name__ == "__main__":
    main()
