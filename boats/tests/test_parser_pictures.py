"""Tests for robust picture extraction from boat pages."""
from django.test import SimpleTestCase
from bs4 import BeautifulSoup

from boats.parser import extract_pictures


class ParserPicturesExtractionTest(SimpleTestCase):
    def test_extracts_from_gallery_component_with_gallery_attr(self):
        boat_id = '116675'
        html = f"""
        <html><body>
          <gallery :gallery='[
            {{"path":"boats/{boat_id}/main_01.jpg"}},
            {{"path":"boats/{boat_id}/main_02.jpg"}}
          ]'></gallery>
        </body></html>
        """
        soup = BeautifulSoup(html, 'html.parser')

        pics = extract_pictures(html, soup)

        self.assertEqual(
            pics,
            [
                f'boats/{boat_id}/main_01.jpg',
                f'boats/{boat_id}/main_02.jpg',
            ],
        )

    def test_extracts_from_gallery_images_with_url_and_cdn(self):
        boat_id = '62b96d157a9323583a5a4880'
        html = f"""
        <html><body>
          <gallery-mobile :images='[
            {{"url":"https://imageresizer.yachtsbt.com/boats/{boat_id}/front-view-01.jpg?method=fit"}},
            {{"path":"boats/{boat_id}/photo_2.webp"}},
            {{"src":"https://cdn2.prvms.ru/yachts/{boat_id}/photo_3.jpeg"}}
          ]'></gallery-mobile>
        </body></html>
        """
        soup = BeautifulSoup(html, 'html.parser')

        pics = extract_pictures(html, soup)

        self.assertEqual(
            pics,
            [
                f'boats/{boat_id}/front-view-01.jpg',
                f'boats/{boat_id}/photo_2.webp',
                f'boats/{boat_id}/photo_3.jpeg',
            ],
        )

    def test_regex_fallback_handles_non_hex_filenames(self):
        boat_id = '62b96d157a9323583a5a4880'
        html = (
            f'<html><body><script>var data = {{"main_img":"boats/{boat_id}/front-view-01.jpg"}};</script>'
            f'<script>var data2 = {{"thumb":"boats/{boat_id}/deck.photo_02.png"}};</script></body></html>'
        )
        soup = BeautifulSoup(html, 'html.parser')

        pics = extract_pictures(html, soup)

        self.assertIn(f'boats/{boat_id}/front-view-01.jpg', pics)
        self.assertIn(f'boats/{boat_id}/deck.photo_02.png', pics)
