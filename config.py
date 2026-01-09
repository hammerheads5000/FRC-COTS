import os

# FRC_COTS Add-In Global Variables
# This module serves as a way to share variables across different
# modules (global variables).

# Parts Database Project
PARTS_DB_PROJECT = 'FRC_COTS'

# The path to store the database folder and the thumbnails (this needs to exist)
# PARTS_DB_FOLDER = os.path.dirname(__file__)   # Use the folder this file is in
PARTS_DB_FOLDER = os.path.expanduser('~')       # Use the users home folder (e.g. 'C:\Users\frc_user\')

# The subfolder to put all the data in (will be created)
PARTS_DB_PATH = os.path.join(PARTS_DB_FOLDER, 'FRC-COTS_db')

# Do we default to linking inserted parts?
DEFAULT_TO_LINKED_PARTS = False


# # Gets the name of the add-in from the name of the folder the py file is in.
# # This is used when defining unique internal names for various UI elements 
# # that need a unique name. It's also recommended to use a company name as 
# # part of the ID to better ensure the ID is unique.
ADDIN_NAME = 'FRC_COTS'
COMPANY_NAME = 'TEAM_5000'

# Command IDS
INSERT_PART_CMD_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_insertPart'
INSERT_SPACER_CMD_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_insertSpacer'

# # Palettes
palette_id = f'{COMPANY_NAME}_{ADDIN_NAME}_palette_id'

# Flag that indicates to run in Debug mode or not. When running in Debug mode
# more information is written to the Text Command window. Generally, it's useful
# to set this to True while developing an add-in and set it to False when you
# are ready to distribute it.
DEBUG = False
