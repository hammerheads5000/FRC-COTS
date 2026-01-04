import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config
app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
# CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_insertPart'
CMD_NAME = 'FRC_COTS Insert Part'
CMD_Description = 'Insert a COTS part'

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

# The active component
g_active_occ = adsk.fusion.Occurrence.cast(None)

# Executed when add-in is run.
def start():
    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        config.INSERT_PART_CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)


# Executed when add-in is stopped.
def stop():
    # Get the cmddef for this command
    command_definition = ui.commandDefinitions.itemById(config.INSERT_PART_CMD_ID)

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    
    # General logging for debug.
    futil.log(f'{args.command.parentCommandDefinition.id} Command Created Event')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # TODO Define the dialog for your command by adding different inputs to the command.

    # Create a simple text box input.
    partFile = inputs.addTextBoxCommandInput('insert_part', 'Part:', '', 2, True)

    # Create a selection input for the joint locations.
    sel = inputs.addSelectionInput('target_entity', 'Joints:', 'Select face or circle')
    sel.addSelectionFilter('PlanarFaces')
    sel.addSelectionFilter('CircularEdges')
    sel.addSelectionFilter('JointOrigins')
    sel.addSelectionFilter('SketchPoints')
    sel.addSelectionFilter('ConstructionPoints')
    sel.addSelectionFilter('Vertices')
    sel.setSelectionLimits(1, 0)

    # zero = adsk.core.ValueInput.createByReal(0)
    # angleInp = inputs.addAngleValueCommandInput( 'joint_angle', 'Angle', zero)
    # angleInp.isVisible = False
    # angleInp.isEnabled = False

    inputs.addBoolValueInput( 'force_flip', 'Flip', True, os.path.join(ICON_FOLDER, 'Flip'))

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
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

# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{args.command.parentCommandDefinition.id} Command Execute Event')

    # TODO ******************************** Your code here ********************************

    # Get a reference to your command's inputs.
    inputs = args.command.commandInputs
    target_entity: adsk.core.SelectionCommandInput = inputs.itemById('target_entity')


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    global g_dataFile
    global g_active_occ

     # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs

    target_selInput: adsk.core.SelectionCommandInput = inputs.itemById('target_entity')
    # angleInp: adsk.core.AngleValueCommandInput = inputs.itemById('joint_angle')
    flipInp: adsk.core.BoolValueCommandInput = inputs.itemById('force_flip')
    force_flip = flipInp.value

    # futil.log(f'Angle = {angleInp.expression}')

    design: adsk.fusion.Design = adsk.fusion.Design.cast(app.activeProduct)

    if g_active_occ:
        active_comp = g_active_occ.component
    else:
        active_comp = design.rootComponent

    root_occs = design.rootComponent.occurrences

    transform = adsk.core.Matrix3D.create()
    part_occ = adsk.fusion.Occurrence.cast(None)
    for i in range( target_selInput.selectionCount):
        target = target_selInput.selection(i).entity
        # if part_occ:
        #     part_occ = occs.addExistingComponent( part_occ.component, transform )
        #     joint_part(active_comp, target, part_occ, force_flip)
        # else:
        if 1:
            # A bug makes so you can only insert a linked component from another project
            # into the root component.  So we have to move it if a sub component
            # is the active component.
            part_occ = root_occs.addByInsert( g_dataFile, transform, True )
            if active_comp.id != design.rootComponent.id:
                # futil.log(f'Active comp: name = {active_comp.name}, comp_id = {active_comp.id}')
                # active_occ = None
                # for occ in  root_occs.asArray():
                #     futil.log(f'Root occurance name = {occ.name}, comp_name={occ.component.name}, comp_id = {occ.component.id}')
                occList = design.rootComponent.allOccurrencesByComponent( active_comp )
                if occList.count == 0:
                    return
                active_occ = occList.item(0)
                # temp_occ = None
                # if occs.count == 0:
                #     temp_occ = occs.addNewComponent(transform)
                #     # copied_occ = occs.addExistingComponent( part_occ.component, transform )
                #     # part_occ.deleteMe()
                #     # part_occ = copied_occ
                part_occ = part_occ.moveToComponent( active_occ )
                # if temp_occ:
                #     pass
                    # temp_occ.deleteMe()
            # angleVal = adsk.core.ValueInput.createByString(angleInp.expression)
            joint_part(active_comp, target, part_occ, force_flip)

    args.isValidResult = True


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs

    # General logging for debug.
    # futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    target_selInput: adsk.core.SelectionCommandInput = inputs.itemById('target_entity')
    # angleInp: adsk.core.AngleValueCommandInput = inputs.itemById('joint_angle')

    # if changed_input.id == 'target_entity' :
    #     if target_selInput.selectionCount == 0:
    #         angleInp.isVisible = False
    #         angleInp.isEnabled = False
    #     elif target_selInput.selectionCount == 1:
    #         angleInp.isVisible = True
    #         angleInp.isEnabled = True
    #         normal, centroid = find_normal_centroid( target_selInput.selection(0).entity )
    #         plane = adsk.core.Plane.create( centroid, normal )
    #         angleInp.setManipulator( centroid, plane.uDirection, plane.vDirection )
    #     else:
    #         angleInp.isVisible = True
    #         angleInp.isEnabled = False

# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    # futil.log(f'{CMD_NAME} Validate Input Event')

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


def joint_part(
        comp: adsk.fusion.Component, 
        target: adsk.core.Base, 
        part_occ: adsk.fusion.Occurrence,
        force_flip: bool = False
):
    joints = comp.joints

    try:
        part_occ.isGroundToParent = False
    except:
        pass

    isPartFlipped, joint_geo_cots = get_part_joint(part_occ)
    isTargetFlipped, joint_geo_target = create_joint_from_entity(target, comp)

    if joint_geo_target:
        joint_input = joints.createInput(
            joint_geo_cots,
            joint_geo_target
        )
        joint_input.setAsRigidJointMotion()

        # Flip the default joint orientation (for example, 180 degrees about its primary axis)
        try:
            joint_input.isFlipped = isPartFlipped ^ isTargetFlipped
            joint_input.isFlipped = joint_input.isFlipped ^ force_flip
        except:
            # If this property is not available, just ignore and proceed
            pass

        joints.add(joint_input)

def get_part_joint(part_occ: adsk.fusion.Occurrence) -> adsk.fusion.JointGeometry:
    comp = part_occ.component

    # If the part has a joint origin then use it
    if comp.jointOrigins.count > 0 :
        joint_origin = comp.jointOrigins.item(0)
        new_joint_occ = joint_origin.createForAssemblyContext(part_occ)
        return False, new_joint_occ
    
    # No joint origin so we use the coordinate origin
    origin_native = comp.originConstructionPoint
    if not origin_native:
        ui.messageBox(
            "Inserted component '{}' has no originConstructionPoint.".format(comp.name)
        )
        return None

    origin_proxy = origin_native.createForAssemblyContext(part_occ)
    if not origin_proxy:
        ui.messageBox(
            "Failed to create origin proxy for '{}'.".format(comp.name)
        )
        return None
    
    joint_geo_cots = adsk.fusion.JointGeometry.createByPoint(origin_proxy)

    return False, joint_geo_cots

def create_joint_from_entity(entity: adsk.core.Base, occ: adsk.fusion.Occurrence = None ):
    joint_geo_target = None
    isFlipped = False

    try:
        if occ:
            entity = entity.createForAssemblyContext(occ)
    except:
        pass

    if isinstance(entity, adsk.fusion.BRepEdge):
        entity = adsk.fusion.BRepEdge.cast(entity)
        normal = None
        planeFace = None
        for face in entity.faces:
            if isinstance(face.geometry, adsk.core.Plane):
                planeFace = face
                _, normal = face.evaluator.getNormalAtPoint(planeFace.centroid)
                break
        if normal:
            joint_geo_target = adsk.fusion.JointGeometry.createByPlanarFace(
                planeFace,
                entity,
                adsk.fusion.JointKeyPointTypes.CenterKeyPoint
            )
            isFlipped = True
        else:
            joint_geo_target = adsk.fusion.JointGeometry.createByCurve(
                entity,
                adsk.fusion.JointKeyPointTypes.CenterKeyPoint
            )

    elif isinstance(entity, adsk.fusion.BRepFace):
        face = entity
        surf = face.geometry

        if isinstance(surf, adsk.core.Plane):
            joint_geo_target = adsk.fusion.JointGeometry.createByPlanarFace(
                face,
                None,
                adsk.fusion.JointKeyPointTypes.CenterKeyPoint
            )
            isFlipped = True
        else:
            joint_geo_target = adsk.fusion.JointGeometry.createByNonPlanarFace(
                face,
                None
            )

    elif isinstance(entity, adsk.fusion.BRepVertex):
        joint_geo_target = adsk.fusion.JointGeometry.createByPoint(entity)
    elif isinstance(entity, adsk.fusion.ConstructionPoint):
        joint_geo_target = adsk.fusion.JointGeometry.createByPoint(entity)
    elif isinstance(entity, adsk.fusion.SketchPoint):
        joint_geo_target = adsk.fusion.JointGeometry.createByPoint(entity)

    elif isinstance(entity, adsk.fusion.JointOrigin):
        joint_geo_target = entity
    else:
        ui.messageBox(
            "Unsupported selection type for joint target: {}".format(
                type(entity)
            )
        )

    return isFlipped, joint_geo_target

def find_normal_centroid( entity: adsk.core.Base) -> tuple[adsk.core.Vector3D, adsk.core.Point3D]:

    if isinstance(entity, adsk.fusion.BRepEdge):
        edge: adsk.fusion.BRepEdge = entity
        for face in edge.faces:
            if isinstance(face.geometry, adsk.core.Plane):
                _, normal = face.evaluator.getNormalAtPoint(face.centroid)
                return normal, face.centroid

    elif isinstance(entity, adsk.fusion.BRepFace):
        brFace: adsk.fusion.BRepFace = entity
        if isinstance(brFace.geometry, adsk.core.Plane):
            _, normal = brFace.evaluator.getNormalAtPoint(brFace.centroid)
            return normal, brFace.centroid

    elif isinstance(entity, adsk.fusion.JointOrigin):
        jo: adsk.fusion.JointOrigin = entity
        return jo.primaryAxisVector, jo.transform.translation.asPoint()

    else:
        futil.log(f'  ------- find_normal -----  Unhandled entity type "{entity.objectType}"')

    return adsk.core.Vector3D.create(0,0,1), adsk.core.Point3D.create()