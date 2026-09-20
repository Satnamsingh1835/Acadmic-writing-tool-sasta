# Google Docs integration

The API can read a Google Doc, send its text through the existing deterministic review pipeline, and optionally replace the document with the refined text. Google Docs access is optional.

## One-time Google Cloud setup

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable **Google Docs API**.
4. Configure the OAuth consent screen. For personal use, **External** is sufficient; add your Google account as a test user if requested.
5. Create an OAuth client ID for a **Desktop app** and download the JSON file.
6. Save it locally as `client_secret.json` beside the API, or set `GOOGLE_CLIENT_SECRET_FILE` to its path.
7. Install the optional dependencies:

```bash
python -m pip install -r requirements.txt -r requirements-google.txt
```

## Start and connect

Start the API as usual:

```bash
python -m uvicorn api:app --reload
```

Open this URL in your browser:

```text
http://localhost:8000/google/auth
```

Approve access with Google. Google redirects to `/google/callback`, and the API stores a refresh token in `token.json`. Do not commit `client_secret.json` or `token.json`; add them to `.gitignore`.

## Use a document

Copy the document ID from its URL:

```text
https://docs.google.com/document/d/DOCUMENT_ID/edit
```

Review without changing the document:

```bash
curl -X POST http://localhost:8000/google/review \\
  -H "Content-Type: application/json" \\
  -d '{"document_id":"DOCUMENT_ID","profile":"standard","write_back":false}'
```

Review and replace the document with the refined text:

```bash
curl -X POST http://localhost:8000/google/review \\
  -H "Content-Type: application/json" \\
  -d '{"document_id":"DOCUMENT_ID","profile":"standard","write_back":true}'
```

`write_back` defaults to `false`, so the document is protected unless you explicitly enable replacement. Always keep a copy before using write-back.

## Important limitations

- This integration replaces the document body as plain text; rich formatting, comments, footnotes, and inline drawings are not preserved.
- The application uses the Google Docs OAuth scope, so treat the token as sensitive.
- The editor changes language only; review citations and meaning manually.
- For a deployed server, set `GOOGLE_REDIRECT_URI` to your HTTPS callback URL and configure the same URL in Google Cloud.
