# Accessibility

Alcove targets **WCAG 2.1 Level AA** compliance for its web UI.

## Theme Support

The web UI includes a three-state theme toggle (auto / light / dark):

- **Auto**: follows the operating system preference via `prefers-color-scheme`
- **Light**: warm parchment palette, optimized for readability
- **Dark**: default dark palette

Theme preference is saved in `localStorage` and applied before the stylesheet loads to prevent flash of unstyled content (FOUC).

## Color Contrast

All foreground/background color pairs have been audited against WCAG AA requirements (4.5:1 for normal text, 3:1 for large text).

**Dark theme verified pairs:**

| Foreground | Background | Ratio | Status |
|-----------|-----------|-------|-------|
| text `#c9d1d9` | bg-body `#1a1a2e` | 9.73:1 | Pass |
| text `#c9d1d9` | bg-card `#0d1117` | 12.21:1 | Pass |
| muted `#97a0aa` | bg-body `#1a1a2e` | 6.51:1 | Pass |
| muted `#97a0aa` | bg-card `#0d1117` | 8.17:1 | Pass |
| amber `#d2a56e` | bg-body `#1a1a2e` | 5.95:1 | Pass |
| amber `#d2a56e` | bg-card `#0d1117` | 7.47:1 | Pass |
| cyan `#79c0ff` | bg-card `#0d1117` | 8.19:1 | Pass |
| green `#7ee787` | bg-card `#0d1117` | 10.04:1 | Pass |
| amber-badge `#ebbe87` | amber-glow `#d2a56e40` | 5.23:1 | Pass |

**Light theme** uses adjusted values (`#896512` amber, `#636058` muted, `#2d2a26` text on `#f5f0eb` / `#ffffff` backgrounds) that also meet WCAG AA.

## Keyboard Navigation

| Key | Action |
|-----|--------|
| Tab | Move focus through interactive elements (skip link, theme toggle, search input, search button, upload zone, back link) |
| Enter / Space | Activate the upload zone (opens file chooser) or cycle theme toggle |
| Enter | Submit the search form |
| Escape | No custom handler; browser-native behavior (dismiss dialogs, cancel file chooser) |

The skip link is the first focusable element in the DOM. Activating it moves focus directly to `#main-content`, bypassing the header.

## Screen Reader Support

Tested landmarks and regions:

- `<html lang="en">` sets document language at root
- Skip link (`<a href="#main-content">`) is first in DOM, visible on focus
- `<header>`, `<main>`, `<footer>` use native landmark roles
- Search form uses `role="search"` with a visible `<label>` (`.sr-only`) linked to the input via `for`/`id`
- Upload zone uses `role="button"`, `tabindex="0"`, `aria-label`, `aria-describedby` pointing to the supported-formats note
- Upload status uses `aria-live="polite"`, `aria-atomic="true"`, `aria-busy` toggled during file processing
- Results region uses `role="region"`, `aria-label="Search results"`, `aria-live="assertive"` so new results are announced immediately
- Result cards use `aria-describedby` pointing to per-card metadata (source, file type badge, relevance score)
- Theme toggle button uses `aria-label="Toggle theme"`

Screen readers verified with:
- VoiceOver (macOS / Safari): navigation by landmark, form interaction, live region announcements
- NVDA (Windows / Firefox): browse mode, forms mode, live region announcements

## Known Limitations

- No automated WCAG test in CI yet. A template-attribute test exists in `tests/test_accessibility.py`; browser-level axe integration (pytest-axe / pa11y) is planned.
- Mobile screen reader testing (TalkBack, VoiceOver iOS) has not been performed.
