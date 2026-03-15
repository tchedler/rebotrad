# tests/test_connection.py
# Sentinel Pro KB5 — Test Connexion MT5

import unittest
import time
from unittest.mock import MagicMock, patch, PropertyMock
from gateway.mt5_connector import MT5Connector
from config.constants import Gateway, Status


class TestMT5Connection(unittest.TestCase):
    """Tests unitaires MT5Connector."""

    def setUp(self):
        self.connector = MT5Connector()

    def tearDown(self):
        try:
            self.connector.disconnect()
        except Exception:
            pass

    # ─── CONNEXION ───────────────────────────────

    @patch("gateway.mt5connector.mt5")
    def test_connect_success(self, mock_mt5):
        """Connexion réussie → statut CONNECTED."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value      = True
        mock_mt5.account_info.return_value = MagicMock(
            login=12345, balance=10000.0,
            currency="USD", server="Exness-MT5Real",
            leverage=500
        )
        result = self.connector.connect()
        self.assertTrue(result)
        self.assertEqual(self.connector.status, Status.CONNECTED)

    @patch("gateway.mt5connector.mt5")
    def test_connect_fail_initialize(self, mock_mt5):
        """Échec initialize → statut DISCONNECTED."""
        mock_mt5.initialize.return_value = False
        mock_mt5.last_error.return_value  = (-1, "Erreur test")
        result = self.connector.connect()
        self.assertFalse(result)
        self.assertEqual(self.connector.status, Status.DISCONNECTED)

    @patch("gateway.mt5connector.mt5")
    def test_connect_fail_login(self, mock_mt5):
        """Échec login → statut DISCONNECTED."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value      = False
        mock_mt5.last_error.return_value = (-2, "Login échoué")
        result = self.connector.connect()
        self.assertFalse(result)
        self.assertEqual(self.connector.status, Status.DISCONNECTED)

    @patch("gateway.mt5connector.mt5")
    def test_connect_no_account_info(self, mock_mt5):
        """account_info None → statut DISCONNECTED."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value      = True
        mock_mt5.account_info.return_value = None
        result = self.connector.connect()
        self.assertFalse(result)

    # ─── DÉCONNEXION ─────────────────────────────

    @patch("gateway.mt5connector.mt5")
    def test_disconnect(self, mock_mt5):
        """Disconnect → statut DISCONNECTED + mt5.shutdown appelé."""
        mock_mt5.initialize.return_value   = True
        mock_mt5.login.return_value        = True
        mock_mt5.account_info.return_value = MagicMock(
            login=1, balance=1000.0, currency="USD",
            server="Test", leverage=100
        )
        self.connector.connect()
        self.connector.disconnect()
        self.assertEqual(self.connector.status, Status.DISCONNECTED)
        mock_mt5.shutdown.assert_called()

    # ─── HEARTBEAT ───────────────────────────────

    @patch("gateway.mt5connector.mt5")
    def test_heartbeat_detects_disconnect(self, mock_mt5):
        """Heartbeat détecte déconnexion → statut change."""
        mock_mt5.initialize.return_value   = True
        mock_mt5.login.return_value        = True
        mock_mt5.account_info.return_value = MagicMock(
            login=1, balance=1000.0, currency="USD",
            server="Test", leverage=100
        )
        self.connector.connect()
        # Simuler perte connexion
        mock_mt5.terminal_info.return_value = None
        time.sleep(0.1)
        result = self.connector.check_connection()
        self.assertFalse(result)

    # ─── CALLBACKS ───────────────────────────────

    @patch("gateway.mt5connector.mt5")
    def test_subscribe_disconnect_callback(self, mock_mt5):
        """subscribe_disconnect → callback appelé sur déconnexion."""
        called = []
        def on_disconnect():
            called.append(True)

        self.connector.subscribe_disconnect(on_disconnect)
        self.connector.notify_disconnect()
        self.assertEqual(len(called), 1)

    def test_subscribe_same_callback_twice(self):
        """Même callback souscrit 2x → enregistré une seule fois."""
        cb = MagicMock()
        self.connector.subscribe_disconnect(cb)
        self.connector.subscribe_disconnect(cb)
        self.assertEqual(len(self.connector.disconnect_callbacks), 1)

    # ─── INFOS COMPTE ─────────────────────────────

    @patch("gateway.mt5connector.mt5")
    def test_get_account_info_when_connected(self, mock_mt5):
        """get_account_info → dict complet quand connecté."""
        mock_mt5.initialize.return_value   = True
        mock_mt5.login.return_value        = True
        account = MagicMock(
            login=99999, balance=5000.0, equity=5100.0,
            margin=200.0, margin_free=4800.0,
            currency="USD", server="Exness-MT5Real", leverage=500
        )
        mock_mt5.account_info.return_value = account
        self.connector.connect()

        info = self.connector.get_account_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["login"],   99999)
        self.assertEqual(info["balance"], 5000.0)

    @patch("gateway.mt5connector.mt5")
    def test_get_account_info_when_disconnected(self, mock_mt5):
        """get_account_info → None quand déconnecté."""
        info = self.connector.get_account_info()
        self.assertIsNone(info)

    # ─── STATUT ──────────────────────────────────

    def test_get_status_keys(self):
        """get_status → toutes les clés attendues présentes."""
        status = self.connector.get_status()
        for key in ["status", "is_connected", "last_connected_at",
                    "reconnect_count", "reconnecting"]:
            self.assertIn(key, status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
