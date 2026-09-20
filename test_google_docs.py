import unittest
from unittest.mock import patch

from google_docs import GoogleDocsIntegration


class TestGoogleDocsIntegration(unittest.TestCase):
    def test_raises_helpful_error_without_google_dependencies(self):
        with patch("google_docs.Request", None), patch("google_docs.Credentials", None), patch("google_docs.Flow", None), patch("google_docs.build", None):
            with self.assertRaisesRegex(ImportError, "requirements-google.txt"):
                GoogleDocsIntegration().authorization_url()


if __name__ == "__main__":
    unittest.main()
