import adsk.core
import adsk.fusion
import traceback
import json
import os
import threading

from .lib import fusionAddInUtils as futil


# Keep a global reference to event handlers so they are not garbage collected.
handlers = []

# Global state
g_cots_files = []      # list of (path, partname, DataFile, thumbidx)
g_favorites = {}       # dataFile.id -> bool
g_palette = None       # HTML palette reference
g_thumbnails = []
app = adsk.core.Application.get()
ui = app.userInterface


def get_app_ui():
    app = adsk.core.Application.get()
    ui = app.userInterface if app else None
    return app, ui


def _favorites_path():
    """Path to the favorites JSON file next to this add-in."""
    folder = os.path.dirname(__file__)
    return os.path.join(folder, 'FRC_COTS_favorites.json')

def get_icon_filename( thumbidx: int ):
    """Path to the favorites JSON file next to this add-in."""
    folder = os.path.dirname(__file__)
    return os.path.join(folder, 'icons', f'icon_{thumbidx}.png')

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

def _walk_folder(progress: adsk.core.ProgressDialog, folder, prefix, out_list):
    """Recursively walk a DataFolder and append (label, DataFile) for .f3d files."""
    # Files
    progress.message = f'Loading folder {prefix}, file %v ...'
    idx = 0
    for df in folder.dataFiles:
        if progress.wasCancelled:
            return
        
        try:
            adsk.doEvents()
            if df.fileExtension and df.fileExtension.lower() == 'f3d':
                label = df.name
                out_list.append((prefix, label, df, len(out_list)+1))
                futil.log(f'Loading file {label} at idx {len(out_list)}...')
                idx = idx + 1
                progress.progressValue = idx
        except:
            futil.log(f'Failed to load file {df.name}.')
            continue
    
    futil.log( f'Folder {folder.name}, loaded {idx} files...')

    # Subfolders
    for sub in folder.dataFolders:
        new_prefix = prefix + sub.name + '/'
        _walk_folder(progress, sub, new_prefix, out_list)


def load_cots_files(app):
    """Populate g_cots_files with all .f3d files under the FRC_COTS project."""
    global g_cots_files
    global g_thumbnails

    g_cots_files = []

    futil.log(f'Loading COTS files....')

    progress = ui.createProgressDialog()
    try:
        data = app.data
        projects = data.dataProjects

        frc_project = None
        for proj in projects:
            if proj.name == 'FRC_COTS':
                frc_project = proj
                break

        if not frc_project:
            futil.popup_error( "Could not find project FRC_COTS.")
            return

        root = frc_project.rootFolder

        progress.show( "Loading COTS files from FRC_COTS Project...", "", 0, 20 )
        _walk_folder(progress, root, '', g_cots_files)
        futil.log( f'Loaded {len(g_cots_files)} COTS files...')

        # Sort nicely by label
        g_cots_files.sort(key=lambda t: (t[0] + t[1]).lower())
    except:
        futil.handle_error( "Load COTS files" )
        g_cots_files = []
    progress.hide()

    futil.log( "   Requesting thumbnails...")
    for (_, _, df, idx) in g_cots_files:
        g_thumbnails.append( (idx, df.thumbnail) )


def insert_part_at_targets(design, label, data_file, targets, ui):
    """
    Insert the given DataFile into the root component and create joints
    from its origin to each of the target entities.
    """
    root_comp = design.rootComponent
    occs = root_comp.occurrences
    joints = root_comp.joints

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
            new_occ.isGrounded = False
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

def load_palette(ui):
    """Load the HTML palette used to browse COTS parts."""
    global g_cots_files

    futil.log(f'load_palette()....')

    try:
        # Refresh COTS list in case the project changed
        # load_cots_files(app)
        palette = get_or_create_palette(ui)
        if palette:
            try:
                palette.isVisible = True
            except:
                # If Fusion is unhappy about toggling visibility, just ignore it.
                pass

            parts = []
            for idx, (path, label, df, thumbidx) in enumerate(g_cots_files):
                parts.append({
                    'index': idx,
                    'path': path,
                    'label': label,
                    'favorite': g_favorites.get(df.id, False),
                    'thumb': get_icon_filename(thumbidx)
                })
            palette.sendInfoToHTML('partsList', json.dumps(parts))
    except:
        futil.handle_error('load_palette failed:')


def get_or_create_palette(ui):
    """Create or return the HTML palette used to browse COTS parts."""
    global g_palette

    futil.log(f'get_or_create_palette()....')

    pal_id = 'FRC_COTS_Palette'
    # If we already have a valid reference, reuse it
    if g_palette and g_palette.isValid:
        return g_palette

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

    g_palette = pal
    return pal

class ThumbnailThread(threading.Thread):
    def __init__(self, event):
        threading.Thread.__init__(self)
        self.stopped = event

    def run(self):
        global g_thumbnails

        futil.log(f'ThumbnailThread::run()...')

        # Process all the thumbnail images....
        doneLoading = False

        while not doneLoading:
            doneLoading = True
            idx = 0
            while idx < len(g_thumbnails):
                # futil.log(f'Processing thumbnail {idx}...')
                (index, future) = g_thumbnails[idx]
                future : adsk.core.DataObjectFuture = future
                if future.state == adsk.core.FutureStates.ProcessingFutureState:
                    doneLoading = False
                try:
                    if future.dataObject != None:
                        filename = get_icon_filename(index)
                        # futil.log(f'Creating thumbnail for {filename}')
                        try:
                            os.remove( filename )
                        except:
                            pass
                        future.dataObject.saveToFile( filename )
                except:
                    futil.handle_error(f'   Error processing thumbnail {index}...')

                idx = idx + 1

        futil.log(f'ThumbnailThread finished...')



class FRCHTMLHandler(adsk.core.HTMLEventHandler):
    """Handles messages coming from the HTML palette."""

    def notify(self, args):
        global g_cots_files

        futil.log(f'FRCHTMLHandler::notify()...')

        app, ui = get_app_ui()
        try:
            action = args.action
            data = args.data or ''

            # HTML asks for the list of parts
            if action == 'requestParts':
                # parts = []
                # for idx, (label, df, thumbidx) in enumerate(g_cots_files):
                #     parts.append({
                #         'index': idx,
                #         'label': label,
                #         'favorite': g_favorites.get(df.id, False),
                #         'thumb': get_icon_filename(thumbidx)
                #     })
                # args.palette.sendInfoToHTML('partsList', json.dumps(parts))
                load_palette(ui)
                return

            # HTML tells us to insert the selected part at current canvas selection
            if action == 'insertPart':
                try:
                    payload = json.loads(data) if data else {}
                    idx = int(payload.get('index', -1))
                except Exception:
                    idx = -1

                if idx < 0 or idx >= len(g_cots_files):
                    ui.messageBox('Invalid part index from HTML.')
                    return

                path, label, data_file, _ = g_cots_files[idx]

                project = os.path.join( path, label )

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

                insert_part_at_targets(design, project, data_file, targets, ui)
                return

            # HTML toggles favorite state for a part
            if action == 'toggleFavorite':
                try:
                    payload = json.loads(data) if data else {}
                    idx = int(payload.get('index', -1))
                    fav = bool(payload.get('favorite', False))
                except Exception:
                    idx = -1
                    fav = False

                if 0 <= idx < len(g_cots_files):
                    _, _label, df, _thumbidx = g_cots_files[idx]
                    g_favorites[df.id] = fav
                    save_favorites()
                return

        except:
            ui.messageBox('HTML palette error:\n{}'.format(traceback.format_exc()))


def run(context):
    app, ui = get_app_ui()
    try:

        cmd_id = 'FRC_InsertCOTS'
        cmd_def = ui.commandDefinitions.itemById(cmd_id)
        if not cmd_def:
            cmd_def = ui.commandDefinitions.addButtonDefinition(
                cmd_id,
                'FRC COTS Library',
                'Open the FRC COTS library palette to insert components'
            )

        class ShowPaletteCreatedHandler(adsk.core.CommandCreatedEventHandler):
            def __init__(self):
                super().__init__()

            def notify(self, args):

                futil.log(f'ShowPaletteCreatedHandler::notify()...')

                load_palette(ui)

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
                insert_panel.controls.addCommand(cmd_def, '')

        # Load favorites and COTS list once when the add-in starts
        load_favorites()
        load_cots_files(app)

        stopFlag = threading.Event()
        thumbThread = ThumbnailThread(stopFlag)
        thumbThread.start()

        # Pre-create the HTML palette so it is ready when the button is pressed
        load_palette(ui)
        # palette.isVisible = False

    except:
        ui.messageBox('Add-in run failed:\n{}'.format(traceback.format_exc()))


def stop(context):
    app, ui = get_app_ui()
    try:
        cmd_id = 'FRC_InsertCOTS'

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