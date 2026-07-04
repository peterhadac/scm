# Slovak Coffee Map — Brand Spec

Extracted from the user-supplied palette + `src/styles/custom.css` token system.

## Color tokens

| Token       | Hex / Value | Role |
|---|---|---|
| `--bg`      | `#F5F4ED`   | Morning Snow — page background (light) |
| `--surf`    | `#FFFFFF`   | Card / table row surface |
| `--surf-var`| `#ECECDC`   | Amazon Mist — table header, surface variant |
| `--fg`      | `#1C1B17`   | Body text on Morning Snow |
| `--fg-muted`| `#7A7869`   | Muted / secondary text, outline |
| `--border`  | `#CCCBB9`   | Card / table borders |
| `--border-lite` | `#E0DFCF` | Hairline dividers |
| `--accent`  | `#FF6037`   | Toxic Orange — primary: eyebrow, "best value" badge, focus rings |
| `--washed`  | `#2A5A5B`   | Aqua Mist dark — washed-process badge text |
| `--washed-bg` | `#C8ECED` | Aqua Mist light — washed-process badge bg |
| `--natural` | `#733635`   | Garnet — natural-process badge text |
| `--natural-bg`| `#FFD9D8`| Garnet light — natural-process badge bg |
| `--honey`   | `#7A3000`   | Honey-process badge text (derived from Toxic Orange) |
| `--honey-bg`| `#FFE5CF`   | Honey-process badge bg |

## OKLch equivalents (for `:root` in seed template)

```css
:root {
  --bg:      oklch(97% 0.008 87);   /* Morning Snow */
  --surface: oklch(100% 0 0);
  --fg:      oklch(20% 0.015 80);
  --muted:   oklch(52% 0.012 80);
  --border:  oklch(84% 0.01 80);
  --accent:  oklch(62% 0.20 35);    /* Toxic Orange */
}
```

## Typography

```
--font-serif: 'Iowan Old Style', 'Charter', Georgia, serif
--font-sans:  -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif
--font-mono:  'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace
```

- **Display / brand**: serif (Georgia stack) — numbers in stats bar, page title, nav brand
- **Body / UI**: system sans — table cells, labels, filter controls
- **Metadata / code / badges**: monospace — column headers (UPPERCASE 0.625rem, tracking 0.1em), badge text, price cells

## Layout posture rules

1. **Morning Snow background, not white** — the page canvas is warm, not neutral. White is reserved for card surfaces (table rows, stats bar, filter dropdowns).
2. **Amazon Mist for headers** — `#ECECDC` as the table header background and sticky toolbar overlay creates a clear section hierarchy without heavy borders.
3. **Radius 12px for containers, 4px for inputs, full (9999px) for badges / pills** — three tiers only.
4. **Accent budget = 2** — Toxic Orange (#FF6037) appears at most twice per screen: (1) the "best value" badge, (2) the page eyebrow OR a single focus/hover state. Never use it as a background fill.
5. **Process badges are semantic, not decorative** — Aqua Mist = washed (clean), Garnet = natural (earthy), Orange-derived = honey. Badge border-color is always 50% opacity of the badge text color.
