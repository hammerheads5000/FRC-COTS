import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_makeSpacer'
CMD_NAME = 'FRC_COTS Make Spacer'
CMD_Description = 'Make a COTS part into a Dynamic Spacer'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# TODO *** Define the location where the command button will be created. ***
# This is done by specifying the workspace, the tab, and the panel, and the 
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = 'FusionSolidEnvironment'
TAB_ID = 'ToolsTab'
TAB_NAME = 'Make Spacer'

PANEL_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_makeSpacerPanel'
PANEL_NAME = 'Make Spacer'
COMMAND_BESIDE_ID = ''

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get the panel the button will be created in.
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

    # Get target panel for the command and and create the panel if necessary.
    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, '', False)

    # Create the button command control in the UI after the specified existing command.
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

    # Specify if the command is promoted to the main toolbar. 
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()

    # Delete the panel if it is empty
    if panel.controls.count == 0:
        panel.deleteMe()

    # Delete the tab if it is empty
    if toolbar_tab.toolbarPanels.count == 0:
        toolbar_tab.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # TODO Define the dialog for your command by adding different inputs to the command.

    mesg = ('This command makes a Part into a Dynamic Spacer. '
            'It does this by setting an invisible attribute in the file '
            'that can be detected when the part is inserted into a design.')

    # # Create a Text Box for information.
    text = inputs.addTextBoxCommandInput( 'info', '', mesg, 6, True)
    text.isFullWidth = True

    design: adsk.fusion.Design = app.activeProduct
    make_spacer = inputs.addBoolValueInput('make_spacer', 'Make Spacer', True)
    make_spacer.value = is_design_spacer(design)

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')


    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    # jointSel: adsk.core.SelectionCommandInput = inputs.itemById('jointing_position')
    makeSpacer: adsk.core.BoolValueCommandInput = inputs.itemById('make_spacer')

    design: adsk.fusion.Design = app.activeProduct

    # Delete any only joint attributes
    oldAttribs = design.findAttributes('FRC_COTS', 'joint')
    for oldAttrib in oldAttribs:
        oldAttrib.deleteMe()

    # if jointSel.selectionCount > 0:
    #     joint = jointSel.selection(0).entity
    #     if isinstance(joint, adsk.fusion.BRepEdge):
    #         edge: adsk.fusion.BRepEdge = joint
    #         edge.attributes.add( 'FRC_COTS', 'joint', '1' )
    #     elif isinstance(joint, adsk.fusion.BRepFace):
    #         face: adsk.fusion.BRepFace = joint
    #         face.attributes.add( 'FRC_COTS', 'joint', '1' )
    #     else:
    #         futil.log(f'Unhandled selection type "{joint.classType()}"')

    if makeSpacer.value:
        design.attributes.add( 'FRC_COTS', 'spacer', '1' )
    else:
        attr = design.attributes.itemByName( 'FRC_COTS', 'spacer' )
        if attr:
            attr.deleteMe()


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')


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

def is_design_spacer(design: adsk.fusion.Design):
    spacer_attr = design.attributes.itemByName('FRC_COTS', 'spacer')
    if spacer_attr:
        # This part is a spacer
        return True
    
    return False

def is_dataFile_spacer(dataFile: adsk.core.DataFile) -> bool:
    doc = app.documents.open(dataFile, False)
    design = doc.products.itemByProductType('DesignProductType')
    isSpacer = False
    if design:
        isSpacer = is_design_spacer(design)
    doc.close(False)

    return isSpacer