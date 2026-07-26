# Assets

## Logo

Square mark, 512×512.

| File | Size | Use |
|------|------|-----|
| `logo.svg` | vector | Dark tile — the master |
| `logo.png` | 512×512 | Dark raster |
| `logo@2x.png` | 1024×1024 | Dark, for app-icon slots that want 1024 |
| `logo-light.svg` / `.png` / `@2x.png` | | Light variant |
| `logo-mark.svg` | vector | Transparent, `currentColor` — for inlining beside text, as the app header does |

The mark is the app header's, scaled proportionally: the rounded rect occupies
62.5% of the tile, leaving the margin an icon needs, and the inner ratios
(corner radius, circle radius, stroke weight, diagonal endpoints) are derived
from the 32px original rather than eyeballed.

### A note on the alternative

Isolated at icon size, a circle with a diagonal through its centre reads as a
prohibition sign — "no entry" — which is the opposite of what the product
means. It is much weaker in the header, where the mark is small and sits beside
the wordmark.

`logo-alt.*` keeps every proportion but carries the diagonal to the corners of
the frame and lets the circle sit **over** it, filled with the background. The
circle then reads as a seal laid on a stroke rather than a bar drawn through a
circle. Same geometry, no negation.

It is not the default, because changing a brand mark is not a change to make
silently. To adopt it, replace `logo.svg` with `logo-alt.svg` and update the
header mark in `app/frontend/index.html` to match.

Note that the alternative's circle is filled with the page background, so it
needs the correct fill per theme — which is why there is no transparent
`currentColor` version of it.

## Splash screen

16:9.

| File | Size | Use |
|------|------|-----|
| `splash.svg` | vector | Dark — the master. Scales to any size. |
| `splash.png` | 640×360 | Dark raster |
| `splash@2x.png` | 1280×720 | Dark, for retina and slide decks |
| `splash-light.svg` | vector | Light variant |
| `splash-light.png` | 640×360 | Light raster |
| `splash-light@2x.png` | 1280×720 | Light, retina |

Prefer the SVG wherever vectors are accepted — it stays crisp at any size and
is under 3 KB.

## Design notes

Follows the app's own palette and geometry rather than a generic template:
`#0a0a0a` on dark, `#ffffff` on light, no gradients or shadows, everything
built from circles, rectangles and straight lines.

- **Corner ticks** are registration marks — the alignment marks on a printing
  plate. A quiet nod to stamping.
- **Concentric rings** behind the mark read as the impression a stamp leaves.
- **The hex string** is `sha256("BinaryStamp")`, the product applied to itself.
- **The footer row** names the stack the project is built on.

Text uses the system UI font stack, so the SVG picks up the viewer's native
font exactly as the app does.

## Regenerating the PNGs

The SVGs are the source; the PNGs are rendered from them. This box has no
system fonts, so the renderer is given open-licensed ones explicitly —
otherwise text silently fails to draw.

```bash
mkdir -p /tmp/render && cd /tmp/render && npm init -y
npm install @resvg/resvg-js @expo-google-fonts/inter @expo-google-fonts/roboto-mono
```

```js
// r.cjs — node r.cjs <src.svg> <out.png> <width>
const { Resvg } = require('@resvg/resvg-js');
const fs = require('fs');
const [src, out, width] = process.argv.slice(2);
const r = new Resvg(fs.readFileSync(src, 'utf8'), {
    fitTo: { mode: 'width', value: Number(width) },
    font: {
        fontFiles: [
            'node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf',
            'node_modules/@expo-google-fonts/inter/500Medium/Inter_500Medium.ttf',
            'node_modules/@expo-google-fonts/inter/600SemiBold/Inter_600SemiBold.ttf',
            'node_modules/@expo-google-fonts/roboto-mono/400Regular/RobotoMono_400Regular.ttf',
        ],
        loadSystemFonts: false,
        defaultFontFamily: 'Inter',
    },
});
fs.writeFileSync(out, r.render().asPng());
```

Inter and Roboto Mono are SIL Open Font License, used only to rasterize. They
are not redistributed here and are not required to view the SVG, which falls
back to the system UI font.
