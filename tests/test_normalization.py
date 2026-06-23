import unittest

from listing_os.normalization import normalize_domain, normalize_url


class UrlNormalizationTest(unittest.TestCase):
    def test_normalize_url_removes_tracking_and_fragment(self):
        raw = "https://Example.com/path/?utm_source=google&b=2&gclid=abc&a=1#section"

        normalized = normalize_url(raw)

        self.assertEqual(normalized, "https://example.com/path/?a=1&b=2")

    def test_normalize_domain_collapses_common_japanese_prefixes(self):
        self.assertEqual(normalize_domain("https://www.example.co.jp/lp"), "example.co.jp")
        self.assertEqual(normalize_domain("https://m.example.com/compare"), "example.com")


if __name__ == "__main__":
    unittest.main()
