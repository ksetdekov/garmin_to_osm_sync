"""
Unit tests for main.py

Tests cover:
- Token management (load, save, exchange, refresh)
- OAuth authorization flow
- Database operations
- GPX upload functionality
- Main sync logic
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open, call
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import tempfile
import os

# Import the module under test
import main


class TestTokenManagement(unittest.TestCase):
    """Tests for token loading, saving, and exchanging."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tokens_file = Path(self.temp_dir.name) / "tokens.json"
        self.original_tokens_file = main.TOKENS_FILE
        main.TOKENS_FILE = self.tokens_file

    def tearDown(self):
        """Clean up test fixtures."""
        main.TOKENS_FILE = self.original_tokens_file
        self.temp_dir.cleanup()

    def test_load_tokens_file_not_exists(self):
        """Test loading tokens when file doesn't exist."""
        result = main.load_tokens()
        self.assertIsNone(result)

    def test_load_tokens_valid_file(self):
        """Test loading tokens from valid JSON file."""
        test_tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": "2025-12-31T23:59:59+00:00"
        }
        self.tokens_file.write_text(json.dumps(test_tokens))
        result = main.load_tokens()
        self.assertEqual(result, test_tokens)

    def test_load_tokens_invalid_json(self):
        """Test loading tokens from invalid JSON file."""
        self.tokens_file.write_text("invalid json {")
        result = main.load_tokens()
        self.assertIsNone(result)

    def test_save_tokens(self):
        """Test saving tokens to file."""
        test_tokens = {
            "access_token": "test_token",
            "refresh_token": "refresh_token"
        }
        main.save_tokens(test_tokens)
        saved_data = json.loads(self.tokens_file.read_text())
        self.assertEqual(saved_data, test_tokens)

    def test_save_tokens_creates_file(self):
        """Test that save_tokens creates the file if it doesn't exist."""
        self.assertFalse(self.tokens_file.exists())
        test_tokens = {"access_token": "test"}
        main.save_tokens(test_tokens)
        self.assertTrue(self.tokens_file.exists())

    @patch('main.requests.post')
    def test_exchange_code_for_tokens(self, mock_post):
        """Test exchanging authorization code for tokens."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
            "scope": "read_gpx write_gpx"
        }
        mock_post.return_value = mock_response

        result = main.exchange_code_for_tokens("auth_code")

        self.assertEqual(result["access_token"], "new_access_token")
        self.assertEqual(result["refresh_token"], "new_refresh_token")
        self.assertIn("expires_at", result)
        self.assertIn("obtained_at", result)

    @patch('main.requests.post')
    def test_exchange_code_for_tokens_no_expires_in(self, mock_post):
        """Test exchange when expires_in is not provided."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "token",
            "refresh_token": "refresh"
        }
        mock_post.return_value = mock_response

        result = main.exchange_code_for_tokens("code")
        self.assertIsNone(result.get("expires_at"))

    @patch('main.requests.post')
    def test_refresh_tokens(self, mock_post):
        """Test refreshing access token."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "refreshed_access_token",
            "refresh_token": "same_refresh_token",
            "expires_in": 3600,
            "scope": "read_gpx write_gpx"
        }
        mock_post.return_value = mock_response

        result = main.refresh_tokens("original_refresh_token")

        self.assertEqual(result["access_token"], "refreshed_access_token")
        self.assertEqual(result["refresh_token"], "same_refresh_token")

    @patch('main.requests.post')
    def test_refresh_tokens_uses_provided_refresh_token(self, mock_post):
        """Test that refresh_tokens uses provided refresh_token if not in response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response

        result = main.refresh_tokens("original_refresh_token")
        self.assertEqual(result["refresh_token"], "original_refresh_token")


class TestEnsureAccessToken(unittest.TestCase):
    """Tests for the ensure_access_token function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tokens_file = Path(self.temp_dir.name) / "tokens.json"
        self.original_tokens_file = main.TOKENS_FILE
        main.TOKENS_FILE = self.tokens_file

    def tearDown(self):
        """Clean up test fixtures."""
        main.TOKENS_FILE = self.original_tokens_file
        self.temp_dir.cleanup()

    @patch('main.CLIENT_ID', "test_id")
    @patch('main.CLIENT_SECRET', "test_secret")
    @patch('main.REDIRECT_URI', "http://localhost:8080")
    @patch('main.get_authorization_code')
    @patch('main.exchange_code_for_tokens')
    def test_ensure_access_token_new_auth(self, mock_exchange, mock_get_code):
        """Test obtaining access token via new authorization."""
        mock_get_code.return_value = "auth_code"
        mock_exchange.return_value = {"access_token": "new_token"}

        token = main.ensure_access_token()

        self.assertEqual(token, "new_token")
        mock_get_code.assert_called_once()
        mock_exchange.assert_called_once_with("auth_code")

    @patch('main.CLIENT_ID', "test_id")
    @patch('main.CLIENT_SECRET', "test_secret")
    @patch('main.REDIRECT_URI', "http://localhost:8080")
    @patch('main.get_authorization_code')
    def test_ensure_access_token_no_code_returned(self, mock_get_code):
        """Test handling when authorization returns no code."""
        mock_get_code.return_value = None

        with self.assertRaises(RuntimeError):
            main.ensure_access_token()

    @patch('main.CLIENT_ID', None)
    def test_ensure_access_token_missing_env_vars(self):
        """Test error when environment variables are missing."""
        with self.assertRaises(RuntimeError):
            main.ensure_access_token()

    def test_ensure_access_token_valid_cached_token(self):
        """Test using cached valid token."""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        test_tokens = {
            "access_token": "cached_token",
            "refresh_token": "refresh",
            "expires_at": future_time
        }
        self.tokens_file.write_text(json.dumps(test_tokens))

        token = main.ensure_access_token()
        self.assertEqual(token, "cached_token")

    @patch('main.refresh_tokens')
    def test_ensure_access_token_expired_token_refresh(self, mock_refresh):
        """Test refreshing when token is expired."""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        test_tokens = {
            "access_token": "expired_token",
            "refresh_token": "refresh_token",
            "expires_at": past_time
        }
        self.tokens_file.write_text(json.dumps(test_tokens))
        mock_refresh.return_value = {"access_token": "refreshed_token"}

        token = main.ensure_access_token()

        self.assertEqual(token, "refreshed_token")
        mock_refresh.assert_called_once()


class TestDatabaseOperations(unittest.TestCase):
    """Tests for database initialization and operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.temp_dir.name) / "test.db"
        self.original_db_file = main.DB_FILE
        main.DB_FILE = self.db_file

    def tearDown(self):
        """Clean up test fixtures."""
        main.DB_FILE = self.original_db_file
        self.temp_dir.cleanup()

    def test_init_db_creates_table(self):
        """Test that init_db creates the processed_activities table."""
        main.init_db()
        
        conn = sqlite3.connect(self.db_file)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processed_activities'")
        table_exists = cur.fetchone() is not None
        conn.close()
        
        self.assertTrue(table_exists)

    def test_init_db_idempotent(self):
        """Test that init_db can be called multiple times safely."""
        main.init_db()
        main.init_db()  # Should not raise
        self.assertTrue(self.db_file.exists())

    def test_get_processed_ids_empty(self):
        """Test getting processed IDs from empty database."""
        result = main.get_processed_ids()
        self.assertEqual(result, set())

    def test_get_processed_ids_with_data(self):
        """Test getting processed IDs from populated database."""
        main.init_db()
        main.add_processed_id("activity_1")
        main.add_processed_id("activity_2")
        
        result = main.get_processed_ids()
        
        self.assertEqual(result, {"activity_1", "activity_2"})

    def test_add_processed_id(self):
        """Test adding a processed activity ID."""
        main.init_db()
        main.add_processed_id("test_activity", gpx_id="gpx_123", status="uploaded")
        
        conn = sqlite3.connect(self.db_file)
        cur = conn.cursor()
        cur.execute("SELECT activity_id, gpx_id, status FROM processed_activities WHERE activity_id=?", ("test_activity",))
        row = cur.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "test_activity")
        self.assertEqual(row[1], "gpx_123")
        self.assertEqual(row[2], "uploaded")

    def test_add_processed_id_with_metadata(self):
        """Test adding processed ID with metadata."""
        main.init_db()
        metadata = {"key": "value"}
        main.add_processed_id("activity_1", metadata=metadata)
        
        conn = sqlite3.connect(self.db_file)
        cur = conn.cursor()
        cur.execute("SELECT metadata FROM processed_activities WHERE activity_id=?", ("activity_1",))
        row = cur.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        loaded_metadata = json.loads(row[0])
        self.assertEqual(loaded_metadata, metadata)

    def test_add_processed_id_replaces_existing(self):
        """Test that add_processed_id replaces existing entries."""
        main.init_db()
        main.add_processed_id("activity_1", gpx_id="gpx_1")
        main.add_processed_id("activity_1", gpx_id="gpx_2")
        
        result = main.get_processed_ids()
        self.assertEqual(len(result), 1)


class TestGPXUpload(unittest.TestCase):
    """Tests for GPX upload functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.gpx_path = Path(self.temp_dir.name) / "test.gpx"
        self.gpx_path.write_text("<gpx></gpx>")

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    @patch('main.requests.post')
    def test_upload_gpx_with_bearer_success(self, mock_post):
        """Test successful GPX upload."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "12345"
        mock_post.return_value = mock_response

        result = main.upload_gpx_with_bearer(
            "access_token",
            self.gpx_path,
            "Test Activity",
            "tag1,tag2",
            "identifiable"
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.text, "12345")

    @patch('main.requests.post')
    def test_upload_gpx_with_bearer_sets_headers(self, mock_post):
        """Test that upload sets correct authorization header."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        main.upload_gpx_with_bearer(
            "test_token_123",
            self.gpx_path,
            "desc",
            "tags",
            "private"
        )

        call_args = mock_post.call_args
        headers = call_args[1].get('headers') or call_args[0][1] if len(call_args[0]) > 1 else {}
        
        # Check that Bearer token is in headers
        self.assertIn("Authorization", call_args[1]['headers'])
        self.assertIn("test_token_123", call_args[1]['headers']["Authorization"])


class TestOAuthCallbackHandler(unittest.TestCase):
    """Tests for OAuth callback handler."""

    def test_oauth_callback_handler_get_code_from_query(self):
        """Test extracting authorization code from callback query string."""
        # Create a mock request object instead of instantiating the handler directly
        mock_request = MagicMock()
        mock_client_address = ("127.0.0.1", 8080)
        mock_server = MagicMock()
        
        # Patch the handler's initialization to avoid socket issues
        with patch.object(main.OAuthCallbackHandler, '__init__', return_value=None):
            handler = main.OAuthCallbackHandler(mock_request, mock_client_address, mock_server)
            handler.path = "/?code=test_auth_code"
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wfile = Mock()
            
            main.authorization_code = None
            handler.do_GET()
            
            self.assertEqual(main.authorization_code, "test_auth_code")

    def test_oauth_callback_handler_no_code(self):
        """Test callback without authorization code."""
        mock_request = MagicMock()
        mock_client_address = ("127.0.0.1", 8080)
        mock_server = MagicMock()
        
        with patch.object(main.OAuthCallbackHandler, '__init__', return_value=None):
            handler = main.OAuthCallbackHandler(mock_request, mock_client_address, mock_server)
            handler.path = "/?error=denied"
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wfile = Mock()
            
            main.authorization_code = None
            handler.do_GET()
            
            self.assertIsNone(main.authorization_code)


class TestGetAuthorizationCode(unittest.TestCase):
    """Tests for get_authorization_code function."""

    @patch('main.HTTPServer')
    @patch('main.webbrowser.open')
    def test_get_authorization_code_opens_browser(self, mock_browser, mock_server):
        """Test that authorization opens browser."""
        mock_httpd_instance = Mock()
        mock_server.return_value = mock_httpd_instance
        
        # Set the global variable to simulate receiving code
        main.authorization_code = "test_code"
        
        with patch('main.CLIENT_ID', "client_id"), \
             patch('main.CLIENT_SECRET', "secret"), \
             patch('main.REDIRECT_URI', "http://127.0.0.1:8080/callback"), \
             patch('main.SCOPES', "read_gpx"):
            
            result = main.get_authorization_code()
            
            # Browser should be opened
            mock_browser.assert_called_once()
            # Server should handle a request
            mock_httpd_instance.handle_request.assert_called_once()


class TestMainFunction(unittest.TestCase):
    """Tests for the main sync function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.temp_dir.name) / "test.db"
        self.download_dir = Path(self.temp_dir.name) / "downloads"
        self.download_dir.mkdir(exist_ok=True)
        
        self.original_db_file = main.DB_FILE
        self.original_download_dir = main.DOWNLOAD_DIR
        
        main.DB_FILE = self.db_file
        main.DOWNLOAD_DIR = self.download_dir

    def tearDown(self):
        """Clean up test fixtures."""
        main.DB_FILE = self.original_db_file
        main.DOWNLOAD_DIR = self.original_download_dir
        self.temp_dir.cleanup()

    @patch('sys.argv', ['main.py'])
    @patch('main.GARMIN_EMAIL', None)
    @patch('main.GARMIN_PASSWORD', None)
    @patch('main.logger')
    def test_main_missing_garmin_credentials(self, mock_logger):
        """Test main exits gracefully with missing Garmin credentials."""
        main.main()
        mock_logger.error.assert_called()

    @patch('sys.argv', ['main.py'])
    @patch('main.GARMIN_EMAIL', 'test@example.com')
    @patch('main.GARMIN_PASSWORD', 'password')
    @patch('main.ensure_access_token')
    @patch('main.Garmin')
    def test_main_get_activities_zero(self, mock_garmin_class, mock_ensure_token):
        """Test main with no new activities."""
        mock_ensure_token.return_value = "test_token"
        mock_garmin = Mock()
        mock_garmin.get_activities.return_value = []
        mock_garmin_class.return_value = mock_garmin
        
        main.main()
        
        # Should complete without errors
        mock_garmin.login.assert_called_once()

    @patch('sys.argv', ['main.py'])
    @patch('main.GARMIN_EMAIL', 'test@example.com')
    @patch('main.GARMIN_PASSWORD', 'password')
    @patch('main.DRY_RUN', True)
    @patch('main.ensure_access_token')
    @patch('main.Garmin')
    def test_main_dry_run_mode(self, mock_garmin_class, mock_ensure_token):
        """Test main in dry run mode."""
        mock_ensure_token.return_value = "test_token"
        
        activity = {
            "activityId": 123,
            "activityName": "Test Run",
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2025-01-01T10:00:00"
        }
        
        mock_garmin = Mock()
        mock_garmin.get_activities.return_value = [activity]
        mock_garmin.download_activity.return_value = b"<gpx></gpx>"
        mock_garmin_class.return_value = mock_garmin
        
        main.main()
        
        # Activity should be marked as processed
        processed = main.get_processed_ids()
        self.assertIn("123", processed)


class TestHistoryMode(unittest.TestCase):
    """Tests for history mode functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.temp_dir.name) / "test.db"
        self.download_dir = Path(self.temp_dir.name) / "downloads"
        self.download_dir.mkdir(exist_ok=True)
        
        self.original_db_file = main.DB_FILE
        self.original_download_dir = main.DOWNLOAD_DIR
        
        main.DB_FILE = self.db_file
        main.DOWNLOAD_DIR = self.download_dir

    def tearDown(self):
        """Clean up test fixtures."""
        main.DB_FILE = self.original_db_file
        main.DOWNLOAD_DIR = self.original_download_dir
        self.temp_dir.cleanup()

    @patch('sys.argv', ['main.py', '--history'])
    @patch('main.GARMIN_EMAIL', 'test@example.com')
    @patch('main.GARMIN_PASSWORD', 'password')
    @patch('main.time.sleep')
    @patch('main.ensure_access_token')
    @patch('main.Garmin')
    def test_main_history_mode_flag(self, mock_garmin_class, mock_ensure_token, mock_sleep):
        """Test that --history flag is recognized."""
        mock_ensure_token.return_value = "test_token"
        mock_garmin = Mock()
        mock_garmin.get_activities.return_value = []
        mock_garmin_class.return_value = mock_garmin
        
        main.main()
        mock_garmin.login.assert_called_once()


if __name__ == "__main__":
    unittest.main()
