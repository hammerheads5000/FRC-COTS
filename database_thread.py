import adsk.core
import os
import threading
import time
import json
import re
from datetime import datetime, timedelta
from queue import Queue
from enum import Enum

from .lib import fusionAddInUtils as futil
from . import config

app = adsk.core.Application.get()
ui = app.userInterface

myCustomEvent = 'FRC_COTS_DatabaseThreadEvent'

# Global state
g_parts_db = None        # PartsDatabase object
g_parts_db_io = None     # PartsDatabaseFileIO object
g_update_queue = None    # Folder Update queue

def sanitize_part_name( part_name:str ):
    safeName = re.sub(r'\W+', '', part_name)
    return safeName

def flatten_path( path:str ):
    flat_path = path.replace( '\\', '_' )
    flat_path = flat_path.replace( '/', '_' )
    return flat_path

def get_icon_filename( path:str, basename:str ):
    """Path to the favorites JSON file next to this add-in."""
    safeName = sanitize_part_name( basename )
    flat_path = flatten_path(path)
    folder = config.PARTS_DB_PATH
    return os.path.join(folder, 'icons', f'{flat_path}{safeName}.png')

def delete_all_icons():
    icon_path = os.path.join(config.PARTS_DB_PATH, 'icons')
    for f in os.listdir(icon_path):
        try:
            os.remove(os.path.join(icon_path,f))
        except:
            pass

def send_event_to_main_thread(action, data):
    # action is one of:
    #   'set_busy' -> set the palette busy state, data is e.g. {'isBusy': True, 'msg': 'Banner message'}
    #   'update' -> tell the palette to update, data is ''
    #   'status' -> set the status line, data is {'msg': 'Idle'}
    args = {'action': action, 'data': data}
    app.fireCustomEvent( myCustomEvent, json.dumps(args) )

class FolderRecord:
    def __init__(self, name, dfolder: adsk.core.DataFolder, parent: 'FolderRecord'):
        self._childFolders = {}  # [name] -> FolderRecord
        self.parentFolder = parent
        self._files = {}  # [id] -> FileRecord
        self.name = name
        if parent:
            self.path = parent.path + name + '/'
        else:
            self.path = '/'
        self.dataFolder = dfolder
        self.areChildrenUpdated = False
        self.areFilesUpdated = False

    def add_child(self, new_child: 'FolderRecord'):
        if new_child.name in self._childFolders:
            # This child is already added
            return
        
        self._childFolders[new_child.name] = new_child

    def get_child(self, name: str):
        if name in self._childFolders:
            return self._childFolders[name]
        
        return None
    
    def add_file(self, file: 'FileRecord'):
        if file.id in self._files:
            # This file record is already added
            return
        
        self._files[file.id] = file

    def get_file(self, id: str):
        if id in self._files:
            return self._files[id]
        
        return None

class FileRecord:
    def __init__(self, df: adsk.core.DataFile, parent: FolderRecord):
        self.parentFolder = parent
        self.id = df.id
        self.dataFile = df

class FolderJobPhase(Enum):
    PROCESS_FOLDERS = 1
    PROCESS_FILES = 2
    SYNC_WITH_DATABASE = 3
    DONE = 4

class FolderUpdateJob:
    def __init__(self, rec: FolderRecord):
        self.record = rec
        self.phase = FolderJobPhase.PROCESS_FOLDERS

    def run_step(self):
        # Returns True if there is more to be done.
        global g_parts_db
        global g_update_queue

        # futil.log(f'Running step {self.phase} on folder {self.record.path}')

        match self.phase:
            case FolderJobPhase.PROCESS_FOLDERS:
                g_parts_db.reload_record_subfolders(self.record)
                for fdr in self.record._childFolders:
                    g_update_queue.push(FolderUpdateJob(self.record.get_child(fdr)))
                self.phase = FolderJobPhase.PROCESS_FILES
            case FolderJobPhase.PROCESS_FILES:
                g_parts_db.update_record_parts(self.record)
                self.phase = FolderJobPhase.SYNC_WITH_DATABASE
            case FolderJobPhase.SYNC_WITH_DATABASE:
                g_parts_db.sync_record_with_database(self.record)
                self.phase = FolderJobPhase.DONE
            case FolderJobPhase.DONE:
                pass

    def done(self):
        return self.phase == FolderJobPhase.DONE

class FolderViewedJob(FolderUpdateJob):

    def run_step(self):
        # Returns True if there is more to be done.
        global g_parts_db

        # futil.log(f'Running step {self.phase} on folder {self.record.path}')

        match self.phase:
            case FolderJobPhase.PROCESS_FOLDERS:
                g_parts_db.update_record_subfolders(self.record)
                self.phase = FolderJobPhase.PROCESS_FILES
            case FolderJobPhase.PROCESS_FILES:
                g_parts_db.update_record_parts(self.record)
                self.phase = FolderJobPhase.SYNC_WITH_DATABASE
            case FolderJobPhase.SYNC_WITH_DATABASE:
                g_parts_db.sync_record_with_database(self.record)
                self.phase = FolderJobPhase.DONE
            case FolderJobPhase.DONE:
                pass

class FolderUpdateQueue:
    def __init__(self, job: FolderUpdateJob):
        self.queue = Queue()
        self.push(job)

    def empty(self) -> bool:
        return self.queue.empty()
    
    def push(self, job: FolderUpdateJob):
        self.queue.put(job)

    def pop(self) -> FolderUpdateJob:
        if self.queue.empty():
            return None
        job: FolderUpdateJob = self.queue.get()
        futil.log(f'Queue::pop(size={self.queue.qsize()}) -- Working on {job.record.path}')
        return job

class PartsDatabaseFileIO:
    def __init__(self, project: adsk.core.DataProject):
        self.project = project
        self.rootRec = FolderRecord( 'root', self.project.rootFolder, None )
        self.record_mutex = threading.Lock()
        self.thumbnail_jobs = Queue()
        self.priority_thumbnail_jobs = Queue()

    def get_data_file(self, path, id):
        futil.log( f'get_data_file() -- Getting data file at {path} with id={id}...')
        
        fRec = self.get_data_folder(path)
        if not fRec:
            futil.log_error( f'Cannot find dataFolder {path}.')
            return None
        
        fileRec = fRec.get_file(id)
        if fileRec:
            return fileRec
        
        self.load_folder_files(fRec, True)
        return fRec.get_file(id)

    def get_data_folder(self, path: str) -> FolderRecord:
        if path == '/':
            return self.rootRec

        if path[-1] == '/':
            path = path[0:-1]

        start_path = '/'
        path_parts = path.split('/')[1:]

        fRec = self.rootRec
        while len(path_parts) > 0:
            childRec = fRec.get_child(path_parts[0])
            if not childRec:
                return self.find_folder_with_path( start_path, fRec, path_parts )
            
            fRec = childRec
            start_path = start_path + path_parts[0] + '/'
            path_parts = path_parts[1:]
        
        return fRec
    
    def find_folder_with_path( self, start_path: str, startRec: FolderRecord, path_parts: str ):
        # Look for a folder that is a sub-folder of the startRec
        # path_parts is a List of folders that we are looking for
        # when that list has a length of 1 we have found the folder we
        # are looking for.
        dfolder = startRec.dataFolder.dataFolders.itemByName( path_parts[0] )
        if not dfolder:
            futil.log_error( f'find_folder_with_path() Error finding folder {start_path}{path_parts[0]}...')
            return None

        dfolder_path = start_path + dfolder.name + '/'
        fRec = FolderRecord( dfolder.name, dfolder, startRec )
        self.record_mutex.acquire()
        startRec.add_child(fRec)
        self.record_mutex.release()

        # We are done.  Return the folder
        if len(path_parts) == 1:
            return fRec
        
        # Look inside the new folder since length of path_parts is greater than 1
        return self.find_folder_with_path( dfolder_path, fRec, path_parts[1:] )

    def reload_folder_children(self, fRec: FolderRecord):
        fRec.areChildrenUpdated = True
        fRec._childFolders = {}
        for df in fRec.dataFolder.dataFolders:
            self.record_mutex.acquire()
            fRec.add_child(FolderRecord(df.name, df, fRec))
            self.record_mutex.release()

    def update_folder_children(self, fRec: FolderRecord):
        fRec.areChildrenUpdated = True
        for df in fRec.dataFolder.dataFolders:
            self.record_mutex.acquire()
            fRec.add_child(FolderRecord(df.name, df, fRec))
            self.record_mutex.release()

    def load_folder_files(self, fRec: FolderRecord, ui_priority: bool):
        fRec.areFilesUpdated = True
        fRec._files = {}
        for df in fRec.dataFolder.dataFiles:
            if df.fileExtension and df.fileExtension.lower() == 'f3d':
                self.record_mutex.acquire()
                fRec.add_file(FileRecord(df, fRec))
                self.record_mutex.release()
                self.add_thumbnail_job(fRec.path, df, ui_priority)

    def add_thumbnail_job(self, path, dataFile: adsk.core.DataFile, ui_priority: bool):
        icon_name = get_icon_filename(path, dataFile.name)
        if ui_priority:
            self.priority_thumbnail_jobs.put((icon_name, dataFile.thumbnail))
        else:
            self.thumbnail_jobs.put((icon_name, dataFile.thumbnail))

    def is_thumbnail_job_waiting(self):
        return not self.thumbnail_jobs.empty()

    def process_one_thumbnail_job(self, queue: Queue):
        # Process a single job from the queue and return
        # True if an icon file was saved.
        job = queue.get()
        icon_name = job[0]
        thumb_future: adsk.core.DataObjectFuture = job[1]
        # futil.log(f'Processing thumbnail {icon_name} ...')

        if thumb_future.state == adsk.core.FutureStates.FinishedFutureState:
            try:
                if thumb_future.dataObject != None:
                    # futil.log(f'Creating thumbnail for {icon_name}')
                    try:
                        os.remove( icon_name )
                    except:
                        pass
                    thumb_future.dataObject.saveToFile( icon_name )
                    return True
            except:
                futil.handle_error(f'   Error processing thumbnail {icon_name}...')
        elif thumb_future.state == adsk.core.FutureStates.ProcessingFutureState:
            # Not done.  Put it and the end of the line
            queue.put( job )
            time.sleep(0.05)
        else:
            futil.log(f'   Retrieving thumbnail for {icon_name} failed...')

        return False

    def process_thumbnail_jobs(self, maxNumber: int = -1):
        # Process at most maxNumber of thumbnail jobs
        # If maxNumber = -1 process all available jobs
        # Returns True if some thumbnails were saved
        if self.thumbnail_jobs.empty() and self.priority_thumbnail_jobs.empty():
            # No more jobs to process
            return False

        start_time = time.time()
        TIMEOUT = 2.0

        need_update = False
        # Process the priority thumbnails that were requested due to
        # the UI navigation
        while not self.priority_thumbnail_jobs.empty() and time.time() - start_time < TIMEOUT:
            if self.process_one_thumbnail_job(self.priority_thumbnail_jobs):
                # We processed a priority thumbnail and saved a file.
                # Need to update the palette
                need_update = True

        if maxNumber == -1:
            maxNumber = 200
        
        idx = 0
        # Only allow 2 seconds for processing
        while not self.thumbnail_jobs.empty() and idx < maxNumber and time.time() - start_time < TIMEOUT:
            idx = idx + 1
            self.process_one_thumbnail_job(self.thumbnail_jobs)

        if time.time() - start_time > TIMEOUT:
            futil.log(f'   Processing thumbnails TIMED OUT!! ..')

        return need_update


class PartsDatabase:
    DATE_FORMAT = r'%d/%m/%y %H:%M:%S.%f'
    EXPIRED_DATABASE = timedelta( 14 )  # Forteen days
    JSON_FILE = 'parts_db.json'

    def __init__(self, io: PartsDatabaseFileIO):
        self.io = io
        self.mutex = threading.Lock()
        self.database = {}

        if not self.load_json_file():
            self.blank_database()
            return
        
        # Make sure the main keys exist
        if not 'built' in self.database:
            self.blank_database()
            return
        
        if not 'project' in self.database:
            self.blank_database()
            return

        if not 'name' in self.database['project']:
            self.blank_database()
            return

        if not 'build_date' in self.database:
            self.database['build_date'] = datetime.strftime(datetime(1900, 1, 1), PartsDatabase.DATE_FORMAT)

        # Check if the database is too old.
        build_date = datetime.strptime(self.database['build_date'], PartsDatabase.DATE_FORMAT)
        if datetime.now() - build_date > PartsDatabase.EXPIRED_DATABASE:
            futil.log(f'Expired database..  Build date = {build_date}')
            delete_all_icons()
            self.blank_database()
            return

        if self.database['project']['name'] != self.io.project.name:
            # The parts db is for a different project!
            futil.log(f'JSON project and the settings project do not match!')
            futil.log(f'   Regenerating the JSON database...')
            self.blank_database()

    def blank_database(self):
        self.database = {}
        self.database['built'] = False
        self.database['build_date'] = datetime.strftime(datetime(1900, 1, 1), PartsDatabase.DATE_FORMAT)
        self.database['project'] = {'name': self.io.project.name, 'id': self.io.project.id }
        self.database['parts'] = {}
        self.database['paths'] = {}

    def is_built(self):
        return self.database['built']

    def build_complete(self):
        timestr = datetime.strftime(datetime.now(), PartsDatabase.DATE_FORMAT)
        self.database['build_date'] = timestr
        self.database['built'] = True

    def add_part(self, id, path, name, version):
        
        icon_name = get_icon_filename(path, name)
        if path[-1] != '/':
            path = path + '/'
        self.mutex.acquire()
        if not path in self.database['paths']:
            self.database['paths'][path] = []
        if not id in self.database['paths'][path]:
            self.database['paths'][path].append(id)
        self.database['parts'][id] = { "path": path,
                                       "name": name,
                                       "version": version, 
                                       "icon": icon_name }
        self.mutex.release()

    def remove_part(self, id):
        try:
            self.mutex.acquire()
            part = self.database['parts'][id]
            path = part['path']
            self.database['paths'][path].remove(id)
            if len(self.database['paths'][path]) == 0:
                del self.database['paths'][path]

            del self.database['parts'][id]

        except:
            futil.handle_error(f'remove_part() id = {id}')
        finally:
            self.mutex.release()

    def remove_part_at_path(self, id, path):
        # If a part gets moved from one folder to another
        # then the partID is still in the database but
        # the path should be different
        try:
            self.mutex.acquire()
            part = self.database['parts'][id]
            id_path = part['path']
            self.database['paths'][path].remove(id)
            if len(self.database['paths'][path]) == 0:
                del self.database['paths'][path]

            if id_path == path:
                del self.database['parts'][id]

        except:
            futil.handle_error(f'remove_part() id = {id}')
        finally:
            self.mutex.release()



    def add_folder_placeholder(self, path):
        id = path + '_placeholder_'
        self.add_part(id, path, '_placeholder_', '')

    def remove_folder_placeholder(self, path):        
        id = path + '_placeholder_'
        if not id in self.database['parts']:
            # This placeholder is not in the db
            return
        
        self.remove_part(id)

    def get_part(self, id):
        try:
            part = self.database['parts'][id]
            return part
        except:
            return None
        
    def get_sorted_list(self):
        self.mutex.acquire()
        sorted_list = [(data['path'], data['name'], id, data['icon']) for id, data in self.database['parts'].items()]
        self.mutex.release()

        sorted_list.sort()

        return sorted_list

    def update_folder(self, path):
        global g_update_queue

        dfRec = self.io.get_data_folder(path)
        if not dfRec:
            futil.log_error( f'update_folder() -- Error loading "{path}".')
            return False
        
        # if self.is_built() or (g_update_queue.empty() and dfRec.areChildrenUpdated and dfRec.areFilesUpdated):
        if self.is_built():
            # Both the files and the folder have been updated
            # so add this folder to the job queue to check for
            # any changes since running Fusion but turn recursion off
            g_update_queue.push(FolderViewedJob(dfRec))
            return
        
        # Only update if not already done
        if not dfRec.areChildrenUpdated:
            self.update_record_subfolders(dfRec)

        # Only update if not already done
        if not dfRec.areFilesUpdated:
            self.update_record_parts(dfRec, True)

        self.sync_record_with_database(dfRec)

    def reload_record_subfolders(self, rec: FolderRecord):
        self.io.reload_folder_children(rec)

    def update_record_subfolders(self, rec: FolderRecord):
        self.io.update_folder_children(rec)

    def update_record_parts(self, rec: FolderRecord, ui_priority: bool = False):
        # Load all of this folders data files
        self.io.load_folder_files(rec, ui_priority)

        # Add a placeholder entry for child folders if 
        # they do not have any files or child folders yet.
        # Otherwise they won't show up in the list in the palette.
        for fdr in rec._childFolders:
            child: FolderRecord = rec._childFolders[fdr]
            try:
                db_parts = self.database['paths'][child.path]
            except:
                db_parts = 0
            if len(child._files) == 0 and len(child._childFolders) == 0 and db_parts == 0:
                self.add_folder_placeholder(child.path)

        # Remove the placeholder entry for this folders if
        # we now have either child folders or files
        if (len(rec._files) > 0 or len(rec._childFolders)) > 0:
            self.remove_folder_placeholder(rec.path)

    def sync_record_with_database(self, rec: FolderRecord):
        # We need to add all the parts to the part database
        for id in rec._files:
            f: FileRecord = rec._files[id]
            self.add_part(id, rec.path, f.dataFile.name, f.dataFile.versionNumber)

        # Remove any child folders that have been deleted
        child_paths = []
        for fdr in rec._childFolders:
            child: FolderRecord = rec._childFolders[fdr]
            child_paths.append( child.path )

        delete_paths = []
        path_length = len(rec.path.split('/'))
        for path in self.database['paths']:
            if path.find(rec.path) == 0 and len(path.split('/')) == path_length + 1:
                if not path in child_paths:
                    delete_paths.append(path)

        # Remove the paths that are no longer there
        for path in delete_paths:
            # Remove all the parts.  remove_part() will delete the path
            # entry when there are no more parts
            for fid in self.database['paths'][path]:
                self.remove_part_at_path(fid, path)
                
        # Remove any parts that have been deleted from the project
        delete_ids = []
        try:
            self.mutex.acquire()
            for fid in self.database['parts']:
                part = self.database['parts'][fid]
                if part['name'] != '_placeholder_' and part['path'] == rec.path and not fid in rec._files:
                    delete_ids.append(fid)

        finally:
            self.mutex.release()

        for id in delete_ids:
            futil.log(f'   Removing database part id = {id}')
            del self.database['parts'][id]


    def load_json_file(self):
        db_filename = os.path.join(config.PARTS_DB_PATH, PartsDatabase.JSON_FILE)
        if os.path.exists(db_filename):
            try:
                with open(db_filename, 'r') as f:
                    try:
                        self.mutex.acquire()
                        self.database = json.load(f)
                    except:
                        futil.handle_error( f'Could not read parts db JSON file {db_filename}...')
                        return False
                    finally:
                        self.mutex.release()
                return True
            except:
                futil.handle_error( f'Could not open parts db JSON file {db_filename} for reading...')
        else:
            futil.log( f'Parts db JSON file {db_filename} does not exist...')
        return False

    def save_json_file(self):
        db_filename = os.path.join( config.PARTS_DB_PATH, PartsDatabase.JSON_FILE )
        try:
            with open(db_filename, 'w') as f:
                self.mutex.acquire()
                json.dump(self.database, f, indent=2)
        except Exception:
            futil.handle_error(f"Could not write parts database file '{db_filename}'.")
        finally:
            self.mutex.release()


def get_data_file( path, data_file_id ):
    global g_parts_db_io

    df_entry: FileRecord = g_parts_db_io.get_data_file( path, data_file_id )
    if not df_entry:
        return None
    
    return df_entry.dataFile

def load_folder( path ):
    global g_parts_db

    g_parts_db.update_folder( path )

def get_sorted_database_list():
    global g_parts_db

    if not g_parts_db:
        return {}
    
    return g_parts_db.get_sorted_list()

def find_project(name: str):
    try:
        data = app.data
        projects = data.dataProjects

        frc_project = None
        for proj in projects:
            if proj.name == name:
                frc_project = proj
                break

        if not frc_project:
            futil.log_error(f"Could not find project '{name}'.")
            return None
    except:
        futil.handle_error(f"Error loading project '{name}'.")

    return frc_project


class DatabaseThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stopped = threading.Event()

    def stop(self):
        self.stopped.set()

    def run(self):
        global g_parts_db
        global g_parts_db_io
        global g_update_queue

        try:
            futil.log(f'DatabaseThread::run()...')

            # Find the COTS database
            project = find_project(config.PARTS_DB_PROJECT)
            if not project:
                send_event_to_main_thread('set_busy', 
                    { 
                        'isBusy': True, 
                        'msg': f'Unable to Open project {config.PARTS_DB_PROJECT}!!'
                    }
                )
                return
            
            # Create the parts file IO database
            g_parts_db_io = PartsDatabaseFileIO(project)

            # Load the parts database
            g_parts_db = PartsDatabase(g_parts_db_io)

            if g_parts_db.is_built():
                # Just refresh the root folder
                job = FolderViewedJob(g_parts_db_io.rootRec)
            else:
                # Refresh the root folder and all subfolders
                job =  FolderUpdateJob(g_parts_db_io.rootRec)

            # Create the update queue and add the root folder job to it.
            g_update_queue = FolderUpdateQueue(job)

            send_event_to_main_thread('set_busy', 
                {
                    'isBusy': True,
                    'msg': f'LOADING DATABASE...'
                }
            )

            g_parts_db.save_json_file()

            busy_idx = 0
            busy_rounds = ['|', '/', '-', '\\']
            if g_parts_db.is_built():
                busy_text = 'Updating...'
            else:
                busy_text = 'Building index...'

            busy_update_time = time.time()
            msg = busy_text + busy_rounds[busy_idx % 4]
            send_event_to_main_thread('status', {'msg': msg})
            busy_idx += 1

            # Fire an event that tells the Palette to refresh.
            send_event_to_main_thread('update', '' )

            current_job = g_update_queue.pop()
            first_job = True

            # Start the main processing loop for the database thread...
            while not self.stopped.is_set():
                # Check if there are thumbnail images to process
                # Process them then 'update' the palette if priority
                # thumbnail files were created.
                need_update = g_parts_db_io.process_thumbnail_jobs()
                if need_update:
                    send_event_to_main_thread('update', '' )

                # Now process other folders that have not been refreshed
                if current_job and not current_job.done():
                    time.sleep(0.02)
                    # Update the busy text to spin around.
                    if time.time() - busy_update_time > 0.5:
                        msg = busy_text + busy_rounds[busy_idx % 4]
                        send_event_to_main_thread('status', {'msg': msg})
                        busy_idx += 1
                        busy_update_time = time.time()

                    current_job.run_step()
                    if current_job.done():
                        current_job = g_update_queue.pop()
                        if first_job:
                            # Remove the busy overlay and update the parts
                            send_event_to_main_thread('set_busy', {'isBusy': False})
                            send_event_to_main_thread('update', '' )
                            first_job = False


                        if not current_job:
                            # We just finished the last job in the queue
                            # Save the JSON file to disk
                            g_parts_db.build_complete()
                            g_parts_db.save_json_file()
                            send_event_to_main_thread('status', {'msg': 'Idle.'} )
                            send_event_to_main_thread('update', '' )

                if not current_job:
                    if g_update_queue.empty():                        
                        # Nothing to do just sleep for a bit
                        busy_text = 'Updating...'
                        time.sleep( 0.1 )
                    else:
                        # Grab a new job
                        current_job = g_update_queue.pop()
                        if current_job:
                            msg = busy_text + busy_rounds[busy_idx % 4]
                            send_event_to_main_thread('status', {'msg': msg})
                            busy_idx += 1
                            busy_update_time = time.time()

            g_parts_db.save_json_file()
            futil.log(f'DatabaseThread() -- Finishing normally...')

        except:
            futil.handle_error( "----  DatabaseThread ERROR  ----" )