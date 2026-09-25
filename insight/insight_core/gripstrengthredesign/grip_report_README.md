# Hand Grip Strength — nudge PNG

Replaces the current 300 × 296 grip-strength nudge PNG.
**PNG only — no PDF in scope.**

```
grip_report/
├── template.html      # Jinja2 template, the design itself
├── render.py          # template + data -> 1024x1536 PNG
├── assets/
│   ├── hero.jpg       # 617x560  dynamometer shot
│   ├── logo.png       # 310x180  Insight lockup
│   └── mountain.png   # 362x105  quote-block backdrop
└── README.md
```

## Run it

```bash
pip install jinja2 playwright && playwright install chromium

python render.py --out arun_2026-09-18.png \
  --test-date "Sep 18, 2026" --name "Dr Pavan" \
  --right 48.1 --left 42.7 \
  --right-label Average --left-label Average
```

Import it instead of shelling out:

```python
from render import render
render({
    "test_date": "Sep 18, 2026",
    "name": "Dr Pavan",
    "test_name": "Hand Grip Strength",
    "right": "48.1", "left": "42.7",          # always pre-formatted to 1dp
    "right_label": "Average", "left_label": "Good",
}, pathlib.Path("out.png"))
```

## Canvas: 1024 × 1536, fixed

2:3, matching the reference. **Use pixels, not DPI.** DPI is print metadata and
WhatsApp ignores it; WhatsApp also re-encodes anything past ~1600px on the long
edge, so 1536 passes through close to untouched and a 2x render would only get
downscaled and recompressed. Render at 1x.

The layout is absolutely positioned at these coordinates. It is not responsive
and is not meant to be.

## Template slots

Seven variables, all strings. Everything else in the template is literal text.

| Slot | Example | Notes |
|---|---|---|
| `test_date` | `Sep 18, 2026` | `%b %-d, %Y` |
| `name` | `Dr Pavan` | Person assessed. Label reads **NAME** |
| `test_name` | `Hand Grip Strength` | Fixed today; a slot so other protocols reuse the template |
| `right` / `left` | `48.1` / `42.7` | **Pre-format to 1dp before passing.** The template does no rounding |
| `right_label` / `left_label` | `Average` | Existing classifier output. Both hands always labelled |

The footer (`Arun Alex David`, `97911 72562`) is **static trainer detail**,
hard-coded in the template — not client data, not a slot.

## Fonts

Three Google Fonts, pulled over the network at render time:

| Role | Family |
|---|---|
| Display — title, kg numbers | Archivo Black |
| Body, labels | Archivo 400–700 |
| Script — "Stronger / Healthier / Happier You" | Dancing Script 600 |

`render.py` waits for `networkidle` so they land before the screenshot. **If the
renderer will run somewhere without outbound network** (CI, a locked-down Cloud
Run image), download the four TTFs into `assets/fonts/` and swap the
`<link>` in `template.html` for local `@font-face` rules — otherwise you get
silent fallback to system sans and the whole thing looks wrong.

Letter-spacing is load-bearing throughout (micro labels run 2.2–11px tracked).
Don't normalise it away.

## Layout landmarks

| Section | Top | Height |
|---|---|---|
| Masthead | 0 | 487 |
| └ hero panel | 0 | 478 (527 wide, flush top-right) |
| Meta strip | 487 | 129 (full bleed) |
| Hand cards | 628 | ~255 |
| What this means | ~895 | ~300 |
| Quote | ~1207 | 170 |
| Footer | bottom | ~160 |

**The hero is not a rectangle.** It is a 527 × 478 panel with a V-shaped left
edge cut into it, traced off the reference: starts at x=612 on the top edge,
narrows to an apex at x=497 / y=225, widens back to x=685 at the bottom.

```css
clip-path: polygon(21.8% 0, 100% 0, 100% 100%, 35.7% 100%, 0 47.1%);
```

The grey wedge behind it is **the identical shape shifted 135px left** — same
width, same height, same clip-path. Do not rebuild it as a differently-sized
polygon with the same percentages; the diagonals then diverge instead of
running parallel.

The photo carries white text over it, so it also has a left-to-right scrim
(`rgba(20,33,46,0.10 -> 0.78)`) plus a text-shadow. Swapping in a lighter
photo means re-checking contrast in the two text zones.

## Colour tokens

| Token | Hex | Use |
|---|---|---|
| ink | `#14212E` | headlines, hero panel |
| ink soft | `#24333F` | "WHAT THIS MEANS" tab |
| body | `#43505D` | secondary text |
| label | `#67727E` | all-caps micro labels |
| band | `#ECEFF1` / `#F1F3F5` | meta strip / panels |
| crimson | `#8B1F2C` | right hand |
| crimson tint | `#FBEEF0` | right card body |
| pine | `#14453C` | left hand |
| pine tint | `#EAF4EF` | left card body |
| accent | `#8E1F2F` | rules, phone icon |

Icon row: `#9B2436` / `#2E7D5B` / `#2C6FA8` / `#C96A2B` on tints
`#FAEEF0` / `#E8F4EE` / `#E7F0F8` / `#FBF0E5`.

All icons are inline SVG on a 24×24 viewBox, outline-only, `stroke-width: 1.6`,
round caps and joins. No icon font, no emoji. Keep that consistent if you add
one — the row reads as a set because every glyph shares those values.

## Known edges

- **`test_name` wraps** at the default value because the meta strip is three
  equal columns and this is the longest. Harmless today; if it bothers you,
  widen column 3 rather than shrinking the type.
- **Long `name` values** are the only real overflow risk. Cap around 22
  characters before it collides with the divider.
- 3-digit kg values (`100.0`) still fit.
- `mountain.png` has a white background, not transparency — it relies on
  `mix-blend-mode: multiply` to sit on the grey panel. If you ever place it on
  a non-grey background, cut a real alpha channel instead.
- Meta-strip dividers are hand-drawn SVG strokes (from the design tool), not
  CSS borders. I removed the duplicate CSS borders so they don't double up.

## Licensing

`hero.jpg` is a stock image. Confirm the licence covers commercial use and
redistribution — these go to clients over WhatsApp.

## Design source

The editable design lives in a Claude Design canvas. `template.html` is a
mechanical conversion of it: the `<x-dc>` wrapper, the `DCLogic` script and the
`<helmet>` block are stripped, `/_blob/` asset ids are rewritten to `assets/`
paths, and the `{{slot}}` holes happen to be valid Jinja2 already.

If the design changes there, re-export rather than hand-patching this file.
