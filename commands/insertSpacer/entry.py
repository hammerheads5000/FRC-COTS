import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
from ..insertPart.entry import joint_part, find_normal_centroid

app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_NAME = 'FRC_COTS Insert Spacer'
CMD_Description = 'Insert a dynamic spacer'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = False

# Define the location where the command button will be created.
# This is done by specifying the workspace, the tab, and the panel, and the 
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'InsertPanel'
COMMAND_BESIDE_ID = ''

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# The datafile to be inserted.  Set in FRC_COTS.py - FRCHTMLHandler()
g_dataFile = adsk.core.DataFile.cast(None)

# The active component
g_active_occ = adsk.fusion.Occurrence.cast(None)

# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        config.INSERT_SPACER_CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event.
    futil.add_handler(cmd_def.commandCreated, command_created)

# Executed when add-in is stopped.
def stop():
    # Get the cmddef for this command
    command_definition = ui.commandDefinitions.itemById(config.INSERT_SPACER_CMD_ID)

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # TODO Define the dialog for your command by adding different inputs to the command.

    # Create a simple read only text box.
    partFile = inputs.addTextBoxCommandInput('insert_part', '', '', 1, True)
    partFile.isFullWidth = True

    # Create a selection input for the joint location.
    sel = inputs.addSelectionInput('target_entity', 'Start', 'Select face or circle/arc')
    sel.addSelectionFilter('PlanarFaces')
    sel.addSelectionFilter('CircularEdges')
    sel.addSelectionFilter('JointOrigins')
    sel.addSelectionFilter('SketchPoints')
    sel.addSelectionFilter('ConstructionPoints')
    sel.addSelectionFilter('Vertices')
    sel.setSelectionLimits(1, 1)

    extentType = inputs.addDropDownCommandInput(
        'extent_type', 'Extent Type', adsk.core.DropDownStyles.LabeledIconDropDownStyle
    )
    dditems = extentType.listItems
    dditems.add('Distance', False, os.path.join(ICON_FOLDER, 'Dist'))
    dditems.add('To Object', True, os.path.join(ICON_FOLDER, 'To'))

    # Create a selection input for the 'To Object' selection.
    extent = inputs.addSelectionInput('extent_selection', 'Object', 'Select face, point, or edge')
    extent.addSelectionFilter('PlanarFaces')
    extent.addSelectionFilter('CircularEdges')
    extent.addSelectionFilter('SketchPoints')
    extent.addSelectionFilter('ConstructionPoints')
    extent.addSelectionFilter('Vertices')
    extent.setSelectionLimits(1, 1)
    extent.isVisible = True

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = app.activeProduct.unitsManager.defaultLengthUnits
    default_value = adsk.core.ValueInput.createByString('1')
    distInp = inputs.addValueInput('spacer_length', 'Distance', defaultLengthUnits, default_value)
    distInp.isVisible = False

    default_value = adsk.core.ValueInput.createByString('0')
    startOffset = inputs.addValueInput('start_offset', 'Start Offset', defaultLengthUnits, default_value)
    endOffset = inputs.addValueInput('end_offset', 'End Offset', defaultLengthUnits, default_value)

    # Create a selection input for multiple copies.
    copies = inputs.addSelectionInput('spacer_copies', 'Copies', 'Select face, point, or edge')
    copies.addSelectionFilter('PlanarFaces')
    copies.addSelectionFilter('CircularEdges')
    copies.addSelectionFilter('SketchPoints')
    copies.addSelectionFilter('ConstructionPoints')
    copies.addSelectionFilter('Vertices')
    copies.setSelectionLimits(0, 0)
    copies.isVisible = True

    flipInp = inputs.addBoolValueInput('force_flip', 'Flip', True, os.path.join(ICON_FOLDER, 'Flip'))

    # Connect to the events that are needed by this command.
    # futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.preSelect, command_preselect, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)

    global g_dataFile
    partFile.text = g_dataFile.name

    global g_active_occ
    design: adsk.fusion.Design = adsk.fusion.Design.cast(app.activeProduct)
    active_comp = design.activeComponent
    occList = design.rootComponent.allOccurrencesByComponent( active_comp )
    if occList.count == 0:
        return
    g_active_occ = occList.item(0)

    design.activateRootComponent()

# Only allow selection of an extent entity with a parallel plane to the target entity
def command_preselect(args: adsk.core.SelectionEventArgs):
    inputs: adsk.core.CommandInputs = args.firingEvent.sender.commandInputs

    targetInp: adsk.core.SelectionCommandInput = inputs.itemById('target_entity')
    extentInp: adsk.core.SelectionCommandInput = inputs.itemById('extent_selection')

    if targetInp.selectionCount == 0 and extentInp.selectionCount == 0:
        return
    
    already_selected = None
    if args.activeInput.id == extentInp.id:
        # We are selecting the extent selection
        already_selected = targetInp
    elif args.activeInput.id == targetInp.id and extentInp.isVisible:
        # We are selecting the target selection
        already_selected = extentInp
    else:
        return
    
    if not already_selected:
        return
    
    target = already_selected.selection(0).entity
    targetNorm, centroid = find_normal_centroid(target)
    selNorm, centroid = find_normal_centroid(args.selection.entity)

    if not targetNorm.isParallelTo(selNorm) :
        # Do not allow selection of non-coplanar faces
        args.isSelectable = False

# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    global g_dataFile
    global g_active_occ

     # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs

    target_selInput: adsk.core.SelectionCommandInput = inputs.itemById('target_entity')
    target_entity = target_selInput.selection(0).entity

    extentInp: adsk.core.SelectionCommandInput = inputs.itemById('extent_selection')
    extentType: adsk.core.DropDownCommandInput = inputs.itemById('extent_type')
    distanceInp: adsk.core.ValueCommandInput = inputs.itemById('spacer_length')
    startOffset: adsk.core.ValueCommandInput = inputs.itemById('start_offset')
    endOffset: adsk.core.ValueCommandInput = inputs.itemById('end_offset')
    copies: adsk.core.SelectionCommandInput = inputs.itemById('spacer_copies')

    flipInp: adsk.core.BoolValueCommandInput = inputs.itemById('force_flip')
    force_flip = flipInp.value

    # Determine how long the spacer should be
    spacer_length = 2.0 * 2.54
    extrude_flip = False
    if extentType.selectedItem.name == 'Distance':
        spacer_length = distanceInp.value + startOffset.value
    else:
        extent = extentInp.selection(0).entity
        selection_distance = app.measureManager.measureMinimumDistance(target_entity, extent)
        spacer_length = selection_distance.value + startOffset.value + endOffset.value

        extrude_flip = determine_extrude_flip(target_entity, extent)

    design: adsk.fusion.Design = adsk.fusion.Design.cast(app.activeProduct)

    start_timeline_pos = design.timeline.markerPosition

    target = target_selInput.selection(0).entity

    if g_active_occ:
        active_comp = g_active_occ.component
    else:
        active_comp = design.rootComponent

    transform = adsk.core.Matrix3D.create()
    occs = active_comp.occurrences
    new_occ = occs.addByInsert(
        g_dataFile,
        transform,
        False  # reference to original design
    )

    insert = design.timeline.item(start_timeline_pos)
    if insert.isGroup:
        # Delete the group so the whole command can be grouped
        insert = adsk.fusion.TimelineGroup.cast(insert)
        insert.deleteMe(False)

    top_face = find_offset_face(new_occ, True)
    offset_face = find_offset_face(new_occ)
    tempBR = adsk.fusion.TemporaryBRepManager.get()
    body1 = tempBR.copy(top_face)
    body2 = tempBR.copy(offset_face)
    model_length = app.measureManager.measureMinimumDistance(body1, body2)

    joint_part(active_comp, target, new_occ, force_flip ^ extrude_flip)

    bottom_dist = spacer_length - model_length.value - startOffset.value
    if abs(bottom_dist) > 0.0001:
        bottom_distInp = adsk.core.ValueInput.createByReal(bottom_dist)
        offset_input = active_comp.features.offsetFacesFeatures.createInput( [offset_face], bottom_distInp)
        active_comp.features.offsetFacesFeatures.add(offset_input)

    if abs(startOffset.value) > 0.0001:
        top_dist = adsk.core.ValueInput.createByReal(startOffset.value)
        offset_input = active_comp.features.offsetFacesFeatures.createInput( [top_face], top_dist)
        active_comp.features.offsetFacesFeatures.add(offset_input)

    new_occ.component.name = g_dataFile.name + f' x {spacer_length/2.54:.3f}in'

    if copies.selectionCount > 0:
        for sidx in range(copies.selectionCount):
            copy_location_entity = copies.selection(sidx).entity
            copy_occ = occs.addExistingComponent(new_occ.component, transform)
            joint_part(active_comp, copy_location_entity, copy_occ, force_flip ^ extrude_flip)

    end_timeline_pos = design.timeline.markerPosition - 1
    grp = design.timeline.timelineGroups.add( start_timeline_pos, end_timeline_pos )
    grp.name = "Insert Spacer"

    args.isValidResult = True
    
    # This was needed once debugging output was turned off....
    app.activeViewport.refresh()

# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    target_selInput: adsk.core.SelectionCommandInput = inputs.itemById('target_entity')
    extentInp: adsk.core.SelectionCommandInput = inputs.itemById('extent_selection')
    extentType: adsk.core.DropDownCommandInput = inputs.itemById('extent_type')
    distanceInp: adsk.core.ValueCommandInput = inputs.itemById('spacer_length')
    endOffset: adsk.core.ValueCommandInput = inputs.itemById('end_offset')
    copiesInp: adsk.core.SelectionCommandInput = inputs.itemById('spacer_copies')

    if changed_input.id == 'target_entity' :
        if target_selInput.selectionCount > 0:
            if extentInp.isVisible:
                extentInp.hasFocus = True
            else:
                copiesInp.hasFocus = True

    elif changed_input.id == 'extent_selection' :
        if target_selInput.selectionCount == 0 :
            target_selInput.hasFocus = True
        else:
            copiesInp.hasFocus = True
            
    elif changed_input.id == 'extent_type' :
        if extentType.selectedItem.name == 'Distance':
            extentInp.clearSelection()
            extentInp.setSelectionLimits(0, 1)
            distanceInp.isVisible = True
            extentInp.isVisible = False
            endOffset.isVisible = False
            if target_selInput.selectionCount == 0:
                target_selInput.hasFocus = True
        else:
            extentInp.setSelectionLimits(1, 1)
            distanceInp.isVisible = False
            extentInp.isVisible = True
            endOffset.isVisible = True
            if target_selInput.selectionCount == 0:
                target_selInput.hasFocus = True
            else:
                extentInp.hasFocus = True

# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Validate Input Event')

    inputs = args.inputs
    
    # # Verify the validity of the input values. This controls if the OK button is enabled or not.
    # valueInput = inputs.itemById('value_input')
    # if valueInput.value >= 0:
    #     args.areInputsValid = True
    # else:
    #     args.areInputsValid = False
        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global g_active_occ
    if g_active_occ:
        g_active_occ.activate()
    g_active_occ = None

    global local_handlers
    local_handlers = []

def find_offset_face( occ: adsk.fusion.Occurrence, jointFace: bool = False):
    if occ.bRepBodies.count > 1:
        futil.log(f'Cannot handle spacers with more than one body!')
        return None
    
    # Default to top face pointing in the positive Z-direction
    plus_Z = adsk.core.Vector3D.create(0,0,1)
    joint_origin = None
    if occ.component.jointOrigins.count > 0:
        joint_origin = occ.component.jointOrigins.item(0)
        # Use the joint origin primary direction
        plus_Z = joint_origin.primaryAxisVector
        if joint_origin.isFlipped:
            plus_Z.scaleBy(-1.0)
    
    dotProd = -1.0
    if jointFace:
        dotProd = 1.0

    # if joint_origin:
    #     if joint_origin.isFlipped:
    #         dotProd = dotProd * -1.0

    body = occ.bRepBodies.item(0)
    for face in body.faces:
        ok, normal = face.evaluator.getNormalAtPoint(face.centroid)
        # futil.log(f'Evaluator normal = {normal.x},{normal.y},{normal.z}')
        if isinstance(face.geometry, adsk.core.Plane):
            if normal.isParallelTo(plus_Z) and abs(normal.dotProduct(plus_Z)-dotProd) < 0.0001:
                futil.log(f'Planar face parallel to Z-direction and pointing in the right direction!..')
                return face
            
    return None

def determine_extrude_flip( start: adsk.core.Base, end: adsk.core.Base) -> bool:

    start_normal, start_centroid = find_normal_centroid(start)
    end_normal, end_centroid = find_normal_centroid(end)

    start_to_end_normal = start_centroid.vectorTo(end_centroid)
    start_to_end_normal.normalize()

    stoend_z_dot = start_normal.dotProduct(start_to_end_normal)

    return stoend_z_dot < 0

