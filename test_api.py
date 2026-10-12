import io
import unittest

from fastapi.testclient import TestClient

from api import MAX_TEXT_CHARS, MAX_UPLOAD_BYTES, app


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["max_text_chars"], MAX_TEXT_CHARS)

    def test_editor_home_serves_web_application(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ScholarFlow Academic Editor", response.text)

    def test_editor_assets_are_available(self):
        response = self.client.get("/assets/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/editor/rewrite", response.text)

    def test_editor_capabilities_do_not_expose_credentials(self):
        response = self.client.get("/editor/capabilities")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default_profile"], "standard")
        self.assertIn("llm_available", payload)
        self.assertNotIn("api_key", payload)

    def test_editor_rewrite_returns_revision_report(self):
        response = self.client.post(
            "/editor/rewrite",
            json={
                "text": "It is important to note that caste shapes land relations (Gupta, 2000).",
                "profile": "standard",
                "use_llm": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "deterministic-local")
        self.assertFalse(payload["used_llm"])
        self.assertIn("stats", payload)
        self.assertIn("literature_review", payload)
        self.assertNotIn("important to note", payload["refined_text"].lower())

    def test_editor_rewrite_rejects_unknown_profile(self):
        response = self.client.post(
            "/editor/rewrite",
            json={"text": "Caste shapes access to land.", "profile": "unknown"},
        )
        self.assertEqual(response.status_code, 400)

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
        for key in (
            "refined_text",
            "grammar_and_style",
            "literature_review",
            "suggestions",
            "safeguards",
        ):
            self.assertIn(key, payload)
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

    def test_review_rejects_none_profile(self):
        response = self.client.post(
            "/review",
            json={"text": "Caste shapes land relations.", "profile": None},
        )
        self.assertEqual(response.status_code, 422)

    def test_review_rejects_text_over_limit(self):
        response = self.client.post(
            "/review",
            json={"text": "x" * (MAX_TEXT_CHARS + 1)},
        )
        self.assertEqual(response.status_code, 422)

    def test_review_file_accepts_utf8_txt(self):
        response = self.client.post(
            "/review/file",
            files={
                "file": (
                    "proposal.txt",
                    io.BytesIO("Caste shapes land relations.".encode("utf-8")),
                    "text/plain",
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("refined_text", response.json())

    def test_review_file_rejects_non_txt(self):
        response = self.client.post(
            "/review/file",
            files={
                "file": (
                    "proposal.pdf",
                    io.BytesIO(b"not a pdf"),
                    "application/pdf",
                )
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_review_file_rejects_non_utf8(self):
        response = self.client.post(
            "/review/file",
            files={
                "file": (
                    "proposal.txt",
                    io.BytesIO(b"\xff\xfe"),
                    "text/plain",
                )
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_review_file_rejects_oversized_upload(self):
        response = self.client.post(
            "/review/file",
            files={
                "file": (
                    "proposal.txt",
                    io.BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1)),
                    "text/plain",
                )
            },
        )
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
