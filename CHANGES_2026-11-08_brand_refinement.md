# MMS Recruitment Portal — UI/UX refinement & brand standardisation (08-11-2026)

Visual-only update. No backend, API, database, workflow, permission or calculation change.

## Design tokens
- **Brand blues** (from the MetaMorphoSys logo): Sky #A0D5FC, Brand #67B5F4, Royal #4089DE, Deep #2265C8, Pale (selected states) #EDF5FE.
- **Neutrals:** White #FFFFFF, Off-white #F7F8FA (app background), Light grey #E8EBEF (borders), Charcoal #20242B (text), Muted #737B87 (secondary text).
- **Status:** muted green #3E8E63, amber #C08A2E, red #C0504D.
- **Where the values live:** `src/index.css` (CSS variables used by shadcn/ui), `tailwind.config.js` (`brand-*`, `ink`, `subtle`, `line`, `canvas` utilities) and `src/lib/brand.js` (chart colours and axis style).
- **Chart order:** Deep → Royal → Brand → Sky → grey. Joined and other positive outcomes use muted green.
- **Shape:** controls have a 8–10 px radius, cards and dialogs 16 px. Shadows are minimal.

## Typography
IBM Plex Sans is the only font family, in weights 400, 500, 600 and 700. The font files are bundled with the app (`src/assets/fonts/ibm-plex-sans`, SIL Open Font License) and no longer load from Google. Plus Jakarta Sans, JetBrains Mono and Inter have been removed. Numbers use tabular figures. The type scale follows the brief: page titles 28–30 px, KPI values 26–30 px, card headings 15–16 px, body 14 px, labels 13 px, secondary text 12 px.

## What changed
- **Shared components** (so every module changes together):
  - **Buttons:** primary deep blue; secondary white with a grey border; ghost with a pale-blue hover.
  - **Form controls:** inputs, selects and textareas are white, 36 px high, with a royal-blue focus ring.
  - **Tabs:** pale-blue active tab with deep-blue text; the tab bar scrolls sideways on small screens.
  - **Dialogs, sheets, menus and popovers:** 16 px radius and a soft overlay.
  - **Data tables:** sentence-case headers, row hover, numeric columns right-aligned with tabular figures, a sticky first column, single-line cells (full text on hover) and horizontal scrolling.
  - **Status badges:** compact, with restrained colours; offer stages shown in brand blue.
  - **KPI cards, sections and empty states.**
- **App shell:**
  - **Sidebar:** white, 248 px wide; charcoal labels with grey icons; pale-blue active item with deep-blue text and an accent bar; a cleaner collapsed state.
  - **Header:** 64 px high, breadcrumbs, notification badge, and the user name with designation.
  - **Content area:** a single consistent container.
- **Dashboard:**
  - **Header:** title and subtitle with the period and comparison dates, then period, department, requisition and recruiter filters and Export.
  - **KPI row:** seven KPI cards with icons and real period-over-period changes.
  - **Trend:** blue trend chart with a Weekly/Monthly switch and a clickable legend.
  - **Funnel:** tapered funnel with a conversion and drop-off table; each stage is clickable.
  - **Cost and Age:** Cost per Hire and Age per Hire cards with breakdowns and sparklines.
  - **Sources:** donut chart plus table.
  - **Recruiters:** recruiter bars with a measure picker and a full details table.
  - **Requisitions:** requisition cards with filters, stat boxes, time to fill and ageing.
  - **Other cards:** upcoming interviews, activity timeline, pending actions and pipeline distribution.
  - All metrics and drill-downs are unchanged.
- **Analytics:** every tab, metric and calculation is kept. The filter panel is more compact: Partner, Source and Status moved under "More filters", which opens automatically when one of them is set. KPI cards have icons, and charts use the brand palette with consistent tooltips and legends.
- **Login page:** not redesigned. It now uses IBM Plex Sans like the rest of the portal.

## Checked
- **Pages:** all 14 open with no errors: Dashboard, Requisitions, Candidates, Pipeline, Interviews, Offers, Joining, Costs, Analytics, Reports, Import, Activity, Users and Settings.
- **Font:** IBM Plex Sans is the only family rendered, and it is loaded locally.
- **Layout:** no horizontal page overflow on desktop or mobile (390 px). Wide tables scroll inside their card.
- **Interactions:** the "More filters" panel opens.
