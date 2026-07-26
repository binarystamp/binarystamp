# Assets

Splash screen, 16:9.

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
