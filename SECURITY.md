# Security Policy

## Supported version

Security fixes are applied to the current `main` branch. Older snapshots are
not maintained as separate release lines.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Security** tab when
available. Do not open a public issue containing credentials, private research
material, unpublished manuscripts, or exploit details. Include the affected
endpoint or workflow, reproduction steps, impact, and any suggested mitigation.

## Data-handling notes

- Deterministic editor mode processes text inside the running application and
  does not call an external model provider.
- Text is sent to an OpenAI-compatible provider only when `LLM_API_KEY` is
  configured and the request explicitly enables model enhancement.
- Provider credentials remain server-side and are never included in capability
  or review responses.
- Revision receipts contain SHA-256 text digests rather than manuscript text.
  Digests can still identify known text, so exported receipts should be treated
  as research metadata.
- Uploaded files are limited to UTF-8 `.txt` content and bounded by
  `MAX_UPLOAD_BYTES`.
- Do not commit `.env`, provider keys, Google OAuth secrets, access tokens, or
  copyrighted source documents without permission.

Model output is untrusted. Citation and structural safeguards reduce risk but
do not replace researcher verification.
