# Project Overview

Autodesk Fusion 360 add-in that generates parameterised Luer fittings (slip and lock,
male and female, plus two "internal" variants for cutting into existing bodies). Adds a
single command `Luer Fitting` to the **Create** panel of the Solid workspace.

Originally written by Nico Schlüter (<https://github.com/nico-schluter/LuerFittingGenerator>),
ported in 2026 to phos.systems' standardised add-in framework and resubmitted to the
Autodesk App Store after Autodesk's installer-format change broke the previous release.
The legacy single-file add-in is preserved under
[docs/LuerFittingGenerator/](docs/LuerFittingGenerator/) for reference.

## Goals

- Restore App Store availability after the forced resubmission.
- Triage and fix accumulated minor bugs surfaced from GitHub issues and store reviews.
- Establish a clean baseline structured around the new template (`futil`, `commands/`)
  so subsequent maintenance is light.

## Next Release

### In Progress

- [Smoke test in Fusion](tests/manual-checklist.md) — all six types confirmed generating
  on first inspection (angled body, circular edge as origin). Full matrix coverage still
  outstanding, especially direct-design and hybrid-document modes.

### Planned

- **Profile lookup by intrinsic property** (replaces `sketch.profiles[N]` integer
  indexing). Currently, when topology shifts unexpectedly (e.g. invalid inputs slip
  past the validator, or Fusion changes profile enumeration order in some future
  release), the builders raise `IndexError` mid-build. The fix is to look profiles up
  by an intrinsic property — the radius of one of their bounding loops, or membership
  of a specific known sketch curve — so the builders are tolerant of topology shifts
  and only fail on genuinely invalid input.

- **Verify Male Lock outer-cylinder OD against ISO 594-2.** Code uses 10 mm OD; secondary
  sources cite 9.8–9.9 mm. Likely a mating-fit candidate worth a 0.1–0.2 mm reduction
  if confirmed against the actual standard figure.

- **Richer hover-text on all command inputs.** Currently only `SIOrigin`, `SIPlane`,
  and the diametral-clearance input have tooltipDescription content. Hole diameter,
  the type dropdown, and the status text box would all benefit from short
  explanations. Deferred from the input-validation pass to keep that change focused.

### Deferred

- Document the derivation of the magic vector offsets used for the thread cross-section
  rosette (`offset_od_arc`, `offset_csa1`, `offset_csa2`) against the ISO 594-2 figure.
- **ISO 80369 sub-section variants** (gastric, neuraxial, etc). Requested by Brett
  Foster in the App Store reviews — different small-bore connector standards exist
  that intentionally don't mate (e.g. preventing a feeding tube being connected to a
  venous line). Out of scope for this resubmission release; revisit if there's
  sustained demand. ISO 80369-7 (Luer for IV / hypodermic) is what we currently
  generate.

## Implementation

### Structure

```
src/LuerFittingGenerator/
  LuerFittingGenerator.py        # Entry point; delegates start/stop to commands/
  LuerFittingGenerator.manifest  # Manifest. Preserves legacy add-in UUID.
  config.py                      # COMPANY_NAME / ADDIN_NAME / DEBUG flag
  commands/
    __init__.py                  # Registers all commands
    luerFitting/
      entry.py                   # The whole command — UI, validation, geometry
      resources/                 # Toolbar icons (16/32 px, @2x, disabled variants)
  lib/fusionAddInUtils/          # Vendored utilities (Autodesk template)
    general_utils.py             # log(), handle_error()
    event_utils.py               # add_handler() — keeps refs alive automatically
```

### Command flow

`Luer Fitting` is added to `SolidCreatePanel`, positioned beside `FusionThreadCommand`.
On invocation:

1. `command_created` builds the input dialog (origin, plane, type, hole, clearance) and
   wires `executePreview`, `inputChanged`, `validateInputs`, `destroy`.
2. `command_input_changed` toggles `Hole diameter` visibility based on Male/Female.
3. `command_validate_input` requires that when no plane is given, the origin must be a
   sketch point in a parametric design.
4. `command_preview` does the actual work — builds a sketch on the chosen plane,
   projects the origin onto it, transforms into sketch coordinates, and dispatches to
   one of six per-type builders. Marks `isValidResult = True` so the preview commits
   when the user clicks OK ("persistent preview" pattern, inherited from the legacy
   add-in).

### Persistence

A module-level `pers` dict caches the last-used type / hole / clearance within a
session. **Intentionally not written to disk** — values reset on Fusion restart.

### Geometry

Each fitting type is built by a private function `_build_<type>(comp, des, sketch, point_prim, hole, clearance)`.
All taper/thread constants are preserved verbatim from the legacy add-in, derived
implicitly from ISO 594 (6% taper, 1.72° half-angle, 2-start lock thread, 2.5 mm pitch).
Spot-check against secondary sources of the standard is recorded in the [Progress Log](#progress-log)
entry for 2026-05-06.

The two Male Lock variants share their thread-rosette sketching via `_build_male_thread_geometry`.
The Female Lock has its own (different) rosette inline.

## Progress Log

### 2026-05-06 — App Store submission packet

- New repo README modelled on reverse-reloaded's structure: title + tagline,
  attribution to Nico Schlüter's original, "Use" walkthrough, supported types,
  installation, changelog.
- Description prose tweaks per review: "luer" → "Luer" (twice), "IV type" →
  "IV-type", "Standard luer fitting for IV type fittings" → "Standard Luer
  fitting for IV-type connections", trailing 4-space gaps replaced with `<br>`
  for explicit line breaks.
- New canonical privacy policy at `repo/src/LuerFittingGenerator/privacy-policy.html`,
  adapted from reverse-reloaded's policy (same legal entity / brand, structure
  unchanged, only the add-in name and the description of in-product operations
  updated). The legacy `AppStorePrivacyPolicy.txt` (still in `docs/` for
  reference) is now obsolete — Autodesk no longer pushes downloader personal
  data to publishers, and we capture nothing.
- Manifest `description` simplified to follow reverse-reloaded's convention
  (one-line summary + privacy disclaimer pointing at the shipped file).
  Added `privacyPolicyFilename` key to the manifest.
- [app-store-submission/submission.md](../app-store-submission/submission.md)
  filled in: app name, short and long descriptions (~2400 chars), version
  description, ≥1500 char usage instructions, support / company / privacy
  URLs, known-issues callout for the lock-thread fit on first prints. Asset
  list still has screenshots, F1 help, and an in-addin privacy-policy link
  outstanding.

### 2026-05-06 — Documentation polish & v1.1.0 release prep

- Manifest version bumped to `1.1.0` (previous App Store listing was `1.0.0`). The
  resubmission was originally framed as a forced repackage, but the validator,
  status-line surfacing, and tooltip pass have added enough user-visible behaviour
  to justify a minor bump.
- Top-level manifest icon replaced: `AddInIcon.svg` placeholder → `AddInIcon.png`
  (luer-themed). Manifest `iconFilename` updated accordingly.
- Tool-clip image supplied at `commands/luerFitting/resources/toolclip.png`. The
  conditional load in `start()` picks it up automatically; nothing to wire.
- Enriched `CMD_DESCRIPTION` (the toolbar-button tooltip) from `'Creates a luer
  fitting'` to a multi-sentence description covering type variants, placement, and
  the bore/clearance tuning controls.
- Added `tooltip` + `tooltipDescription` for the remaining inputs: `DDType` (slip vs.
  lock vs. internal explainer with HTML formatting), `VIHole` (through-bore vs.
  female-bore distinction), `TBStatus` (validation status explainer).
- Triaged App Store reviews and GitHub issues. No open bugs. One feature request
  (Brett Foster, 2020): ISO 80369 sub-section variants for use-class differentiation
  (gastric, neuraxial, etc.) — added to Deferred, out of scope for this resubmission.
- Removed three stale `TODO: assembly-context world transform still required` comments
  in `_get_primitive_from_selection`. The bug they flagged is no longer reachable in
  current Fusion (parts/assemblies split into separate document types) — same
  rationale as removing the assembly-context Deferred item earlier.
- Cleaned up a duplicate Planned/Deferred entry for the profile-by-property lookup.

### 2026-05-06 — UX polish after second dialog test

- Widened build-error keyword detection so failure modes outside the original
  `NO_TARGET_*` family map to the same user-facing message
  (`'Place fitting on or near a body.'`). The previous catch-all was triggering for
  Female Slip in empty space (its first extrude is a Join, which fails differently
  than the Cut-driven Internal Male Lock case). Raw exception text is now also logged
  to the Text Command window so unmapped patterns can be added to the keyword list
  later.
- Stashed `_last_build_error` in module state so the validator can surface it on its
  next firing and gray out the OK button. Cleared on every input change and on
  command destroy. Per Fusion docs the validate event timing is "indeterminate", so
  this is best-effort — there can be a brief window after a failed preview where OK
  stays enabled. Clicking OK in that window is harmless because the failed preview
  set `isValidResult = False`.
- Shortened the diametral-clearance label from `Clearance (diametral)` to
  `Clearance`; the "diametral" qualifier and a longer explanation now live in the
  hover tooltip. Other inputs still need richer hover text — deferred to a later
  pass.

### 2026-05-06 — Validator refinements after first dialog test

- Status messages shortened so they fit within 1–2 lines at the default dialog width
  (the previous messages wrapped to 3 lines and triggered a scrollbar).
- Male hole-diameter check tightened: now checked against the **tip** (smaller end) of
  the taper rather than the base. The base-side check let the bore break through the
  cone tip in cases where wall thickness was adequate at the base but went negative at
  the tip. The tip is where the wall is structurally thinnest, so that is the right
  reference.
- Removed the "internal variants need a body in the active component" pre-check. It
  was shallow — a body could exist but be nowhere near the chosen origin, in which
  case the cut would fail silently with a `RuntimeError: NO_TARGET_SWEEP_BODY`.
  Replaced with a `try/except RuntimeError` around the builder dispatch in
  `command_preview`. On error, the status text is set to a brief reason
  (`'No body to cut into here.'` for the no-target case, `'Build failed — adjust
  inputs.'` as catch-all) and `args.isValidResult = False`. Covers the original
  body-absence case plus any other build failure we haven't anticipated.

### 2026-05-06 — Input validation & failure communication

- Smoke test (full matrix) returned green for all 18 normal cases (6 fitting types × 3
  design modes). See [tests/manual-checklist.md](tests/manual-checklist.md). Two
  failure classes surfaced: out-of-range inputs producing silent wrong geometry, and
  `sketch.profiles[N]` `IndexError`s when topology shifts (e.g. hole diameter > base).
  Assembly-context bug confirmed untestable — dropped from Deferred.
- Added per-type input validator (`_validate_geometry`) gating `args.areInputsValid`.
  Covers: hole > 0 for Male variants, male base diameter positive, hole < male base
  with one-wall margin, female mouth positive, female mouth fits inside outer collar
  with one-wall margin, and "internal" variants require an existing body in the active
  component. Wall-thickness margin is `MIN_WALL = 0.02 cm` (0.2 mm).
- Added a full-width read-only status `TextBoxCommandInput` at the bottom of the
  dialog. Reasons for invalid input are surfaced there; OK is greyed out per the
  no-message-box convention. Always-visible (left as a few lines of empty space when
  valid); revisit hide-when-empty behaviour if it bothers in practice.
- Extracted `_male_base_diameter(clearance)` so the validator and the three male
  builders share a single source of truth for that formula.
- Dropped `executePreview → execute` migration and document-level undo grouping from
  the Deferred list — both were speculative concerns now negated by smoke-test
  evidence (clean timeline group, single-undo behaviour, automatic preview rollback
  on cancel).
- Promoted profile-by-property lookup from Deferred to Planned for the next release
  cycle; it is now the standing fix for the `sketch.profiles[N]` IndexError class
  rather than just a theoretical fragility.

### 2026-05-06 — Port to phos.systems framework

- Ported the legacy single-file `LuerFittings.py` into the new template structure
  (`commands/luerFitting/entry.py`).
- Behaviour preserved verbatim, including the persistent-preview creation pattern and
  the session-only persistence dict.
- Manifest carries forward the legacy UUID `c7766c33-d7e6-4fef-b141-9018de20d36f` so
  existing App Store installs upgrade rather than duplicate.
- Structural cleanups baked in: per-type builders extracted, shared male-lock thread
  geometry factored out, `designType` truthy check replaced with explicit
  `DesignTypes.ParametricDesignType` comparison, `exturde` typo fixed throughout,
  origin-selection tooltip clarified to spell out which selection types need a separate
  plane.
- Removed the three default template commands (`commandDialog`, `paletteShow`,
  `paletteSend`) and their resources.
- Smoke test: all six fitting types generated successfully on first attempt against an
  angled body using a circular edge as the origin reference. Single-undo collapses the
  full timeline group as expected.
- Geometry constants spot-checked against secondary sources of ISO 594 / 80369-7. All
  major dimensions match (6% taper, 1.72° half-angle, 4 mm tip, 4.45 mm base, 7.5 mm
  male taper length, 9 mm female socket depth, 2-start thread with 2.5 mm pitch giving
  396° / 648° twist over the male / female lock sweep paths). The only candidate
  discrepancy is the male lock outer cylinder OD (code: 10 mm; secondary sources:
  9.8–9.9 mm); to be verified against the actual ISO 594-2 figure if accessible.
