"""Tests for utils module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from lost_years.utils import closest, column_exists, download_file, fixup_columns, isstring


class TestUtilFunctions:
    """Test utility functions."""

    def test_isstring(self):
        """Test isstring function with various types."""
        # Test with strings
        assert isstring("hello") is True
        assert isstring("") is True

        # Test with non-strings
        assert isstring(42) is False
        assert isstring(None) is False
        assert isstring([]) is False
        assert isstring({"key": "value"}) is False

    def test_column_exists_valid_columns(self, capsys):
        """Test column_exists with valid columns."""
        df = pd.DataFrame({"age": [25, 30], "name": ["Alice", "Bob"]})

        # Test existing columns
        assert column_exists(df, "age") is True
        assert column_exists(df, "name") is True

        # No output should be printed for valid columns
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_column_exists_invalid_columns(self, capsys):
        """Test column_exists with invalid columns."""
        df = pd.DataFrame({"age": [25, 30], "name": ["Alice", "Bob"]})

        # Test non-existing column
        assert column_exists(df, "invalid_col") is False

        # Check error message is printed
        captured = capsys.readouterr()
        assert "The specify column `invalid_col` not found" in captured.out

    def test_column_exists_none_column(self):
        """Test column_exists with None column."""
        df = pd.DataFrame({"age": [25, 30]})

        # None should return True (no column check needed)
        assert column_exists(df, None) is True

    def test_fixup_columns_with_integers(self):
        """Test fixup_columns with integer column indices."""
        cols = [0, 1, 2, "name", "age"]
        result = fixup_columns(cols)
        expected = ["col0", "col1", "col2", "name", "age"]
        assert result == expected

    def test_fixup_columns_with_strings(self):
        """Test fixup_columns with all string columns."""
        cols = ["name", "age", "country"]
        result = fixup_columns(cols)
        assert result == cols  # Should return unchanged

    def test_fixup_columns_mixed_types(self):
        """Test fixup_columns with mixed types."""
        cols = [0, "name", 2, "age", 4]
        result = fixup_columns(cols)
        expected = ["col0", "name", "col2", "age", "col4"]
        assert result == expected

    def test_closest_with_list(self):
        """Test closest function with regular list."""
        lst = [1.0, 2.5, 3.8, 5.1]

        assert closest(lst, 2.0) == 2.5  # Closest to 2.0
        assert closest(lst, 3.0) == 2.5  # Closest to 3.0 (tie goes to first)
        assert closest(lst, 4.0) == 3.8  # Closest to 4.0
        assert closest(lst, 6.0) == 5.1  # Closest to 6.0

    def test_closest_with_numpy_array(self):
        """Test closest function with numpy array."""
        arr = np.array([1.0, 2.5, 3.8, 5.1])

        assert closest(arr, 2.0) == 2.5
        assert closest(arr, 4.0) == 3.8

    def test_closest_edge_cases(self):
        """Test closest function with edge cases."""
        # Single element
        assert closest([5.0], 10.0) == 5.0

        # Exact match
        lst = [1.0, 2.0, 3.0]
        assert closest(lst, 2.0) == 2.0

    @patch('lost_years.utils.requests.get')
    def test_download_file_default_path(self, mock_get):
        """Test download_file with default path."""
        # Mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            try:
                # Change to temp directory for test
                import os
                os.chdir(tmpdir)

                download_file("https://example.com/file.txt")

                # Check file was created
                assert Path("file.txt").exists()

                # Check content
                content = Path("file.txt").read_bytes()
                assert content == b"chunk1chunk2"

            finally:
                os.chdir(original_cwd)

    @patch('lost_years.utils.requests.get')
    def test_download_file_custom_path(self, mock_get):
        """Test download_file with custom path."""
        # Mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"test data"]
        mock_get.return_value = mock_response

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            custom_path = tmp.name

        try:
            download_file("https://example.com/file.txt", custom_path)

            # Check file exists and has correct content
            assert Path(custom_path).exists()
            content = Path(custom_path).read_bytes()
            assert content == b"test data"

        finally:
            Path(custom_path).unlink(missing_ok=True)

    @patch('lost_years.utils.requests.get')
    def test_download_file_path_object(self, mock_get):
        """Test download_file with Path object."""
        # Mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b"path test"]
        mock_get.return_value = mock_response

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path_obj = Path(tmp.name)

        try:
            download_file("https://example.com/file.txt", path_obj)

            # Check file exists and has correct content
            assert path_obj.exists()
            content = path_obj.read_bytes()
            assert content == b"path test"

        finally:
            path_obj.unlink(missing_ok=True)
