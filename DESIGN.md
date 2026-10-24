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

## Tokens — Spacing & Shapes
- **Base unit**: 4px
- **Border Radii**: Cards `12px`, Inputs `8px` or `9999px` pill, Buttons & Badges `9999px` full pill, Code/Terminal `8px`
- **Card Elevation**: Layered surface color hierarchy (`#0b0c0e` → `#0e111b` → `#0d172b` → `#12244f`) augmented by deep ambient shadows (`rgba(0, 0, 0, 0.5) 0px 4px 30px 0px`).

## SlothForm Specific Extensions
- **Dry-Run Amber Safety Guard**:
  - Border & Accent: `#f59e0b` (Amber-500)
  - Glow / Halo: `rgba(245, 158, 11, 0.25)`
  - Badge Background: `rgba(245, 158, 11, 0.12)`
- **Live Submission Warning**:
  - Danger Rose: `#f43f5e`
  - Glow / Halo: `rgba(244, 63, 94, 0.25)`
- **Success / Completed**:
  - Emerald: `#10b981`
  - Badge Background: `rgba(16, 185, 129, 0.12)`
- **Tax Tier Sensitivity Badge**:
  - Amethyst: `#a855f7`
  - Badge Background: `rgba(168, 85, 247, 0.12)`
```

---

## 2. Component System Implementation

### 1. Navigation Header
- **Layout**: Fixed/sticky at top (`backdrop-filter: blur(16px)`), height 64px, hairline bottom border (`#172540`).
- **Brand Mark**: Sloth mascot logo (`🦥`) with glowing radial backlight, sleek typography ("SlothForm" in Figtree 600, uppercase tracked kicker "AUTONOMOUS FORM AGENT").
- **Vault Status Indicator**: Pill badge with animated pulsing glowing dot (`#10b981` or `#f59e0b`), monospace AES-256 vault indicator.

### 2. Command Deck & Hero
- **Atmosphere**: Dual radial aurora glows (purple on top-left, magenta on bottom-right) layered over `#0b0c0e` base.
- **Eyebrow Kicker**: Uppercase tracked label (`0.08em` letter spacing) declaring multi-agent architecture ("BROWSERBASE SANDBOX + ULTRAMARINE + AUTH0 CIBA").
- **Display Title**: Large Figtree 500 heading with tight `-0.025em` tracking and gradient shimmer.

### 3. Target URL Command Bar
- **Input Wrapper**: Pill command bar (`border-radius: 9999px`), dark elevated surface (`#0d172b`), glowing focus ring.
- **Safety Switch**: Dry-Run Guard toggle switch with amber warning illumination when ON, warning red when toggled OFF.
- **Primary Action**: White pill button (`#ffffff` fill, `#050606` text) with hover lift and glowing drop shadow.
- **Sample URL Chips**: Sleek pill chips with hover highlights for Greenhouse, Lever, Ashby, and W-8BEN.

### 4. 5-Stage Visual Execution Pipeline
- **Pipeline Track**: Deep sea channel with animated glowing progress bar (`linear-gradient(90deg, #305fbd, #625fff, #10b981)`).
- **Stage Nodes**: 5 distinct instrument nodes (Provisioning, DOM Schema, Ultramarine, Auth0 CIBA, Form Fill & Guard) with status badges (10%, 30%, 50%, 70%, 100%), active pulsing border, and completion checkmarks.

### 5. Split Telemetry Dashboard
- **Replay Monitor**: 16:9 cinematic container with Browserbase session embed, CRT scanning line effect, live view status dot, and external session trigger.
- **Privacy Diff Table**: Structured audit grid comparing field attributes, sensitivity tiers (PUBLIC, SEMI_SENSITIVE, CRITICAL_TAX, CRITICAL_FINANCIAL), values (masked/synthetic), and consent states.
- **Live Terminal Feed**: macOS dark IDE terminal with red/yellow/green control dots, monospaced log stream, stage tags, and real-time SSE listener.
