# 02 · Design system — “Editorial Control Room”

Derived from the Cartesia GW Traffic Map reference and reinterpreted for a content factory.
The reference's grammar, not its content: **white paper, black ink, hairline rules, mono metadata,
one lime signal colour, editorial serif display, dense operational tables, black-framed selected
panels, and a diagram of the system's traffic.**

## 1. Foundations

### Colour tokens

| Token | Value | Use |
|-------|-------|-----|
| `--background` | `#FFFFFF` | Page canvas |
| `--paper` | `#FBFBF8` | Warm paper for inset regions |
| `--muted` | `#F5F5F2` | Inactive rows, disabled controls |
| `--foreground` | `#111111` | Primary text, rules, primary buttons |
| `--muted-foreground` | `#888888` | Secondary text |
| `--subtle-foreground` | `#A9A9A4` | Mono captions, axis labels |
| `--border` | `#D5D5D5` | Hairlines |
| `--border-strong` | `#111111` | Section rules, framed panels |
| `--accent` | `#D6FF45` | Signal: active, selected, live, progress, key metric |
| `--accent-soft` | `#F1FFC8` | Selected row tint |
| `--success` | `#A8D83E` | Healthy |
| `--warning` | `#E8B94B` | Degraded / awaiting |
| `--danger` | `#D9534F` | Failed |

Rules:
- Lime is **functional**, never decorative. It marks exactly one thing per region: where the user
  is, what is selected, what is live, how far a pipeline got.
- No gradients, no glass, no coloured shadows. The only shadow is a hard `2px 2px 0 #111` offset used
  on the command palette and popovers.
- Charts: black strokes/fills + lime highlights + hairline `#E9E9E4` grid.

### Typography

| Role | Family | Usage |
|------|--------|-------|
| Display | **Instrument Serif** (fallback Georgia) | Page titles 44–60px, section headings 22–26px. Tight tracking, regular weight. |
| Technical | **IBM Plex Mono** | Uppercase micro-labels (11px, `0.14em` tracking), IDs, timestamps, metric values & captions, status chips, breadcrumbs. |
| Interface | **Geist Sans** (`next/font`) | Nav, buttons, inputs, body copy, table cells. |

Metric values use mono at 30–34px with tabular numerals — the reference's `24 / 88% / 3,720`.
Every metric is a value + mono caption pair (`required_foreground`).

### Space & shape

- 4px base scale; page gutters 28–40px; section rhythm 24/32.
- Radii: `0` for chips, tabs and buttons; `2px` for inputs and panels; `6px` only for large surfaces
  when unavoidable. The reference is square — we stay square.
- Borders: 1px `#D5D5D5` hairlines; 1px black for section underlines and framed panels.
- Selected/active: **black frame** (`1px solid #111`) plus optional lime offset bar on the left;
  never a drop shadow.

## 2. Components

- `PageHeader`: breadcrumbs (mono, uppercase) → serif H1 (with optional italic word) → 1–2 line
  description (max 72ch) → double rule (1px + 6px gap + 1px).
- `MetricStrip`: horizontal bordered grid, each cell has mono label, mono value (can carry a lime
  underline bar), mono caption. Cells separated by hairlines; the strip has black top & bottom rules.
- `Panel`: section title (serif small) + right-side mono action + hairline header, open body.
  No card chrome unless content demands a frame (interactive/selected panels).
- `StatusChip`: mono 10px uppercase, 1px border, leading 6px dot. Variants: `live` (lime fill),
  `idle` (grey), `warning`, `danger`, `ink` (black fill, white text).
- `TagBox`: mono tag with corner brackets on important tags (provider/model), matching the
  dashed provider tags in the reference's request log.
- `DataTable`: 12px mono column headers with leading icon, 1px row rules, hover tint `--muted`,
  right-aligned numerics, optional leading 28px square glyph with lime tint.
- `Tabs`: square segmented buttons; active = filled black.
- `AgentTrafficMap`: the signature diagram. Clients/channels on the left, the factory core in the
  middle (black block, white mono text), agents on the right (selected one framed black with lime
  status), lime dashed routing lines, dotted grid background, `FIG. 01` / caption labels.
- `PipelineRail`: horizontal stages as bordered cells joined by hairlines; completed = lime underline,
  current = black frame + lime fill bar, pending = muted, failed = danger.
- `SetupState`: centred bordered block with mono `NOT CONFIGURED` label, explanation and the exact
  next action link. Replaces fake data anywhere an integration is absent.
- `EmptyState`, `Skeleton` (shimmer-less, muted pulse), `ErrorState`.

## 3. Interaction & motion

- Durations 120–180ms, `ease-out`; only opacity/transform/colour.
- Hover: rows tint, buttons invert (black ↔ white), links underline.
- Command palette `⌘K / Ctrl K`: fuzzy navigation, `G` then `O/C/W/A/…` jumps.
- Keyboard: `?` shortcut sheet, `Esc` closes overlays, focus rings = 1px black + 1px lime offset.
- Toasts for mutations; inline field errors from API validation.

## 4. Responsive

| Breakpoint | Shell |
|-----------|-------|
| ≥1280 | 232px fixed sidebar, 56px topbar, full metric strip |
| 1024–1279 | collapsible sidebar (icon rail), strip scrolls |
| 768–1023 | sidebar as overlay drawer, 2-col grids |
| <768 | drawer + bottom-safe padding, 1-col, tables become stacked record rows with mono keys |

The desktop dashboard is primary; mobile preserves the same editorial identity (same rules, type
contrast and lime signal), not a generic mobile redesign.

## 5. Copy voice

Operational, precise, lower-case mono labels in UI ("awaiting approval", "fig. 01", "24 h spend").
Descriptions are plain and factual. Never "AI magic", never emoji.
