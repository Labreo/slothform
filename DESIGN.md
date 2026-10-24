# SlothForm — Design System & Style Reference

> **Style Reference**: Sourced from [Refero Styles — AgentQL Design System](https://styles.refero.design/style/d5307f56-76de-4d13-9741-f969c42e9aa5)  
> **Theme**: Dark AI Command Center / Aurora Glow over a Midnight Terminal  
> **Aesthetic Register**: Deep-space developer command deck, near-black multi-layered canvas, tightly letter-spaced geometric headings, violet aurora radial ambient glows, crisp hairline borders, and instrument-panel telemetry.

---

## 1. Style Reference Prompt (Refero Styles: AgentQL)

```markdown
# AgentQL — Style Reference
> Aurora glow over a midnight terminal
**Theme:** dark

AgentQL operates in a deep-space command-center register: near-black canvas, tightly letter-spaced Figtree display headlines, and a single pair of violet aurora glows (purple + pink radial gradients) that bleed from the hero into the background. The interface is overwhelmingly achromatic — white type, cool-gray secondary text, hairline borders in dark navy — with color reserved for two specific jobs: product surface highlights (a few cards lift into a slightly violet-tinted dark) and accent CTAs (a single blue→violet gradient pill). Components sit on flat dark surfaces with generous padding, rounded to 12px, and rely on heavy dark drop shadows rather than glow for depth. The overall feel is closer to a dark IDE theme than a marketing site — Inter carries the UI, IBM Plex Mono owns code blocks, and Figtree whispers the headlines at weight 500 with tight tracking.

## Tokens — Colors
| Name | Value | Token | Role |
|------|-------|-------|------|
| Void | `#0b0c0e` | `--color-void` | Deepest surface layer, page base under hero — the floor of the dark stack |
| Abyss | `#0e111b` | `--color-abyss` | Primary page canvas and most card backgrounds; cool blue-black anchors the whole system |
| Deep Sea | `#0d172b` | `--color-deep-sea` | Elevated card surface — sits one step above the canvas, used for feature and pricing cards |
| Cobalt Panel | `#12244f` | `--color-cobalt-panel` | Highlighted card surface for feature spotlights; a violet-tinted lift that breaks the monochrome rhythm |
| Frosted Lilac | `#85a6e9` | `--color-frosted-lilac` | Violet wash for highlight backgrounds, decorative bands, and soft emphasis |
| Signal Blue | `#2862d7` | `--color-signal-blue` | Vivid blue link and accent text — the sharp chromatic punctuation against all the dark navy |
| Pulse Violet | `#305fbd` | `--color-pulse-violet` | Mid-saturation violet-blue used in code-syntax blocks and gradient stops |
| Aurora Purple | `radial-gradient(79.43% 95.88% at 38.94% -53.46%, rgba(98, 95, 255, 0.38) 0px, rgba(0, 0, 0, 0))` | `--color-aurora-purple` | Ambient lighting over hero and command sections |
| Plasma Pink | `radial-gradient(27.99% 22.08% at 72.13% 103.46%, rgba(255, 125, 218, 0.33) 0px, rgba(0, 0, 0, 0))` | `--color-plasma-pink` | Secondary hero glow bleeding from bottom-right — warm counterpoint to aurora purple |
| Quartz | `#ffffff` | `--color-quartz` | Primary text and primary CTA fill — high-contrast white against the dark canvas |
| Ash | `#abaebb` | `--color-ash` | Secondary text and subtle hairline borders — the most-used neutral after white |
| Mist | `#c7c9d1` | `--color-mist` | Tertiary text, muted descriptions, helper copy |
| Slate | `#3c3f44` | `--color-slate` | Muted borders and disabled state outlines |
| Obsidian Edge | `#172540` | `--color-obsidian-edge` | Primary border color on cards and buttons — defines component outlines |
| Inkline | `#151e32` | `--color-inkline` | Subtle card borders, slightly lighter than Obsidian Edge for inner nesting |
| Sapphire Hairline | `#24375a` | `--color-sapphire-hairline` | Lighter violet-tinted border for dividers and section separators |

## Tokens — Typography
- **Headings / Display**: `Figtree`, ui-sans-serif, system-ui (weight 500/600, letter-spacing -0.02em to -0.03em)
- **Body & Interactive UI**: `Inter`, ui-sans-serif, system-ui (weight 300 for precision, 400 for standard copy, 500 for navigation/pills)
- **Monospace / Code / Telemetry**: `IBM Plex Mono`, ui-monospace, Menlo, Monaco, Consolas (weight 400, 13px, letter-spacing normal)

### Type Scale (Minor Third 1.2 from 20px base)
| Role | Family | Weight | Size | Line Height | Letter Spacing | Token |
|------|--------|--------|------|-------------|----------------|-------|
| body | Inter | 300/400 | 16px | 1.5 | -0.32px | `--text-body` |
| subheading | Inter | 500 | 20px | 1.38 | -0.54px | `--text-subheading` |
| heading-sm | Figtree | 600 | 28px | 1.25 | -0.56px | `--text-heading-sm` |
| heading | Figtree | 500/600 | 36px | 1.13 | -0.72px | `--text-heading` |
| heading-lg | Figtree | 500/600 | 48px | 1.13 | -0.96px | `--text-heading-lg` |
| display | Figtree | 600 | 64px | 1.00 | -1.28px | `--text-display` |

### Spacing Scale (4px Base Unit)
| Name | Value | Token |
|------|-------|-------|
| 4 | 4px | `--spacing-4` |
| 8 | 8px | `--spacing-8` |
| 12 | 12px | `--spacing-12` |
| 16 | 16px | `--spacing-16` |
| 20 | 20px | `--spacing-20` |
| 24 | 24px | `--spacing-24` |
| 28 | 28px | `--spacing-28` |
| 32 | 32px | `--spacing-32` |
| 36 | 36px | `--spacing-36` |
| 40 | 40px | `--spacing-40` |
| 64 | 64px | `--spacing-64` |
| 76 | 76px | `--spacing-76` |
| 80 | 80px | `--spacing-80` |
| 104 | 104px | `--spacing-104` |
| 160 | 160px | `--spacing-160` |
| 192 | 192px | `--spacing-192` |

### Border Radius
| Element | Value |
|---------|-------|
| nav | 8px |
| tags | 9999px |
| cards | 12px |
| small | 2px |
| inputs | 8px |
| buttons | 9999px |

### Shadows
| Name | Value | Token |
|------|-------|-------|
| md | `rgba(0, 0, 0, 0.2) 0px 3px 16px 0px` | `--shadow-md` |
| xl | `rgba(0, 0, 0, 0.5) 0px 4px 30px 0px` | `--shadow-xl` |
| xl-2 | `rgba(0, 0, 0, 0.34) 0px 20px 35px 0px, rgba(0, 0, 0, 0.25) 0px 4px 13px 0px` | `--shadow-xl-2` |
| md-2 | `rgba(255, 255, 255, 0.35) 0px 2px 14px 0px` | `--shadow-md-2` |
| xl-3 | `rgba(0, 0, 0, 0.35) 0px 20px 34px 0px` | `--shadow-xl-3` |
| subtle | `rgba(0, 0, 0, 0.15) 0px 0px 0px 1px` | `--shadow-subtle` |

### Surfaces Hierarchy
| Level | Name | Value | Role |
|-------|------|-------|------|
| 0 | Void | `#0b0c0e` | Absolute page base and outer canvas |
| 1 | Abyss | `#0e111b` | Primary canvas for body sections, inputs, and standard panels |
| 2 | Deep Sea | `#0d172b` | Elevated cards — feature containers, forms, replay viewer |
| 3 | Cobalt Panel | `#12244f` | Highlighted spotlight cards and active state indicators |

## Guidelines (Do's and Don'ts)
### Do
- Use 9999px radius for all interactive elements — buttons, badges, tags, and nav pills
- Use Figtree at weight 500/600 for all display text 32px and above with -0.02em tracking
- Use Inter weight 300–400 for body copy; let low weight do the work against the dark canvas
- Apply the aurora gradient pair (purple #625fff + pink #ff7dda) as large soft radial glows on dark hero sections only
- Layer surface colors in order: #0b0c0e → #0e111b → #0d172b → #12244f to indicate elevation without generic drop shadows
- Use #2862d7 or #305fbd for link text and code syntax, never for large fills
- Apply 1px borders in #172540 or #151e32 to define cards — avoid using shadows alone for card definition

### Don't
- Don't use bright fills on CTA buttons — white (#ffffff) is the primary action color, never a saturated blue or purple
- Don't place radial gradient glows inside content cards or feature sections — reserve for hero and section backgrounds only
- Don't use Inter for headlines 32px and above — Figtree owns the display register
- Don't use #12244f as a page background — it is a highlight surface, not a canvas
- Don't add color to secondary text — keep #abaebb and #c7c9d1 strictly achromatic
- Don't use sharp corners (0px radius) on interactive elements — minimum is 8px for inputs, 12px for cards, 9999px for pills
- Don't apply elevation shadows to ghost or outline buttons — they should sit flat against the canvas
```

---

## 2. SlothForm Specific Extensions

### Dry-Run Amber Safety Guard
- **Border & Accent**: `#f59e0b` (Amber-500)
- **Glow / Halo**: `rgba(245, 158, 11, 0.25)`
- **Badge Background**: `rgba(245, 158, 11, 0.12)`

### Live Submission Warning
- **Danger Rose**: `#f43f5e`
- **Glow / Halo**: `rgba(244, 63, 94, 0.25)`
- **Badge Background**: `rgba(244, 63, 94, 0.12)`

### Success / Completed
- **Emerald**: `#10b981`
- **Badge Background**: `rgba(16, 185, 129, 0.12)`

### Sensitivity Tiers
- **PUBLIC**: `#38bdf8` (Sky blue, bg `rgba(56, 189, 248, 0.12)`)
- **SEMI_SENSITIVE**: `#f59e0b` (Amber, bg `rgba(245, 158, 11, 0.12)`)
- **CRITICAL_TAX**: `#a855f7` (Amethyst, bg `rgba(168, 85, 247, 0.12)`)
- **CRITICAL_FINANCIAL**: `#f43f5e` (Rose, bg `rgba(244, 63, 94, 0.12)`)

---

## 3. Component System Implementation

### 1. Navigation Header
- **Layout**: Fixed/sticky at top (`backdrop-filter: blur(16px)`), height 64px, hairline bottom border (`#172540`).
- **Brand Mark**: Sloth mascot logo (`🦥`) with glowing radial backlight, sleek typography ("SlothForm" in Figtree 600, uppercase tracked kicker "AUTONOMOUS FORM AGENT").
- **Vault Status Indicator**: Pill badge with animated pulsing glowing dot (`#10b981`), monospace AES-256 vault indicator.

### 2. Command Deck & Hero
- **Atmosphere**: Dual radial aurora glows (`#625fff` on top-left, `#ff7dda` on bottom-right) layered over `#0b0c0e` base with subtle 48px grid hairline lines.
- **Eyebrow Kicker**: Uppercase tracked label (`0.06em` letter spacing) in `#12244f` cobalt panel pill declaring multi-agent architecture.
- **Display Title**: Large Figtree 600 heading with tight `-0.03em` tracking and gradient shimmer (`linear-gradient(180deg, #ffffff 15%, #c7c9d1 100%)`).

### 3. Target URL Command Bar
- **Input Wrapper**: Pill command bar (`border-radius: 9999px`), dark elevated surface (`#0d172b`), glowing focus ring.
- **Safety Switch**: Dry-Run Guard toggle switch with amber warning illumination when ON, warning red when toggled OFF.
- **Primary Action**: White pill button (`#ffffff` fill, `#050606` text) with hover lift and glowing drop shadow.
- **Sample URL Chips**: Sleek pill chips with hover highlights for Greenhouse, Lever, Ashby, and W-8BEN.

### 4. 5-Stage Visual Execution Pipeline
- **Pipeline Track**: Deep sea channel with animated glowing progress bar (`linear-gradient(90deg, #2862d7, #625fff, #10b981)`).
- **Stage Nodes**: 5 distinct instrument nodes (Provisioning, DOM Schema, Ultramarine, Auth0 CIBA, Form Fill & Guard) with status badges (10%, 30%, 50%, 70%, 100%), active pulsing border, and completion checkmarks.

### 5. Auth0 CIBA Human-In-The-Loop Consent Card
- **Trigger**: Activates automatically when pipeline halts for `CIBA_CONSENT` (70%).
- **Card**: Elevated `#0d172b` card with glowing amber hairline border (`rgba(245, 158, 11, 0.5)`).
- **Interactive Controls**:
  - `Authorize Identity Release`: White or Emerald primary pill button calling `POST /api/tasks/{task_id}/consent` with `approved=true`.
  - `Reject & Abort Fill`: Ghost danger pill button calling `POST /api/tasks/{task_id}/consent` with `approved=false`.
  - Real-time status badge updating upon consent submission.

### 6. Split Telemetry Dashboard
- **Replay Monitor**: 16:9 cinematic container with Browserbase session embed, CRT scanning line effect, live view status dot, and external session trigger.
- **Privacy Diff Table**: Structured audit grid comparing field attributes, sensitivity tiers (PUBLIC, SEMI_SENSITIVE, CRITICAL_TAX, CRITICAL_FINANCIAL), values (masked/synthetic), and consent states.
- **Live Terminal Feed**: macOS dark IDE terminal with red/yellow/green control dots, monospaced log stream, stage tags, and real-time SSE listener.
