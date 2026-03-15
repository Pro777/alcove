# Security

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |

## Reporting a vulnerability

Do not open a public issue for security vulnerabilities.

Use GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/Pro777/alcove/security)
2. Click "Report a vulnerability"
3. Describe the issue, steps to reproduce, and impact

You should receive an acknowledgment within 48 hours. We will work with you to understand the scope and coordinate a fix before any public disclosure.

## Security model

Local disk only. No outbound network calls. No telemetry. No account to create.

We do not want your data. Alcove only retrieves and returns matching documents (does not generate or fabricate content). The [architecture](ARCHITECTURE.md#boundary) assumes the operator owns the hardware, controls the storage, and decides what enters the index.

### What Alcove does

Stores documents and vectors on local disk only. Runs a local web server bound to the configured host and port. Makes no outbound network calls unless using `sentence-transformers`, which downloads a model on first use and then runs locally.

### What Alcove does not do

Authentication or authorization. The API is open to anyone who can reach the port.

Encryption at rest. Alcove relies on OS-level disk encryption.

Input sanitization beyond the documented attack surface below.

### Known attack surface

| Surface | Mitigation | Status |
|---------|-----------|--------|
| XSS in search results | `html.escape()` before `<mark>` insertion | Implemented |
| Path traversal via file upload | `Path(filename).name` strips directory components | Implemented |
| File type validation | Extension allowlist on upload | Implemented |
| API is unauthenticated | Bind to localhost; put a reverse proxy in front for auth | Documented |
| ChromaDB telemetry | Disabled by default (`ANONYMIZED_TELEMETRY=False`) | Implemented |

### Operator responsibilities

Bind `alcove serve` to `127.0.0.1` if not behind a reverse proxy (see [operations guide](OPERATIONS.md#web-ui-and-api) for details). Use OS-level disk encryption for data at rest. Keep dependencies updated. Do not expose the API to the public internet without adding authentication.

[Alcove handles search. You handle custody.](../WHY.md)

## Non-claims

Alcove is not a security product. It does not provide enterprise IAM, compliance controls, or audit logging. If you need those things, they belong in the infrastructure around Alcove, not inside it.
