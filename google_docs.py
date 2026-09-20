"""Optional Google Docs integration using local OAuth credentials.

Set GOOGLE_CLIENT_SECRET_FILE to the OAuth client JSON downloaded from Google Cloud.
The first authorization stores a refresh token in GOOGLE_TOKEN_FILE (default:
token.json). Keep both files private and never commit them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/documents"]
DEFAULT_TOKEN_FILE = "token.json"


class GoogleDocsIntegration:
    """Read and optionally replace the text in a Google Doc."""

    def __init__(
        self,
        client_secret_file: str | None = None,
        token_file: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self.client_secret_file = Path(
            client_secret_file or os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")
        )
        self.token_file = Path(token_file or os.getenv("GOOGLE_TOKEN_FILE", DEFAULT_TOKEN_FILE))
        self.redirect_uri = redirect_uri or os.getenv(
            "GOOGLE_REDIRECT_URI", "http://localhost:8000/google/callback"
        )

    def _credentials(self) -> Credentials | None:
        if not self.token_file.exists():
            return None
        credentials = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self.token_file.write_text(credentials.to_json(), encoding="utf-8")
        return credentials if credentials.valid else None

    def authorization_url(self) -> str:
        if not self.client_secret_file.exists():
            raise FileNotFoundError(
                f"Google OAuth client file not found: {self.client_secret_file}"
            )
        flow = Flow.from_client_secrets_file(str(self.client_secret_file), scopes=SCOPES)
        flow.redirect_uri = self.redirect_uri
        url, _ = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )
        return url

    def finish_authorization(self, code: str) -> None:
        flow = Flow.from_client_secrets_file(str(self.client_secret_file), scopes=SCOPES)
        flow.redirect_uri = self.redirect_uri
        flow.fetch_token(code=code)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(flow.credentials.to_json(), encoding="utf-8")

    def _service(self) -> Any:
        credentials = self._credentials()
        if credentials is None:
            raise PermissionError("Google Docs is not connected. Open /google/auth first.")
        return build("docs", "v1", credentials=credentials, cache_discovery=False)

    def read_document(self, document_id: str) -> str:
        document = self._service().documents().get(documentId=document_id).execute()
        chunks: list[str] = []
        for item in document.get("body", {}).get("content", []):
            paragraph = item.get("paragraph")
            if not paragraph:
                continue
            chunks.extend(
                element.get("textRun", {}).get("content", "")
                for element in paragraph.get("elements", [])
            )
        return "".join(chunks).strip()

    def replace_document(self, document_id: str, text: str) -> None:
        document = self._service().documents().get(documentId=document_id).execute()
        end_index = document.get("body", {}).get("content", [{}])[-1].get("endIndex", 1)
        # Google Docs requires leaving the final newline in the body.
        requests = []
        if end_index > 2:
            requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}})
        requests.append({"insertText": {"location": {"index": 1}, "text": text.rstrip() + "\n"}})
        self._service().documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()
