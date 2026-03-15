"""Tests for strict parser image handling without URL fallback."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from django.test import SimpleTestCase

from boats.parser import download_and_save_image


class ParserImageStrictModeTest(SimpleTestCase):
    @patch("boats.parser.requests.get")
    @patch("boats.parser.upload_file_to_s3", return_value=False)
    @patch("boats.parser.check_s3_exists", return_value=False)
    def test_download_returns_none_when_s3_unavailable(
        self,
        _mock_s3_exists,
        _mock_upload,
        mock_get,
    ):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.iter_content.return_value = [b"abc"]
        mock_get.return_value = response

        with TemporaryDirectory() as tmpdir:
            with patch("boats.parser.MEDIA_ROOT", tmpdir):
                image_path = "boats/62b96d157a9323583a5a4880/650d96fa43b7cac28800ead4.jpg"
                result = download_and_save_image(image_path)

        self.assertIsNone(result)

    @patch("boats.parser.check_s3_exists", return_value=False)
    def test_invalid_path_returns_none(self, _mock_s3_exists):
        result = download_and_save_image("broken-path.jpg")
        self.assertIsNone(result)

    @patch("boats.parser.check_s3_exists", return_value=True)
    def test_numeric_boat_folder_path_is_supported(self, _mock_s3_exists):
        result = download_and_save_image("boats/116675/5e6a6de401afcf0d557d9f04.jpeg")
        self.assertEqual(
            result,
            "https://cdn2.prvms.ru/yachts/116675/5e6a6de401afcf0d557d9f04.jpeg",
        )
