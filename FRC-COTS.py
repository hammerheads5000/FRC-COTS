import adsk.core
import adsk.fusion
import traceback
import json
import os
from . import config
from . import database_thread

from .lib import fusionAddInUtils as futil


# Keep a global reference to event handlers so they are not garbage collected.
handlers = []

# Custom event to signal the folder walker thread has finished and the
# palette needs to be updated and enabled
customEvent = None

# Global state
g_favorites = {}            # dataFile.id -> bool
g_palette = None            # HTML palette reference
g_dbThread = None

app = adsk.core.Application.get()
ui = app.userInterface

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')


def _ensure_file_paths_exist():
    if not os.path.exists(config.PARTS_DB_FOLDER):
        futil.popup_error(f'PARTS_DB_FOLDER = "{config.PARTS_DB_FOLDER}" does not exist!  '
                          + 'See config.py file')
        return False
    
    if not os.path.exists(config.PARTS_DB_PATH):
        try:
            os.mkdir(config.PARTS_DB_PATH)
        except:
            futil.popup_error(f'Cannot create PARTS_DB_PATH = "{config.PARTS_DB_PATH}".')
            return False

    icon_path = os.path.join(config.PARTS_DB_PATH, 'icons')
    if not os.path.exists(icon_path):
        try:
            os.mkdir(icon_path)
        except:
            futil.popup_error(f'Cannot create icons directory at "{icon_path}".')
            return False

    return True

def _delete_all_icons():
    icon_path = os.path.join(config.PARTS_DB_PATH, 'icons')
    for f in os.listdir(icon_path):
        try:
            os.remove(os.path.join(icon_path,f))
        except:
            pass
        
def _favorites_path():
    """Path to the favorites JSON file next to this add-in."""
    folder = config.PARTS_DB_PATH
    return os.path.join(folder, 'FRC_COTS_favorites.json')

def load_favorites():
    """Load favorites mapping from disk."""
    global g_favorites

    futil.log( f'Loading favorites...')

    try:
        path = _favorites_path()
        if os.path.exists(path):
            with open(path, 'r') as f:
                g_favorites = json.load(f)
        else:
            g_favorites = {}
    except Exception:
        g_favorites = {}


def save_favorites():
    """Persist favorites mapping to disk."""
    try:
        path = _favorites_path()
        with open(path, 'w') as f:
            json.dump(g_favorites, f, indent=2)
    except Exception:
        pass

def insert_part_at_targets(design: adsk.fusion.Design, path, label, data_file_id, targets, ui):
    """
    Insert the given DataFile into the root component and create joints
    from its origin to each of the target entities.
    """
    root_comp = design.rootComponent
    occs = root_comp.occurrences
    joints = root_comp.joints

    data_file = database_thread.get_data_file( path, data_file_id )
    if not data_file:
        return

    for target_entity in targets:
        # Insert as reference occurrence at identity transform
        transform = adsk.core.Matrix3D.create()
        new_occ = occs.addByInsert(
            data_file,
            transform,
            True  # reference to original design
        )

        # Ensure the inserted occurrence is not grounded so joints can move it
        try:
            new_occ.isGroundToParent = False
        except:
            # If this property is not available for any reason, ignore and continue
            pass

        comp = new_occ.component
        origin_native = comp.originConstructionPoint
        if not origin_native:
            ui.messageBox(
                "Inserted component '{}' has no originConstructionPoint.".format(label)
            )
            continue

        origin_proxy = origin_native.createForAssemblyContext(new_occ)
        if not origin_proxy:
            ui.messageBox(
                "Failed to create origin proxy for '{}'.".format(label)
            )
            continue

        joint_geo_cots = adsk.fusion.JointGeometry.createByPoint(origin_proxy)

        # Build target joint geometry based on the selected entity type
        joint_geo_target = None

        if isinstance(target_entity, adsk.fusion.BRepEdge):
            joint_geo_target = adsk.fusion.JointGeometry.createByCurve(
                target_entity,
                adsk.fusion.JointKeyPointTypes.CenterKeyPoint
            )

        elif isinstance(target_entity, adsk.fusion.BRepFace):
            face = target_entity
            surf = face.geometry

            if isinstance(surf, adsk.core.Plane):
                joint_geo_target = adsk.fusion.JointGeometry.createByPlanarFace(
                    face,
                    None,
                    adsk.fusion.JointKeyPointTypes.CenterKeyPoint
                )
            else:
                joint_geo_target = adsk.fusion.JointGeometry.createByNonPlanarFace(
                    face,
                    None
                )

        elif isinstance(target_entity, adsk.fusion.JointOrigin):
            joint_geo_target = adsk.fusion.JointGeometry.createByJointOrigin(
                target_entity
            )

        else:
            ui.messageBox(
                "Unsupported selection type for joint target: {}".format(
                    type(target_entity)
                )
            )
            continue

        if joint_geo_target is not None:
            joint_input = joints.createInput(
                joint_geo_cots,
                joint_geo_target
            )
            joint_input.setAsRigidJointMotion()

            # Flip the default joint orientation (for example, 180 degrees about its primary axis)
            try:
                joint_input.isFlipped = True
            except:
                # If this property is not available, just ignore and proceed
                pass

            joints.add(joint_input)


def _palette_html_path():
    """Path to the HTML palette file."""
    return os.path.join(os.path.dirname(__file__), 'frc_cots_palette.html')

def send_parts_to_palette(palette: adsk.core.Palette):
    """Send the parts list to the HTML palette used to browse COTS parts."""

    futil.log(f'send_parts_to_palette()....')

    try:
        parts = []
        cots_files = database_thread.get_sorted_database_list()
        for idx, (path, label, dfid, icon_name) in enumerate(cots_files):
            parts.append({
                'index': idx,
                'path': path,
                'label': label,
                'favorite': g_favorites.get(dfid, False),
                'thumb': icon_name
            })
        futil.log(f'   Sending {len(parts)} records to palette...')
        palette.sendInfoToHTML('partsList', json.dumps(parts))
    except:
        futil.handle_error('load_palette failed:')

def get_palette() -> adsk.core.Palette:
    """Return the HTML palette used to browse COTS parts."""
    global g_palette

    # futil.log(f'get_palette()....')

    # If we already have a valid reference, reuse it
    if g_palette and g_palette.isValid:
        return g_palette
    
    return None

def create_palette() -> adsk.core.Palette:
    """Create or return the HTML palette used to browse COTS parts."""
    global g_palette

    # futil.log(f'create_palette()....')

    # If we already have a valid reference, reuse it
    if g_palette and g_palette.isValid:
        return g_palette

    pal_id = 'FRC_COTS_Palette'
    pal: adsk.core.Palette = ui.palettes.itemById(pal_id)
    if pal and not pal.isValid:
        # Stale palette, remove so we can recreate
        pal.deleteMe()
        pal = None

    if not pal:
        html_path = _palette_html_path()
        url = 'file:///' + html_path.replace('\\', '/')
        pal = ui.palettes.add(
            pal_id,
            'FRC COTS Library',
            url,
            True,   # isVisible
            True,   # showCloseButton
            True,   # isResizable
            350,
            600
        )

        html_handler = FRCHTMLHandler()
        pal.incomingFromHTML.add(html_handler)
        handlers.append(html_handler)

        pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        pal.isVisible = False

    g_palette = pal
    return pal

# Event handler for the startupCompleted event.
# Need this when this Add-In is loaded on startup
class MyStartupCompletedHandler(adsk.core.ApplicationEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args: adsk.core.ApplicationEventArgs):
        global g_dbThread

        futil.log('In MyStartupCompletedHandler event handler.')
        # Start the database thread
        if not g_dbThread:
            g_dbThread = database_thread.DatabaseThread()
            g_dbThread.start()

class DatabaseThreadEventHandler(adsk.core.CustomEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args: adsk.core.CustomEventArgs):

        eventArgs = json.loads(args.additionalInfo)
        action = eventArgs['action']
        data = eventArgs['data']
        futil.log( f'DatabaseThreadEventHandler() -- Event "{action} data = {data}"')

        if action == "set_busy":
            palette = get_palette()
            if not palette:
                return
            palette.sendInfoToHTML( 'set_busy', data)

        elif action == "update":
            palette = get_palette()
            if not palette:
                return
            send_parts_to_palette(palette)

        elif action == "status":
            palette = get_palette()
            if not palette:
                return
            palette.sendInfoToHTML( 'status', data)

        else:
            futil.log( f'    ---------- Unhandled event "{action}"  ---------')

class FRCHTMLHandler(adsk.core.HTMLEventHandler):
    """Handles messages coming from the HTML palette."""

    def notify(self, args):
        try:
            action = args.action
            data = args.data or ''

            futil.log( f'FRCHTMLHandler() -- Event "{action}"')

            palette = get_palette()
            if not palette:
                futil.log( f'     ------------- ERROR Palette not valid!! ----------')
                return

            # HTML asks for the list of parts
            if action == 'requestParts':
                send_parts_to_palette(palette)

            # HTML palette is active and ready to receive data
            # send it the parts list
            elif action == 'ready':
                send_parts_to_palette(palette)

            # HTML tells us to insert the selected part at current canvas selection
            elif action == 'insertPart':
                try:
                    payload = json.loads(data) if data else {}
                    idx = int(payload.get('index', -1))
                except Exception:
                    idx = -1

                cots_files = database_thread.get_sorted_database_list()
                if idx < 0 or idx >= len(cots_files):
                    ui.messageBox('Invalid part index from HTML.')
                    return

                path, label, data_file_id, _ = cots_files[idx]

                # Get current canvas selections as targets
                sels = ui.activeSelections
                targets = [sels.item(i).entity for i in range(sels.count)]
                if not targets:
                    ui.messageBox(
                        'No geometry selected.\n\n'
                        'Select one or more faces, edges, or joint origins in the canvas, '
                        'then click the part in the FRC COTS palette.'
                    )
                    return

                design = adsk.fusion.Design.cast(app.activeProduct)
                if not design:
                    ui.messageBox('No active Fusion design.')
                    return

                insert_part_at_targets(design, path, label, data_file_id, targets, ui)
                return

            # User navigated to a new folder
            elif action == 'folderRequest':
                folder = '/' + data
                if len(data) > 1:
                    folder = folder + '/'
                futil.log( f'FRCHTMLHandler() -- Folder request for "{folder}"')
                database_thread.load_folder( folder )
                send_parts_to_palette(palette)
                
            # HTML toggles favorite state for a part
            elif action == 'toggleFavorite':
                try:
                    payload = json.loads(data) if data else {}
                    idx = int(payload.get('index', -1))
                    fav = bool(payload.get('favorite', False))
                except Exception:
                    idx = -1
                    fav = False

                cots_files = database_thread.get_sorted_database_list()
                if 0 <= idx < len(cots_files):
                    _, _label, dfid, _thumbidx = cots_files[idx]
                    g_favorites[dfid] = fav
                    save_favorites()
            elif action == "response":
                pass
            else:
                futil.log( f'    --------- Unhandled event "{action}" ----------')

        except:
            ui.messageBox('HTML palette error:\n{}'.format(traceback.format_exc()))

class ShowPaletteCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        global g_dbThread

        futil.log(f'ShowPaletteCreatedHandler::notify()...')
        palette_just_created = False
        palette = get_palette()
        if not palette:
            # The palette needs to be created.
            palette = create_palette()
            palette_just_created = True
            if not palette:
                futil.log(f'     ----------  ERROR Unable to Create Palette! ----------')
                return
            
        # There is an issue when a palette is first created and shown.
        # It takes a while for the Fusion part of the palette to be
        # ready to send/receive information (the adsk object).  For this
        # reason when the palette is first created and shown we need to
        # wait for the palette to send a 'ready' signal back before
        # loading the parts database

        try:
            palette.isVisible = True
        except:
            # If Fusion is unhappy about toggling visibility, just ignore it.
            pass

        # Also call this line in the 'ready' message of FRCHTMLHandler()
        if not palette_just_created:
            send_parts_to_palette(palette)

def run(context):
    global g_dbThread
    try:

        if not _ensure_file_paths_exist():
            raise Exception("Database directory creation failed.") 

        cmd_id = 'FRC_InsertCOTS'
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if not cmd_def:
            cmd_def = ui.commandDefinitions.addButtonDefinition(
                cmd_id,
                'FRC COTS Library',
                'Open the FRC COTS library palette to insert components',
                ICON_FOLDER
            )

        # Handle the startupCompleted event.
        onStartupCompleted = MyStartupCompletedHandler()
        app.startupCompleted.add(onStartupCompleted)
        handlers.append(onStartupCompleted)

        global customEvent
        customEvent = app.registerCustomEvent(database_thread.myCustomEvent)
        onThreadEvent = DatabaseThreadEventHandler()
        customEvent.add(onThreadEvent)
        handlers.append(onThreadEvent)

        on_created = ShowPaletteCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        handlers.append(on_created)

        # Put the button on the Insert panel in the Design workspace
        solid_ws = ui.workspaces.itemById('FusionSolidEnvironment')
        panels = solid_ws.toolbarPanels
        insert_panel = panels.itemById('InsertPanel')
        if insert_panel:
            control = insert_panel.controls.itemById(cmd_id)
            if not control:
                control = insert_panel.controls.addCommand(cmd_def, '')

        # Load favorites 
        load_favorites()

        # Check if startup is already complete.  This is True when
        # the add-in is run manually from the add-ins table.
        if app.isStartupComplete:
            # Manully call the startup handler to start the database thread.
            onStartupCompleted.notify('')

    except:
        ui.messageBox('Add-in run failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    global g_dbThread

    try:
        cmd_id = 'FRC_InsertCOTS'

        # Stop the database thread
        if g_dbThread:
            g_dbThread.stop()
            g_dbThread.join()

        _delete_all_icons()

        # Remove the toolbar button
        solid_ws = ui.workspaces.itemById('FusionSolidEnvironment')
        panels = solid_ws.toolbarPanels
        insert_panel = panels.itemById('InsertPanel')
        if insert_panel:
            control = insert_panel.controls.itemById(cmd_id)
            if control:
                control.deleteMe()

        # Remove the command definition
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if cmd_def:
            cmd_def.deleteMe()

        # Remove the HTML palette if it exists
        global g_palette
        if g_palette:
            g_palette.deleteMe()
            g_palette = None
        else:
            pal = ui.palettes.itemById('FRC_COTS_Palette')
            if pal:
                pal.deleteMe()

    except:
        ui.messageBox('Add-in stop failed:\n{}'.format(traceback.format_exc())) 