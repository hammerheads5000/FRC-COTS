import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
from ..insertPart.entry import joint_part

app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_NAME = 'FRC_COTS Insert Spacer'
CMD_Description = 'Insert a dynamic spacer'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = False

# TODO *** Define the location where the command button will be created. ***
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

# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        config.INSERT_SPACER_CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    # workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # # Get the panel the button will be created in.
    # panel = workspace.toolbarPanels.itemById(PANEL_ID)

    # # Create the button command control in the UI after the specified existing command.
    # control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

    # # Specify if the command is promoted to the main toolbar. 
    # control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    # workspace = ui.workspaces.itemById(WORKSPACE_ID)
    # panel = workspace.toolbarPanels.itemById(PANEL_ID)
    # command_control = panel.controls.itemById(config.INSERT_SPACER_CMD_ID)
    command_definition = ui.commandDefinitions.itemById(config.INSERT_SPACER_CMD_ID)

    # # Delete the button command control
    # if command_control:
    #     command_control.deleteMe()

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
    sel.setSelectionLimits(1, 1)

    extentType = inputs.addDropDownCommandInput(
        'extent_type', 'Extent Type', adsk.core.DropDownStyles.LabeledIconDropDownStyle
    )
    dditems = extentType.listItems
    dditems.add('Distance', False, os.path.join(ICON_FOLDER, 'Dist'))
    dditems.add('To Object', True, os.path.join(ICON_FOLDER, 'To'))

    # Create a selection input for the joint location.
    extent = inputs.addSelectionInput('extent_selection', 'Object', 'Select face, point, or edge')
    extent.addSelectionFilter('PlanarFaces')
    extent.addSelectionFilter('CircularEdges')
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

    flipInp = inputs.addBoolValueInput('force_flip', 'Flip', True, os.path.join(ICON_FOLDER, 'Flip'))

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)

    global g_dataFile
    partFile.text = g_dataFile.name


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')

    # TODO ******************************** Your code here ********************************

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    target_entity: adsk.core.SelectionCommandInput = inputs.itemById('target_entity')




# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    global g_dataFile

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

    flipInp: adsk.core.BoolValueCommandInput = inputs.itemById('force_flip')
    force_flip = flipInp.value

    # Determine how long the spacer should be
    spacer_length = 2.0 * 2.54
    if extentType.selectedItem.name == 'Distance':
        spacer_length = distanceInp.value + startOffset.value
    else:
        extent = extentInp.selection(0).entity
        selection_distance = app.measureManager.measureMinimumDistance(target_entity, extent)
        spacer_length = selection_distance.value + startOffset.value + endOffset.value

    design: adsk.fusion.Design = adsk.fusion.Design.cast(app.activeProduct)

    root_comp = design.rootComponent

    start_timeline_pos = design.timeline.markerPosition

    target = target_selInput.selection(0).entity

    transform = adsk.core.Matrix3D.create()
    occs = root_comp.occurrences
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

    new_occ.isGroundToParent = False

    top_face = find_offset_face(new_occ, True)
    offset_face = find_offset_face(new_occ)
    model_length = app.measureManager.measureMinimumDistance(top_face, offset_face)

    joint_part(root_comp, target, new_occ, force_flip)

    bottom_dist = adsk.core.ValueInput.createByReal(spacer_length - model_length.value - startOffset.value)
    offset_input = root_comp.features.offsetFacesFeatures.createInput( [offset_face], bottom_dist)
    root_comp.features.offsetFacesFeatures.add(offset_input)

    top_dist = adsk.core.ValueInput.createByReal(startOffset.value)
    offset_input = root_comp.features.offsetFacesFeatures.createInput( [top_face], top_dist)
    root_comp.features.offsetFacesFeatures.add(offset_input)

    new_occ.component.name = g_dataFile.name + f' x {spacer_length/2.54:.3f}in'

    end_timeline_pos = design.timeline.markerPosition - 1
    grp = design.timeline.timelineGroups.add( start_timeline_pos, end_timeline_pos )
    grp.name = "Insert Spacer"

    args.isValidResult = True


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

    if changed_input.id == 'target_entity' :
        if target_selInput.selectionCount > 0 and extentInp.isVisible:
            extentInp.hasFocus = True

    if changed_input.id == 'extent_selection' :
        if extentInp.selectionCount == 0 and target_selInput.selectionCount == 0 :
            target_selInput.hasFocus = True

    if changed_input.id == 'extent_type' :
        if extentType.selectedItem.name == 'Distance':
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

    global local_handlers
    local_handlers = []

def find_offset_face( occ: adsk.fusion.Occurrence, topFace: bool = False):
    if occ.bRepBodies.count > 1:
        futil.log(f'Cannot handle spacers with more than one body!')
        return None
    
    # Default to top face pointing in the positive Z-direction
    plus_Z = adsk.core.Vector3D.create(0,0,1)
    if occ.component.jointOrigins.count > 0:
        joint_origin = occ.component.jointOrigins.item(0)
        # Use the joint origin primary direction
        plus_Z = joint_origin.primaryAxisVector
    
    dotProd = -1.0
    if topFace:
        dotProd = 1.0
    
    body = occ.bRepBodies.item(0)
    for face in body.faces:
        ok, normal = face.evaluator.getNormalAtPoint(face.centroid)
        # futil.log(f'Evaluator normal = {normal.x},{normal.y},{normal.z}')
        if isinstance(face.geometry, adsk.core.Plane):
            if normal.isParallelTo(plus_Z) and abs(normal.dotProduct(plus_Z)-dotProd) < 0.0001:
                futil.log(f'Planar face parallel to Z-direction and pointing in the right direction!..')
                return face
            
    return None
