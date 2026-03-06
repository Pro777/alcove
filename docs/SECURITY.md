# 🛡️ Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |

## 🚨 Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Email security reports to the repository owner via GitHub private vulnerability reporting:

1. Go to the [Security tab](https://github.com/Pro777/alcove/security)
2. Click "Report a vulnerability"
3. Describe the issue, steps to reproduce, and impact

You should receive an acknowledgment within 48 hours. We will work with you to understand the scope and coordinate a fix before any public disclosure.

## 🔒 Security model

Alcove is local-first. Your data never leaves your disk.

### What Alcove does

- Stores documents and vectors on local disk only
- Runs a local web server bound to the configured host/port
- Makes no outbound network calls (unless using `sentence-transformers`, which downloads a model on first use)

### What Alcove does not do

- Authentication or authorization (the API is open to anyone who can reach the port)
- Encryption at rest (relies on OS-level disk encryption)
- Input sanitization beyond the documented vectors (see attack surface table below)

### 🎯 Known attack surface

| Surface | Mitigation | Status |
|---------|-----------|--------|
| XSS in search results | `html.escape()` before `<mark>` insertion | Implemented |
| Path traversal via file upload | `Path(filename).name` strips directory components | Implemented |
| File type validation | Extension allowlist on upload | Implemented |
| API is unauthenticated | Bind to localhost in production; do not expose to internet | Documented |
| ChromaDB telemetry | Disabled by default (`ANONYMIZED_TELEMETRY=False`) | Implemented |

### 👷 Operator responsibilities

- Bind `alcove serve` to `127.0.0.1` if not behind a reverse proxy
- Use OS-level disk encryption for data at rest
- Keep dependencies updated (`pip install --upgrade alcove-search`)
- Do not expose the API to the public internet without adding authentication

## ⚠️ Non-claims

Alcove is not a security product. It does not provide enterprise IAM, compliance controls, or audit logging.
