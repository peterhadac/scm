# Slovak Coffee Map — Brand & Design System

> These rules are binding. When writing or editing any UI code for this project, follow them exactly. Do not substitute generic defaults, introduce new colors, or add icon marks beyond the one defined below.

## Logo — Icon + Wordmark lockup

The logo is an icon mark paired with the typographic wordmark, in that left-to-right order. The wordmark has exactly two lines:

```
Slovak           ← DM Serif Display, letter-spacing −0.02 em
COFFEE MAP       ← DM Sans Light 300, ALL CAPS, letter-spacing +0.28 em
```

The second line is shifted ~5% of the display text size to the right for optical alignment (not mechanical).

**Icon mark:** a coffee-cherry silhouette — an outer droplet shape with a bean-split ellipse cut out of the center and a curved seam through it — on a rounded-square chip (corner radius ≈22% of the chip's side). Defined once in `src/components/LogoIcon.astro` (inline, for the site header) and as standalone assets in `public/favicon.svg` / `public/logo-mark.svg` (browser favicon and larger exports). The icon always renders in fixed **Full colour · Dark** styling — chip `#351E1C`, cherry shell `#FF6037`, bean cutout `#351E1C` — regardless of the surrounding page theme or background; it does not invert for light mode.

**Four approved wordmark colour variants — pick by background:**

| Variant | Background | "Slovak" colour | "COFFEE MAP" colour |
|---|---|---|---|
| Full colour · Dark | `#351E1C` or darker | `#F5F4ED` | `#FF6037` |
| Full colour · Light | `#F5F4ED` or white | `#351E1C` | `#733635` |
| Mono · White | Any dark surface | `#ffffff` | `#ffffff` |
| Mono · Dark | Any light surface | `#351E1C` | `#351E1C` |

No other colour combinations are permitted.

**Minimum size:** 120 px wide (digital, icon + wordmark together) / 30 mm wide (print). Icon alone (favicon/app-icon use): never below 16 px.
**Clear space:** 1× the wordmark's total height on all four sides — no text, logos, or imagery inside this zone.

**Never:**
- Render the logo in a typeface other than DM Serif Display + DM Sans
- Remove letter-spacing from "COFFEE MAP"
- Stretch, distort, or scale the two lines unevenly
- Add shadows, glows, outlines, or emboss effects
- Place the logo on a busy patterned background without a solid clear zone
- Recolour the wordmark outside the four variants above, or recolour the icon mark at all
- Introduce a second icon/symbol mark alongside or instead of the coffee-cherry mark

## Colour Palette

```css
:root {
  --color-toxic-orange:  #FF6037;  /* primary action, "COFFEE MAP" text, buttons */
  --color-black-kite:    #351E1C;  /* dark background, ink, body text on light */
  --color-garnet:        #733635;  /* tertiary accent, "COFFEE MAP" on light bg */
  --color-morning-snow:  #F5F4ED;  /* light canvas, page background */
  --color-amazon-mist:   #ECECDC;  /* secondary background, callout blocks */
  --color-aqua-mist:     #A0C9CB;  /* accent, secondary surfaces */
}
```

No other brand colours. Do not introduce greys, blues, greens, or off-palette neutrals.

MD3 token values (`--md-sys-color-*` etc., seed `#FF6037`/`tonalSpot`) are now a static snapshot in `src/styles/custom.css` rather than generated live by a Starlight plugin (issue #121) — see CLAUDE.md's "Astro Site" section.

## Typography

Two families. Never introduce a third.

| Role | Family | Weight | Tracking |
|---|---|---|---|
| Display / headings / wordmark "Slovak" | DM Serif Display | Regular (400) | −0.02 em |
| ALL CAPS labels / wordmark "COFFEE MAP" | DM Sans | Light (300) | +0.08–0.12 em |
| Body text (14–18 px) | DM Sans | Regular (400) | 0 |
| UI elements, buttons | DM Sans | Medium (500) | 0 |

Google Fonts import: `family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500`.

## Spacing Grid

All spacing is a multiple of **8 px**. Use only: `4 8 16 24 32 48 64 96 px`. Do not introduce arbitrary values like `10px`, `15px`, `20px`, or `36px`.

```
4   → micro gap (icon-to-label, badge padding)
8   → inline padding
16  → card inner padding
24  → component gap
32  → section gutter
48  → section vertical padding
64  → page margin / hero padding
```
