import adsk.core
import adsk.fusion
import traceback
import json
import os
from . import commands
from . import config
from . import database_thread

from .commands.insertPart import entry as insertPart
from .commands.insertSpacer import entry as insertSpacer
from .commands.makeSpacer import entry as setJoint

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

        # Load favorites 
        load_favorites()

        # Create the palette
        create_palette()

        futil.log('MyStartupCompletedHandler::notify() -- Starting the DB thread...')
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
        data = json.dumps(eventArgs['data'])
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

                path, label, data_file_id, icon_name = cots_files[idx]

                dataFile = database_thread.get_data_file( path, data_file_id )
                isSpacer = setJoint.is_dataFile_spacer(dataFile)

                if isSpacer:
                    # This is a spacer
                    insertCmd = ui.commandDefinitions.itemById(config.INSERT_SPACER_CMD_ID)
                    insertSpacer.g_dataFile = dataFile
                    insertSpacer.g_iconName = icon_name
                else:
                    insertCmd = ui.commandDefinitions.itemById(config.INSERT_PART_CMD_ID)
                    insertPart.g_dataFile = dataFile
                    insertPart.g_iconName = icon_name

                if insertCmd:
                    insertCmd.execute()


                # insert_part_at_targets(design, path, label, data_file_id, targets, ui)
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

        if not g_dbThread or not g_dbThread.is_alive():
            futil.log('        ------- Restarting the DB thread...')
            g_dbThread = database_thread.DatabaseThread()
            g_dbThread.start()
        # else:
        #     if not g_dbThread.is_alive():
        #         futil.log('ShowPaletteCreatedHandler::notify() -- Restarting the DB thread...')
        #         g_dbThread.start()


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

        # Check if startup is already complete.  This is True when
        # the add-in is run manually from the add-ins table.
        if app.isStartupComplete:
            # Manully call the startup handler to start the database thread.
            onStartupCompleted.notify('')

        commands.start()

    except:
        ui.messageBox('Add-in run failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    global g_dbThread
    global handlers

    # Release event handlers
    handlers = []

    commands.stop()

    try:
        cmd_id = 'FRC_InsertCOTS'

        # Stop the database thread
        if g_dbThread:
            g_dbThread.stop()
            g_dbThread.join()

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