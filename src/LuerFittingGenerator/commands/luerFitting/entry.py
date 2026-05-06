import math
import os

import adsk.core
import adsk.fusion

from ... import config
from ...lib import fusionAddInUtils as futil

app = adsk.core.Application.get()
ui = app.userInterface


CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_luerFitting'
CMD_NAME = 'Luer Fitting'
CMD_DESCRIPTION = (
    'Creates a male or female, locking or slip fit, Luer fitting.<br>'
    'Select a location, and an orientation.<br>'
    'Standard Luer fitting for IV-type connections.<br>'
    'Adjust hole diameter and clearance as needed.'
)

IS_PROMOTED = False

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
COMMAND_BESIDE_ID = 'FusionThreadCommand'

ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Session-only persistence of the last-used inputs. Intentionally not written
# to disk — resets on Fusion restart.
pers = {
    'DDType': 'Male Slip',
    'VIDiametralClearance': 0,
    'VIHole': 0.225,
}

# Minimum wall thickness (cm = Fusion internal length unit) that the validator
# requires between concentric features. 0.02 cm = 0.2 mm.
MIN_WALL = 0.02

local_handlers = []

# Set by command_preview when the builder raises. Surfaced by the validator
# on its next run so the OK button greys out — the validator's only lever for
# disabling OK. Cleared on every input change and on command destroy.
_last_build_error = None


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER)

    toolclip = os.path.join(ICON_FOLDER, 'toolclip.png')
    if os.path.exists(toolclip):
        cmd_def.toolClipFilename = toolclip

    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')

    cmd = args.command

    help_file = os.path.join(ICON_FOLDER, 'help.html')
    if os.path.exists(help_file):
        cmd.helpFile = help_file

    inputs = cmd.commandInputs

    si_origin = inputs.addSelectionInput('SIOrigin', 'Point', 'Select Center Point')
    si_origin.addSelectionFilter('ConstructionPoints')
    si_origin.addSelectionFilter('SketchPoints')
    si_origin.addSelectionFilter('Vertices')
    si_origin.addSelectionFilter('CircularEdges')
    si_origin.setSelectionLimits(1, 1)
    si_origin.tooltip = 'Fitting Center Point'
    si_origin.tooltipDescription = (
        'Select the center point of the Fitting.\n'
        'Will be projected onto the plane.\n\n'
        'Valid selections:\n'
        '    Sketch Points (plane derived from sketch)\n'
        '    Construction Points (plane required)\n'
        '    BRep Vertices (plane required)\n'
        '    Circular BRep Edges (plane required)'
    )

    si_plane = inputs.addSelectionInput('SIPlane', 'Plane', 'Select Fitting Plane')
    si_plane.addSelectionFilter('ConstructionPlanes')
    si_plane.addSelectionFilter('PlanarFaces')
    si_plane.setSelectionLimits(0, 1)
    si_plane.tooltip = 'Fitting Plane'
    si_plane.tooltipDescription = (
        'Select the plane the fitting will be placed on.\n\n'
        'Valid selections are:\n'
        '    Construction Planes\n'
        '    BRep Faces\n\n'
        'Not needed if a Sketch Point is selected.'
    )

    dd_type = inputs.addDropDownCommandInput('DDType', 'Type', 0)
    for name in ('Male Slip', 'Male Lock', 'Male Lock (internal)',
                 'Female Slip', 'Female Slip (internal)', 'Female Lock'):
        dd_type.listItems.add(name, pers['DDType'] == name, '')
    dd_type.tooltip = 'Fitting type'
    dd_type.tooltipDescription = (
        '<b>Slip</b> — friction fit; mates with another slip or with a lock.<br>'
        '<b>Lock</b> — threaded collar that screws onto a mating lock fitting.<br>'
        '<b>Internal</b> variants are sunk into the existing body rather than '
        'protruding from it. Use these to build the fitting into the wall of an '
        'existing part.'
    )

    hole_input = inputs.addValueInput('VIHole', 'Hole diameter', 'mm',
                                      adsk.core.ValueInput.createByReal(pers['VIHole']))
    hole_input.tooltip = 'Through-bore diameter'
    hole_input.tooltipDescription = (
        'Diameter of the through-bore on male variants. The bore is a straight '
        'cylinder concentric with the taper.\n'
        'Hidden for female variants — there the bore is the female taper itself.'
    )
    clearance_input = inputs.addValueInput('VIDiametralClearance', 'Clearance', 'mm',
                                           adsk.core.ValueInput.createByReal(pers['VIDiametralClearance']))
    clearance_input.tooltip = 'Diametral clearance'
    clearance_input.tooltipDescription = (
        'Adjusts the fitting diameter relative to the nominal Luer taper.\n'
        'Applied diametrally — a value of 0.1 mm shrinks the male taper by 0.1 mm '
        '(or enlarges the female taper by 0.1 mm) to give a looser fit.\n'
        'Negative values produce a tighter fit.'
    )

    status = inputs.addTextBoxCommandInput('TBStatus', '', '', 2, True)
    status.isFullWidth = True
    status.tooltip = 'Validation status'
    status.tooltipDescription = (
        'Shows the reason the OK button is unavailable. Empty when all inputs '
        'are valid.'
    )

    futil.add_handler(cmd.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(cmd.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(cmd.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


# Persistent-preview pattern: geometry is created in executePreview and committed
# via isValidResult = True. There is no separate execute handler — matches the
# legacy add-in's behaviour.
def command_preview(args: adsk.core.CommandEventArgs):
    inputs = args.command.commandInputs
    des = adsk.fusion.Design.cast(app.activeProduct)
    comp = des.activeComponent

    fitting_type = inputs.itemById('DDType').selectedItem.name
    clearance = inputs.itemById('VIDiametralClearance').value
    hole = inputs.itemById('VIHole').value

    pers['DDType'] = fitting_type
    pers['VIDiametralClearance'] = clearance
    pers['VIHole'] = hole

    point_sel = inputs.itemById('SIOrigin').selection(0).entity
    point_prim = _get_primitive_from_selection(point_sel)

    plane_input = inputs.itemById('SIPlane')
    if plane_input.selectionCount == 1:
        plane = plane_input.selection(0).entity
    else:
        plane = point_sel.parentSketch.referencePlane

    plane_prim = _get_primitive_from_selection(plane)
    point_prim = _project_point_on_plane(point_prim, plane_prim)

    sketch = comp.sketches.addWithoutEdges(plane)

    inv = sketch.transform.copy()
    inv.invert()
    point_prim.transformBy(inv)

    builders = {
        'Male Slip': _build_male_slip,
        'Male Lock': _build_male_lock,
        'Male Lock (internal)': _build_male_lock_internal,
        'Female Slip': _build_female_slip,
        'Female Slip (internal)': _build_female_slip_internal,
        'Female Lock': _build_female_lock,
    }
    status = inputs.itemById('TBStatus')
    global _last_build_error
    try:
        builders[fitting_type](comp, des, sketch, point_prim, hole, clearance)
    except RuntimeError as exc:
        futil.log(f'{CMD_NAME} build error: {exc}', adsk.core.LogLevels.WarningLogLevel, force_console=True)
        _last_build_error = _short_build_error(exc)
        status.formattedText = _last_build_error
        args.isValidResult = False
        return

    _last_build_error = None
    status.formattedText = ''
    args.isValidResult = True


def _short_build_error(exc):
    """Map a Fusion RuntimeError to a brief user-facing message. The raw
    exception is also logged so unmapped patterns can be added here later."""
    msg = str(exc).upper()
    no_body_keywords = ('NO_TARGET', 'NO_INTERSECT', 'NO_BODY', 'NEW_BODY',
                        'JOIN', 'TARGET_BODY', 'INTERSECT')
    if any(kw in msg for kw in no_body_keywords):
        return 'Place fitting on or near a body.'
    return 'Build failed — adjust inputs.'


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    global _last_build_error
    _last_build_error = None

    if args.input.id == 'DDType':
        args.inputs.itemById('VIHole').isVisible = not args.input.selectedItem.name[0] == 'F'


def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    inputs = args.inputs
    des = adsk.fusion.Design.cast(app.activeProduct)
    status = inputs.itemById('TBStatus')

    si_origin = inputs.itemById('SIOrigin')
    si_plane = inputs.itemById('SIPlane')

    if si_origin.selectionCount == 1 and si_plane.selectionCount == 0:
        is_sketch_point = si_origin.selection(0).entity.objectType == 'adsk::fusion::SketchPoint'
        is_direct = des.designType == adsk.fusion.DesignTypes.DirectDesignType
        if not is_sketch_point or is_direct:
            status.formattedText = ''
            args.areInputsValid = False
            return

    fitting_type = inputs.itemById('DDType').selectedItem.name
    hole = inputs.itemById('VIHole').value
    clearance = inputs.itemById('VIDiametralClearance').value

    msg = _validate_geometry(fitting_type, hole, clearance)
    if msg:
        status.formattedText = msg
        args.areInputsValid = False
        return

    if _last_build_error:
        status.formattedText = _last_build_error
        args.areInputsValid = False
        return

    status.formattedText = ''
    args.areInputsValid = True


def _validate_geometry(fitting_type, hole, clearance):
    """Return a status message if inputs would produce broken geometry, else
    None. Lengths are in cm (Fusion's internal unit). The male hole check is
    against the tip (smaller end) of the taper, not the base — that is where
    the bore-vs-cone wall is thinnest."""
    if fitting_type.startswith('Male'):
        if hole <= 0:
            return 'Hole must be > 0.'
        if _male_base_diameter(clearance) <= 2 * MIN_WALL:
            return 'Clearance too large.'
        # Tip diameter is base - taper-over-7.5 mm = 0.4 - clearance.
        if hole >= (0.4 - clearance) - 2 * MIN_WALL:
            return 'Hole too large for taper.'
        return None

    # Female variants: mouth diameter must fit inside outer collar with one
    # wall thickness on each side.
    mouth = 0.43 + clearance
    if mouth <= 2 * MIN_WALL:
        return 'Clearance too negative.'

    if fitting_type == 'Female Slip' and mouth >= 0.65 - 2 * MIN_WALL:
        return 'Clearance too large.'
    if fitting_type == 'Female Lock' and mouth >= 0.67 - 2 * MIN_WALL:
        return 'Clearance too large.'

    return None


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _last_build_error
    local_handlers = []
    _last_build_error = None


# ---------------------------------------------------------------------------
# Fitting builders
#
# Geometry constants (taper angles, thread cross-section vector offsets, twist
# angles, extrude lengths) are preserved verbatim from the original add-in.
# Their derivation against ISO 594 is not currently documented — see the
# project's bug-triage backlog.
# ---------------------------------------------------------------------------


def _group_timeline(des, first_feature, last_feature):
    if des.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        des.timeline.timelineGroups.add(first_feature.timelineObject.index - 1,
                                        last_feature.timelineObject.index)


# Diameter (cm) at the wide end of the male luer taper. The cone narrows by
# tan(3.44°) per cm of axial length, so this is the diameter at the base after
# 7.5 mm of taper engagement, less the user's diametral clearance.
def _male_base_diameter(clearance):
    return 0.4 + math.tan(math.radians(3.44)) * 0.75 - clearance


def _build_male_slip(comp, des, sketch, point_prim, hole, clearance):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        point_prim,
        _male_base_diameter(clearance) / 2,
    )
    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, hole / 2)

    oc = adsk.core.ObjectCollection.create()
    oc.add(sketch.profiles[0])
    oc.add(sketch.profiles[1])

    extrude_input1 = comp.features.extrudeFeatures.createInput(oc, 0)
    extrude_input1.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('7.5 mm')),
        0,
        adsk.core.ValueInput.createByString('-1.72 deg'),
    )
    f1 = comp.features.extrudeFeatures.add(extrude_input1)

    extrude_input2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
    extrude_input2.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('7.5 mm')),
        0,
        adsk.core.ValueInput.createByString('0 deg'),
    )
    f2 = comp.features.extrudeFeatures.add(extrude_input2)

    _group_timeline(des, f1, f2)


def _build_male_thread_geometry(sketch, point_prim):
    """Shared thread cross-section sketch geometry for Male Lock variants.
    Returns the path line used by the sweep."""
    offset_od_arc = adsk.core.Vector3D.create(0.142, 0.3207, 0)
    offset_csa1 = adsk.core.Vector3D.create(0.1417, -0.0159, 0)
    offset_csa2 = adsk.core.Vector3D.create(-0.1332, -0.0506, 0)
    offset_line = adsk.core.Vector3D.create(0, 0, 0.55)

    pos_od_arc = point_prim.copy()
    pos_od_arc.translateBy(offset_od_arc)

    pos_csa1 = point_prim.copy()
    pos_csa1.translateBy(offset_csa1)

    pos_csa2 = point_prim.copy()
    pos_csa2.translateBy(offset_csa2)

    offset_od_arc.scaleBy(-1)
    offset_csa1.scaleBy(-1)
    offset_csa2.scaleBy(-1)

    pos_od_arc2 = point_prim.copy()
    pos_od_arc2.translateBy(offset_od_arc)

    pos_csa3 = point_prim.copy()
    pos_csa3.translateBy(offset_csa1)

    pos_csa4 = point_prim.copy()
    pos_csa4.translateBy(offset_csa2)

    pos_line = point_prim.copy()
    pos_line.translateBy(offset_line)

    od_arc1 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(point_prim, pos_od_arc, math.radians(42.4))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa1, od_arc1.startSketchPoint, math.radians(-23))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa2, od_arc1.endSketchPoint, math.radians(23))

    od_arc2 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(point_prim, pos_od_arc2, math.radians(42.4))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa3, od_arc2.startSketchPoint, math.radians(-23))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa4, od_arc2.endSketchPoint, math.radians(23))

    return sketch.sketchCurves.sketchLines.addByTwoPoints(point_prim, pos_line)


def _build_male_lock(comp, des, sketch, point_prim, hole, clearance):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        point_prim,
        _male_base_diameter(clearance) / 2,
    )
    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, hole / 2)

    path_line = _build_male_thread_geometry(sketch, point_prim)

    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, 0.4)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, 0.5)

    oc1 = adsk.core.ObjectCollection.create()
    oc1.add(sketch.profiles[0])
    oc1.add(sketch.profiles[1])

    extrude_input1 = comp.features.extrudeFeatures.createInput(oc1, 0)
    extrude_input1.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('7.5 mm')),
        0,
        adsk.core.ValueInput.createByString('-1.72 deg'),
    )
    f1 = comp.features.extrudeFeatures.add(extrude_input1)

    extrude_input2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
    extrude_input2.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('7.5 mm')),
        0,
        adsk.core.ValueInput.createByString('0 deg'),
    )
    comp.features.extrudeFeatures.add(extrude_input2)

    extrude_input3 = comp.features.extrudeFeatures.createInput(sketch.profiles[5], 0)
    extrude_input3.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('5.5 mm')),
        0,
        adsk.core.ValueInput.createByString('0 deg'),
    )
    comp.features.extrudeFeatures.add(extrude_input3)

    oc2 = adsk.core.ObjectCollection.create()
    oc2.add(sketch.profiles[2])
    oc2.add(sketch.profiles[4])

    path = comp.features.createPath(path_line)
    sweep_input = comp.features.sweepFeatures.createInput(oc2, path, 0)
    sweep_input.twistAngle = adsk.core.ValueInput.createByReal(math.radians(396))
    f2 = comp.features.sweepFeatures.add(sweep_input)

    _group_timeline(des, f1, f2)


def _build_male_lock_internal(comp, des, sketch, point_prim, hole, clearance):
    point_prim.translateBy(adsk.core.Vector3D.create(0, 0, -0.55))

    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        point_prim,
        _male_base_diameter(clearance) / 2,
    )
    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, hole / 2)

    path_line = _build_male_thread_geometry(sketch, point_prim)

    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, 0.4)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, 0.5)

    oc2 = adsk.core.ObjectCollection.create()
    oc2.add(sketch.profiles[0])
    oc2.add(sketch.profiles[1])
    oc2.add(sketch.profiles[3])

    path = comp.features.createPath(path_line)
    sweep_input = comp.features.sweepFeatures.createInput(oc2, path, 1)
    sweep_input.twistAngle = adsk.core.ValueInput.createByReal(math.radians(396))
    f1 = comp.features.sweepFeatures.add(sweep_input)

    oc1 = adsk.core.ObjectCollection.create()
    oc1.add(sketch.profiles[0])
    oc1.add(sketch.profiles[1])

    extrude_input1 = comp.features.extrudeFeatures.createInput(oc1, 0)
    extrude_input1.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('7.5 mm')),
        0,
        adsk.core.ValueInput.createByString('-1.72 deg'),
    )
    comp.features.extrudeFeatures.add(extrude_input1)

    extrude_input2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
    extrude_input2.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('7.5 mm')),
        0,
        adsk.core.ValueInput.createByString('0 deg'),
    )
    f2 = comp.features.extrudeFeatures.add(extrude_input2)

    _group_timeline(des, f1, f2)


def _build_female_slip(comp, des, sketch, point_prim, hole, clearance):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, 0.65 / 2)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        point_prim,
        (0.43 - math.tan(math.radians(3.44)) * 0.9 + clearance) / 2,
    )

    extrude_input1 = comp.features.extrudeFeatures.createInput(sketch.profiles[0], 0)
    extrude_input1.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('9 mm')),
        0,
        adsk.core.ValueInput.createByString('0 deg'),
    )
    f1 = comp.features.extrudeFeatures.add(extrude_input1)

    extrude_input2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
    extrude_input2.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('9 mm')),
        0,
        adsk.core.ValueInput.createByString('1.72 deg'),
    )
    f2 = comp.features.extrudeFeatures.add(extrude_input2)

    _group_timeline(des, f1, f2)


def _build_female_slip_internal(comp, des, sketch, point_prim, hole, clearance):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        point_prim,
        (0.43 + clearance) / 2,
    )

    extrude_input1 = comp.features.extrudeFeatures.createInput(sketch.profiles[0], 1)
    extrude_input1.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('-9 mm')),
        0,
        adsk.core.ValueInput.createByString('-1.72 deg'),
    )
    f1 = comp.features.extrudeFeatures.add(extrude_input1)

    _group_timeline(des, f1, f1)


def _build_female_lock(comp, des, sketch, point_prim, hole, clearance):
    sketch.sketchCurves.sketchCircles.addByCenterRadius(point_prim, 0.67 / 2)
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        point_prim,
        (0.43 - math.tan(math.radians(3.44)) * 0.9 + clearance) / 2,
    )

    offset_od_arc = adsk.core.Vector3D.create(-0.124, 0.3695, 0)
    offset_csa1 = adsk.core.Vector3D.create(-0.1487, 0.0435, 0)
    offset_csa2 = adsk.core.Vector3D.create(-0.0156, 0.1534, 0)
    offset_line = adsk.core.Vector3D.create(0, 0, 0.9)

    pos_od_arc = point_prim.copy()
    pos_od_arc.translateBy(offset_od_arc)

    pos_csa1 = point_prim.copy()
    pos_csa1.translateBy(offset_csa1)

    pos_csa2 = point_prim.copy()
    pos_csa2.translateBy(offset_csa2)

    offset_od_arc.scaleBy(-1)
    offset_csa1.scaleBy(-1)
    offset_csa2.scaleBy(-1)

    pos_od_arc2 = point_prim.copy()
    pos_od_arc2.translateBy(offset_od_arc)

    pos_csa3 = point_prim.copy()
    pos_csa3.translateBy(offset_csa1)

    pos_csa4 = point_prim.copy()
    pos_csa4.translateBy(offset_csa2)

    pos_line = point_prim.copy()
    pos_line.translateBy(offset_line)

    od_arc1 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(point_prim, pos_od_arc, math.radians(42.4))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa1, od_arc1.startSketchPoint, math.radians(-22.8))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa2, od_arc1.endSketchPoint, math.radians(22.8))

    od_arc2 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(point_prim, pos_od_arc2, math.radians(42.4))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa3, od_arc2.startSketchPoint, math.radians(-22.8))
    sketch.sketchCurves.sketchArcs.addByCenterStartSweep(pos_csa4, od_arc2.endSketchPoint, math.radians(22.8))

    path_line = sketch.sketchCurves.sketchLines.addByTwoPoints(point_prim, pos_line)

    extrude_input1 = comp.features.extrudeFeatures.createInput(sketch.profiles[3], 0)
    extrude_input1.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('9 mm')),
        0,
        adsk.core.ValueInput.createByString('0 deg'),
    )
    f1 = comp.features.extrudeFeatures.add(extrude_input1)

    extrude_input2 = comp.features.extrudeFeatures.createInput(sketch.profiles[0], 1)
    extrude_input2.setOneSideExtent(
        adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('9 mm')),
        0,
        adsk.core.ValueInput.createByString('1.72 deg'),
    )
    comp.features.extrudeFeatures.add(extrude_input2)

    oc = adsk.core.ObjectCollection.create()
    oc.add(sketch.profiles[1])
    oc.add(sketch.profiles[2])

    path = comp.features.createPath(path_line)
    sweep_input = comp.features.sweepFeatures.createInput(oc, path, 0)
    sweep_input.twistAngle = adsk.core.ValueInput.createByReal(math.radians(648))
    f2 = comp.features.sweepFeatures.add(sweep_input)

    _group_timeline(des, f1, f2)


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------


def _get_primitive_from_selection(selection):
    obj_type = selection.objectType

    if obj_type == 'adsk::fusion::ConstructionPlane':
        return selection.geometry

    if obj_type == 'adsk::fusion::Profile':
        return adsk.core.Plane.createUsingDirections(
            selection.parentSketch.origin,
            selection.parentSketch.xDirection,
            selection.parentSketch.yDirection,
        )

    if obj_type == 'adsk::fusion::BRepFace':
        _, normal = selection.evaluator.getNormalAtPoint(selection.pointOnFace)
        return adsk.core.Plane.create(selection.pointOnFace, normal)

    if obj_type == 'adsk::fusion::ConstructionAxis':
        return selection.geometry

    if obj_type == 'adsk::fusion::BRepEdge':
        if selection.geometry.objectType == 'adsk::core::Line3D':
            _, tangent = selection.evaluator.getTangent(0)
            return adsk.core.InfiniteLine3D.create(selection.pointOnEdge, tangent)
        if selection.geometry.objectType in ('adsk::core::Circle3D', 'adsk::core::Arc3D'):
            return selection.geometry.center

    if obj_type == 'adsk::fusion::SketchLine':
        return selection.worldGeometry.asInfiniteLine()

    if obj_type == 'adsk::fusion::ConstructionPoint':
        return selection.geometry

    if obj_type == 'adsk::fusion::SketchPoint':
        return selection.worldGeometry

    if obj_type == 'adsk::fusion::BRepVertex':
        return selection.geometry


def _project_point_on_plane(point, plane):
    origin_to_point = plane.origin.vectorTo(point)

    normal = plane.normal.copy()
    normal.normalize()
    dist = normal.dotProduct(origin_to_point)

    normal.scaleBy(-dist)
    projected = point.copy()
    projected.translateBy(normal)
    return projected
