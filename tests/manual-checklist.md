# Manual In-Fusion Test Checklist

Pre-release smoke checklist run inside Fusion 360 against the add-in loaded from `src/`.
Tick each row as you go. Add the date next to the section header for each pass.

A pass means: the feature creates without error, the timeline group contains the expected
features, undo collapses the whole group in one step, and the geometry visually matches
expectations.

## 1. Origin selection types

For each origin selection type, run with `Type = Male Slip` and defaults so any breakage
shows up against the simplest geometry.

- [x] Sketch Point (no plane selected — should derive from sketch reference plane)
- [x] Sketch Point + plane selected (plane should override sketch ref plane)
- [x] Construction Point + Construction Plane
- [x] Construction Point + Planar Face
- [x] BRep Vertex + Construction Plane
- [x] BRep Vertex + Planar Face
- [x] Circular BRep Edge + Construction Plane
- [x] Circular BRep Edge + Planar Face (centre derived from edge, plane required)

Edge cases:

- [x] Origin off the selected plane — verify projection onto plane works
- [x] Origin on an angled face — verify fitting axis is normal to the face
- [x] Selecting a non-circular BRep edge — should be rejected by the selection filter

## 2. Generation type × design type matrix

For each fitting type, test in both design modes. Use the same origin (a sketch point on
an angled body face is a representative case — exercises projection and non-axis-aligned
extrudes in one shot).

| Fitting type             | Parametric | Direct | Hybrid (legacy) |
|--------------------------|:----------:|:------:|:---------------:|
| Male Slip                | [x]        | [x]    | [x]             |
| Male Lock                | [x]        | [x]    | [x]             |
| Male Lock (internal)     | [x]        | [x]    | [x]             |
| Female Slip              | [x]        | [x]    | [x]             |
| Female Slip (internal)   | [x]        | [x]    | [x]             |
| Female Lock              | [x]        | [x]    | [x]             |

Per-cell pass criteria:

- [x] Geometry materialises (sketch + extrudes + sweep where applicable)
- [x] Timeline group named sensibly, collapses with single undo
- [x] Threads (Lock variants) wind in the correct hand and don't self-intersect
- [x] `(internal)` variants are oriented inward correctly
- [x] Hole-diameter input toggles visibility correctly when switching Male ↔ Female

Note for direct mode: the validator currently blocks when origin is non-SketchPoint and
no plane is selected even with a plane present in some cases. Confirm whether direct
mode is fully functional or needs a validator tweak.

## 3. Persistence behaviour

- [x] Run the command, change all three values, OK. Re-open the command — values persist.
- [x] Stop and restart the add-in — values reset to defaults (intentional, session-only).

## 4. Cleanup

- [x] Cancel the command after a preview — preview geometry is fully removed.
- [x] Stop the add-in — toolbar button disappears and re-running `start` re-adds it cleanly.

## 5. Known-issue regression spot-checks

These cover the items flagged in the legacy code analysis. Confirm whether each is still
broken so we can decide what's in scope for this release.

- [ ] Construction Plane / Construction Point in an assembly context — does the fitting
      land in the right world location? (Legacy had `TODO` comments suggesting it would
      not.):
      not testable, multi part singe documents are no longer supported.
- [ ] Very large clearance (e.g. 4 mm) — should this be rejected? Currently it can produce
      negative-radius geometry on Male variants:
      Generation produces wrong result. (male slip, tall, narrow cylinder, likely the hole profile, male lock threads generate fine, same cylinder instead of taper, female slip jsut generates the pretruding cylindrical collar with no hole, female slip genearates "correctly" very large hole with taper, female lock just the threaded boss)
- [ ] Hole diameter > base taper diameter on Male Slip — currently produces a sketch where
      the inner circle is outside the outer circle. No graceful failure:
      Male slip, helo become cylinder, swallows taper, male lock same thing, prpduces error when it gets into the threaded section: ==== Error =====
CommandEventHandler
Traceback (most recent call last):
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/lib/fusionAddInUtils/event_utils.py", line 84, in notify
    callback(args)
    ~~~~~~~~^^^^^^
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/commands/luerFitting/entry.py", line 153, in command_preview
    builders[fitting_type](comp, des, sketch, point_prim, hole, clearance)
    ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/commands/luerFitting/entry.py", line 304, in _build_male_lock


## 6. Mid-build failure behaviour (sanity check, not a regression)

If a sketch / extrude / sweep raises during preview generation (e.g. due to invalid
inputs), confirm Fusion's preview rollback leaves the document clean. This is the
scenario that document-level undo grouping would otherwise have to handle — if rollback
works, we can leave it alone.

- [x] Trigger a deliberate build failure (e.g. negative radius via large clearance) and
      verify the document is unchanged after cancelling.

Note:
- all failures are silent to the user UI, only the two logs provided show failures in the debug console
- internal features fail when not placed on a body:

===== Error =====
CommandEventHandler
Traceback (most recent call last):
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/lib/fusionAddInUtils/event_utils.py", line 84, in notify
    callback(args)
    ~~~~~~~~^^^^^^
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/commands/luerFitting/entry.py", line 153, in command_preview
    builders[fitting_type](comp, des, sketch, point_prim, hole, clearance)
    ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/commands/luerFitting/entry.py", line 304, in _build_male_lock
    extrude_input3 = comp.features.extrudeFeatures.createInput(sketch.profiles[5], 0)
                                                               ~~~~~~~~~~~~~~~^^^
  File "/Users/phos/Library/Application Support/Autodesk/webdeploy/production/2448aa8b3276a952725a8bb01f628b797da18a2a/Autodesk Fusion.app/Contents/Api/Python/packages/adsk/fusion.py", line 56271, in __getitem__
    raise IndexError("The index (%d) is out of range." % i)
IndexError: The index (5) is out of range.

===== Error =====
CommandEventHandler
Traceback (most recent call last):
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/lib/fusionAddInUtils/event_utils.py", line 84, in notify
    callback(args)
    ~~~~~~~~^^^^^^
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/commands/luerFitting/entry.py", line 153, in command_preview
    builders[fitting_type](comp, des, sketch, point_prim, hole, clearance)
    ~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/phos/Documents/EA/professional/fusion-extensions/luer-fitting-generator/repo/src/LuerFittingGenerator/commands/luerFitting/entry.py", line 346, in _build_male_lock_internal
    f1 = comp.features.sweepFeatures.add(sweep_input)
  File "/Users/phos/Library/Application Support/Autodesk/webdeploy/production/2448aa8b3276a952725a8bb01f628b797da18a2a/Autodesk Fusion.app/Contents/Api/Python/packages/adsk/fusion.py", line 68796, in add
    return _fusion.SweepFeatures_add(self, input)
           ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
RuntimeError: 3 : NO_TARGET_SWEEP_BODY - No intersecting target body was found.

