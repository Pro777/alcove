# Theming

> **Alcove is a retrieval system** — it matches and returns documents; it does not generate text.
> **Authentication is not built-in.** If you need access control, place Alcove behind a reverse
> proxy (nginx, Caddy, etc.) that handles auth before requests reach the API.

Alcove's web UI uses CSS custom properties (variables) for all color and typography values.
Theming is entirely CSS-based — no build step required.

---

## Built-in themes

The UI ships with two themes and an automatic mode:

| Mode | How to activate | Description |
|------|-----------------|-------------|
| `auto` (default) | `localStorage` key absent | Follows the OS `prefers-color-scheme` setting |
| `dark` | `data-theme="dark"` on `<html>` | Dark background, amber accent |
| `light` | `data-theme="light"` on `<html>` | Warm off-white background, brown accent |

The theme toggle button in the top-right corner cycles through `auto → light → dark`.
The selection persists in `localStorage` under the key `alcove-theme`.

---

## CSS custom properties

All visual tokens are declared in `alcove/web/static/style.css` under the `:root` selector.
Override any of them in a custom stylesheet to retheme the UI:

```css
/* Custom brand colors — paste into your custom.css */
:root {
  --bg-body:      #0f172a;   /* page background */
  --bg-surface:   #1e293b;   /* card and input backgrounds */
  --bg-card:      #1e293b;
  --border:       rgba(99, 179, 237, 0.14);
  --border-hover: rgba(99, 179, 237, 0.40);
  --gold:         #63b3ed;   /* primary accent — "gold" in default theme */
  --gold-dim:     rgba(99, 179, 237, 0.50);
  --gold-faint:   rgba(99, 179, 237, 0.08);
  --gold-glow:    rgba(99, 179, 237, 0.18);
  --text:         #f1f5f9;
  --text-muted:   rgba(241, 245, 249, 0.45);
  --text-excerpt: rgba(99, 179, 237, 0.75);
  --font-sans:    'Inter', sans-serif;
}
```

### Full token reference

| Token | Default (dark) | Purpose |
|-------|---------------|---------|
| `--bg-body` | `#1e1a14` | Page background |
| `--bg-surface` | `#2a241d` | Input fields, sidebars |
| `--bg-card` | `#241f18` | Result cards |
| `--border` | `rgba(211,166,111,0.12)` | Card and input borders |
| `--border-hover` | `rgba(211,166,111,0.35)` | Focus and hover borders |
| `--gold` | `#d3a66f` | Primary accent — buttons, links, highlights |
| `--gold-dim` | `rgba(211,166,111,0.50)` | Secondary accent |
| `--gold-faint` | `rgba(211,166,111,0.08)` | Subtle highlight backgrounds |
| `--gold-glow` | `rgba(211,166,111,0.18)` | Glow effects |
| `--text` | `#f5f0e8` | Primary text |
| `--text-muted` | `rgba(245,240,232,0.45)` | Secondary text, metadata |
| `--text-excerpt` | `rgba(211,166,111,0.75)` | Excerpt text in result cards |
| `--scrollbar` | `#41372a` | Scrollbar thumb |
| `--error` | `#f87171` | Error states |
| `--success` | `#6ee7b7` | Success states |
| `--font-sans` | `'Space Grotesk', system` | UI typeface |
| `--font-mono` | `'SF Mono', 'Cascadia Code', ...` | Code blocks |
| `--radius-sm` | `0.375rem` | Small corner radius |
| `--radius-md` | `0.5rem` | Medium corner radius |
| `--radius-lg` | `0.75rem` | Large corner radius |
| `--radius-xl` | `1rem` | Extra-large corner radius |

---

## Applying a custom stylesheet

Inject a custom stylesheet after the default one in `alcove/web/templates/base.html`:

```html
<link rel="stylesheet" href="{{ base_url }}/static/style.css">
<link rel="stylesheet" href="{{ base_url }}/static/custom.css">
```

Place `custom.css` in `alcove/web/static/`. It overrides any tokens you redefine and
leaves the rest of the design system intact.

---

## Customising the header

The header logo, site title, and tagline are plain HTML in `base.html`:

```html
<div class="logo-mark" aria-hidden="true">A</div>
<h1 class="site-title">Alcove</h1>
<p class="site-tagline">Local-first retrieval</p>
```

Replace or wrap `base.html` in a Jinja2 template to change these for a deployment. The
congress template (`alcove/web/templates/congress/base.html`) is an example of a
collection-specific layout that extends `base.html`.

---

## Disabling the theme toggle

The toggle cycles through `auto / light / dark`. To lock a deployment to a single theme,
remove the `<button class="theme-toggle">` block from `base.html` and add a fixed
`data-theme` attribute to the opening `<html>` tag:

```html
<html lang="en" data-theme="light">
```

---

## Typography

> **Offline-first note:** Alcove is designed to operate without external network
> access. The Google Fonts CDN references in the demo HTML files are for
> convenience only. Production deployments should self-host fonts or use a
> system font stack (see below).

**Recommended for production: use a system font stack (no external requests).**
The demo files load [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk)
from the Google Fonts CDN as an optional convenience enhancement — this is not the
default for deployments. To remove the external dependency and use system fonts:

1. Remove the `<link rel="preconnect">` and `<link href="https://fonts.googleapis.com">` lines from `base.html`.
2. Override `--font-sans` in your custom CSS to point to your font stack.

---

## See also

- `alcove/web/static/style.css` — full CSS source
- `alcove/web/templates/base.html` — base HTML template
- [ACCESSIBILITY.md](../ACCESSIBILITY.md) — contrast and accessibility requirements
