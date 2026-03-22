# ada-audit

Static ADA Title II / WCAG 2.1 AA accessibility checker for HTML files.

Performs lint-style analysis with no external dependencies — uses Python's
standard-library `html.parser` only.

## Usage

```bash
# Audit a single file
python tools/ada-audit/audit.py page.html

# Audit multiple files
python tools/ada-audit/audit.py src/**/*.html

# Exit non-zero only on hard errors (default)
python tools/ada-audit/audit.py page.html --fail-on errors

# Exit non-zero on any violation (useful in strict CI)
python tools/ada-audit/audit.py page.html --fail-on violations

# JSON report
python tools/ada-audit/audit.py page.html --format json
```

## Rules

| Rule ID | Severity | WCAG | Description |
|---|---|---|---|
| `img-alt` | error | 1.1.1 | `<img>` missing `alt` attribute |
| `img-alt-empty` | warning | 1.1.1 | `<img alt="">` — only valid for decorative images |
| `input-label` | error | 1.3.1 | Form control has no associated label |
| `heading-empty` | error | 2.4.6 | Empty or whitespace-only heading |
| `document-lang` | error | 3.1.1 | `<html>` missing `lang` attribute |
| `link-text-empty` | error | 2.4.4 | Link has no text content |
| `link-text-vague` | warning | 2.4.4 | Link text is vague ("click here", "read more", etc.) |
| `button-text` | error | 4.1.2 | Button has no accessible text |

`aria-label`, `aria-labelledby`, and `title` are accepted as valid label sources for all applicable rules.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No violations (or `--fail-on never`) |
| 1 | Violations found matching `--fail-on` threshold |

## Dependencies

No external dependencies — stdlib only.
