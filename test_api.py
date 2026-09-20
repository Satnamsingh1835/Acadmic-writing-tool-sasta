import io
import unittest

from fastapi.testclient import TestClient

from api import app


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_review_returns_structured_response_and_suggestions(self):
        response = self.client.post(
            "/review",
            json={
                "text": "It is important to note that caste shapes land relations (Gupta, 2000).",
                "profile": "standard",
                "include_refined_text": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("refined_text", payload)
        self.assertIn("grammar_and_style", payload)
        self.assertIn("literature_review", payload)
        self.assertIn("suggestions", payload)
        self.assertTrue(payload["suggestions"])

    def test_review_can_omit_refined_text(self):
        response = self.client.post(
            "/review",
            json={"text": "Caste shapes land relations.", "include_refined_text": False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["refined_text"])

    def test_review_rejects_empty_text(self):
        response = self.client.post("/review", json={"text": "   "})
        self.assertEqual(response.status_code, 400)

    def test_review_rejects_invalid_profile(self):
        response = self.client.post(
            "/review",
            json={"text": "Caste shapes land relations.", "profile": "unknown"},
        )
        self.assertEqual(response.status_code, 400)

    def test_review_file_accepts_utf8_txt(self):
        response = self.client.post(
            "/review/file",
            files={"file": ("proposal.txt", io.BytesIO(
                "Caste shapes land relations.".encode("utf-8")
            ), "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("refined_text", response.json())

    def test_review_file_rejects_non_txt(self):
        response = self.client.post(
            "/review/file",
            files={"file": ("proposal.pdf", io.BytesIO(b"not a pdf"), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)

    def test_review_file_rejects_non_utf8(self):
        response = self.client.post(
            "/review/file",
            files={"file": ("proposal.txt", io.BytesIO(b"\xff\xfe"), "text/plain")},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
