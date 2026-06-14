import unittest
from unittest.mock import patch

from app.main import initialize_database, settings


class InitializeDatabaseTests(unittest.TestCase):
    def test_preserves_existing_tables_when_reset_disabled(self) -> None:
        with patch.object(settings, "RESET_DB_ON_STARTUP", False), patch(
            "app.main.Base.metadata.drop_all"
        ) as drop_all, patch("app.main.Base.metadata.create_all") as create_all:
            initialize_database()

        drop_all.assert_not_called()
        create_all.assert_called_once()

    def test_recreates_tables_when_reset_enabled(self) -> None:
        with patch.object(settings, "RESET_DB_ON_STARTUP", True), patch(
            "app.main.Base.metadata.drop_all"
        ) as drop_all, patch("app.main.Base.metadata.create_all") as create_all:
            initialize_database()

        drop_all.assert_called_once()
        create_all.assert_called_once()
