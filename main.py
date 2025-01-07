# main.py

import sys
import subprocess
import os
import configparser
import requests
import csv
import pandas as pd
import toml
import vdf
import glob
import time

from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from steam_web_api import Steam

def get_home_directory():
    
    """Gets the current user's home directory.

    This function tries several methods to determine the home directory,
    providing robust cross-platform support (though primarily aimed at Linux).

    Returns:
        str: The path to the user's home directory, or None if it cannot be determined.
    """
    # 1. Using os.path.expanduser("~") - Most common and generally reliable
    home_dir = os.path.expanduser("~")
    if home_dir != "~":  # Check if it actually expanded
        return home_dir

    # 2. Using the HOME environment variable (Less reliable on some systems)
    home_dir = os.environ.get("HOME")
    if home_dir:
        return home_dir

    # 3. Using pwd module (More robust, but requires import)
    try:
        import pwd
        home_dir = pwd.getpwuid(os.getuid()).pw_dir
        return home_dir
    except ImportError:
        pass  # pwd module not available (rare on Linux)
    except KeyError:
        pass # user not found

    # 4. Using os.path.expandvars("$HOME")
    home_dir = os.path.expandvars("$HOME")
    if home_dir != "$HOME":  # Check if it actually expanded
        return home_dir

    return None  # If all methods fail, return None

def set_default_config():
    """Sets default configuration values in config.ini, only if the file doesn't exist.

    Args:
        home_dir: The user's home directory. Defaults to the result of get_home_directory()

    Returns:
        None
    """
    home_dir = get_home_directory()
    config_file_path = 'config.ini'

    if os.path.exists(config_file_path):
        print(f"Config file '{config_file_path}' already exists. Using configuration file.")
        return None  # Do not overwrite

    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case of keys

    config['Directories'] = {
        'scriptsDir': os.path.join(home_dir, 'Games', 'Launch Scripts'),
        'umuDir': os.path.join(home_dir, 'Games', 'umu'),
        'globalPrefixDir': 'default'
    }
    config['Behavior'] = {
        'preferTOML': 'false' 
    }
    config['Keys'] = {
        'steam-api': '0'
    }
    config['LastUpdated'] = {
        'umu-launcher': '0',
        'umu-database': '0'
    }


    try:
        with open(config_file_path, 'w') as configFile:
            config.write(configFile)
        print(f"Created default config file: {config_file_path}")
    except OSError as e:
        print(f"Error creating config file: {e}")
        return None

    return None

def update_dependencies():
    """Updates dependencies based on timestamps in config.ini."""
    
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read('config.ini')

    dependencies = {
        'umu-launcher': {
            'url': 'placeholder_launcher_url',
            'filename': 'umu_launcher.exe',
            'folder': config['Directories']['umuDir']
        },
        'umu-database': {
            'url': 'https://raw.githubusercontent.com/Open-Wine-Components/umu-database/refs/heads/main/umu-database.csv',
            'filename': 'umu-database.csv',
            'folder': ''
        }
    }

    today = datetime.date.today()

    for dep_name, dep_info in dependencies.items():
        last_updated_str = config['LastUpdated'].get(dep_name, '0')

        try:
            last_updated = datetime.datetime.strptime(last_updated_str, '%Y-%m-%d').date()
        except ValueError:
            last_updated = datetime.date(1970, 1, 1) #Set to an old date to force an update

        if last_updated < today:
            print(f"Updating {dep_name}...")
            if download_file(dep_info['url'], dep_info['filename'], dep_info['folder'], overwrite=True):
                config['LastUpdated'][dep_name] = today.strftime('%Y-%m-%d')
            else:
                print(f"Failed to update {dep_name}")

    try:
        with open(config_file_path, 'w') as configfile:
            config.write(configfile)
    except OSError as e:
        print(f"Error writing to config file: {e}")

def download_file(url, filename, folder_path=None, overwrite=False):
    """Downloads a file from a URL, optionally saving it to a specified folder.

    Args:
        url: The URL of the file to download.
        filename: The name to save the file as.
        folder_path: (Optional) The path to the folder where the file should be saved.
        overwrite: (Optional) If True, overwrite the file if it already exists. Defaults to False.

    Returns:
        True if the download was successful, False otherwise.
    """
    try:
        response = requests.get(url, allow_redirects=True, stream=True)
        response.raise_for_status()

        if response.status_code == 204:
            print(f"File not found at {url}")
            return False

        if folder_path:
            if not os.path.exists(folder_path):
                print(f"Error: Folder path '{folder_path}' does not exist.")
                return False
            if not os.path.isdir(folder_path):
                print(f"Error: '{folder_path}' is not a directory.")
                return False

            filepath = os.path.join(folder_path, filename)
        else:
            filepath = filename

        if os.path.exists(filepath) and not overwrite:
            print(f"File '{filepath}' already exists. Use overwrite=True to overwrite.")
            return False

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded file successfully to: {filepath}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Error downloading file: {e}")
        return False
    except OSError as e:
        print(f"Error saving file: {e}")
        return False

def search_umu_database(search_string):
    """
    Searches the CSV, downloading if not found.
    If no results found, searches Steam.
    """
    filename = "umu-database.csv"
    try:
        df = pd.read_csv(filename)
    except FileNotFoundError:
        print(f"File not found. Attempting download")
        if download_file("https://raw.githubusercontent.com/Open-Wine-Components/umu-database/refs/heads/main/umu-database.csv", "umu-database.csv"):
            try:
                df = pd.read_csv(filename)
            except pd.errors.ParserError:
                return f"Error: Could not parse {filename} after download."
        else:
            return f"Error: Failed to download {filename}."
    except pd.errors.ParserError:
        return f"Error: Could not parse {filename}."

    if not all(col in df.columns for col in ['TITLE', 'STORE', 'UMU_ID']):
        return "Error: The CSV must contain columns 'TITLE', 'STORE', and 'UMU_ID'."

    mask = df['TITLE'].str.contains(search_string, case=False, na=False)
    results = df.loc[mask, ['TITLE', 'STORE', 'UMU_ID']]
    return results

def search_steam(search_string):
    """
    Searches Steam and returns a Pandas DataFrame (empty if no results or error).
    """
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read('config.ini')

    try:
        api_key = config['Keys']['steam-api']
        steam = Steam(api_key)
    except KeyError:
        print("Error: 'steam-api' key not found in config.ini.")
        return pd.DataFrame()  # Return empty DataFrame on config error
    except Exception as e:
        print(f"Error initializing Steam API: {e}")
        return pd.DataFrame()  # Return empty DataFrame on Steam init error

    try:
        response = steam.apps.search_games(search_string)
        if response and response.get("apps"):
            apps = response.get("apps")
            if apps:
                steam_games_list = []
                for game in apps:
                    game_id = game.get('id')
                    if isinstance(game_id, list) and game_id:  # Check if it's a non-empty list
                        game_id = game_id[0]  # Extract the integer from the list
                    elif not isinstance(game_id, int):
                        print(f"Unexpected game ID format: {game_id}. Skipping game")
                        continue
                    steam_games_list.append({
                        "TITLE": game.get("name"),
                        "STORE": "Steam",
                        "UMU_ID": f"umu-{game_id}"
                    })
                return pd.DataFrame(steam_games_list)
        return pd.DataFrame()
    except Exception as e:
        print(f"Error: Failed to access Steam API: {e}")
        return pd.DataFrame()

def run_installer(main_window):
    """Runs the installer, prompting for a file and using either a custom prefix or the global prefix from config.ini."""

    selected_indexes = None
    model = None

    if main_window.umu_tree_view.selectionModel().hasSelection():
        selected_indexes = main_window.umu_tree_view.selectionModel().selectedIndexes()
        model = main_window.umu_tree_view.model()
    elif main_window.steam_tree_view.selectionModel().hasSelection():
        selected_indexes = main_window.steam_tree_view.selectionModel().selectedIndexes()
        model = main_window.steam_tree_view.model()

    if not selected_indexes or not model:
        reply = QMessageBox.question(main_window, "No Item Selected", "No game selected. Do you want to proceed with the installation anyway?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return False
        else:
            umu_id = None
            store_value = None
            print("No UMU ID selected, proceeding anyway")
    else:
        # Get the first selected index
        first_index = selected_indexes[0]
        # Get the row
        row = first_index.row()

        # Get the UMU ID (third column, index 2)
        umu_id_index = model.index(row, 2)
        umu_id = model.data(umu_id_index, Qt.ItemDataRole.DisplayRole)
        print(f"UMU ID selected: {umu_id}")

        # Get the Store Value (second column, index 1)
        store_value_index = model.index(row, 1)
        store_value = model.data(store_value_index, Qt.ItemDataRole.DisplayRole)
        print(f"Store Value selected: {store_value}")

    if main_window.use_custom_prefix_checkbox.isChecked():
        custom_prefix_dir = main_window.custom_prefix_input.text()

        if not custom_prefix_dir:
            QMessageBox.warning(main_window, "Missing Custom Prefix", "Please enter a custom prefix directory.")
            return False

        if not os.path.isdir(custom_prefix_dir):
            QMessageBox.warning(main_window, "Invalid Custom Prefix", "The specified custom prefix directory is invalid.")
            return False

    config_file_path = 'config.ini'
    if not os.path.exists(config_file_path):
        QMessageBox.warning(main_window, "Missing Config File", "The config file is missing. Please run the program at least once to generate it.")
        return False

    config = configparser.ConfigParser()
    config.read(config_file_path)

    if 'Directories' not in config or 'globalPrefixDir' not in config['Directories'] or 'umuDir' not in config['Directories']:
        QMessageBox.warning(main_window, "Missing Config Entry", "The config file is missing the required entries. Please check the config file.")
        return False

    global_prefix_dir = config['Directories']['globalPrefixDir']
    umu_binary_dir = config['Directories']['umuDir']

    if global_prefix_dir != 'default' and not os.path.isdir(global_prefix_dir):
        QMessageBox.warning(main_window, "Invalid Global Prefix", "The global prefix directory specified in config.ini is invalid.")
        return False

    if not os.path.exists(umu_binary_dir):
        try:
            os.makedirs(umu_binary_dir, exist_ok=True)  # Create the directory
            print(f"Created umu directory: {umu_binary_dir}")
            #add step here to download umu-run
        except OSError as e:
            QMessageBox.critical(main_window, "Error Creating Directory", f"Failed to create umu directory: {e}")
            return False

    # Prompt user for file selection
    file_path, _ = QFileDialog.getOpenFileName(main_window, "Select File to Install")
    if not file_path:
        QMessageBox.warning(main_window, "No File Selected", "No file selected. Installation cancelled.")
        return False

    # Construct the command
    umu_run_path = os.path.join(umu_binary_dir, "umu-run")

    my_env = os.environ.copy()  # Create a copy of the current environment

    if main_window.use_custom_prefix_checkbox.isChecked():
        my_env["WINEPREFIX"] = custom_prefix_dir
    elif global_prefix_dir != 'default':
        my_env["WINEPREFIX"] = global_prefix_dir

    if umu_id:
        my_env["GAMEID"] = umu_id
    else:
        my_env["GAMEID"] = '0'

    # Add STORE environment variable if checkbox is checked
    if main_window.pass_store_value_checkbox.isChecked() and store_value:
        my_env["STORE"] = store_value
        print(f"STORE environment variable set to: {store_value}")
    elif main_window.pass_store_value_checkbox.isChecked() and not store_value:
        QMessageBox.warning(main_window, "Missing Store Value", "Pass Store value to UMU is checked, but no store value is selected. Installation cancelled.")
        return False

    command = [umu_run_path, file_path] #Command is now just the executable and the file path
    command_string = " ".join(command)

    # Run the command
    try:
        print("Running command:", command)  # Print the command for debugging
        subprocess.run(command_string, check=True, env=my_env, shell=True)  # Pass the modified environment
        QMessageBox.information(main_window, "Installer", "Installation complete.")
    except subprocess.CalledProcessError as e:
        QMessageBox.critical(main_window, "Installation Error", f"Installation failed: {e}")
        print(f"Installation failed: {e}")
        return False
    except FileNotFoundError:
        QMessageBox.critical(main_window, "Installation Error", f"umu-run not found at: {umu_run_path}")
        print(f"umu-run not found at: {umu_run_path}")
        return False
    except OSError as e:
        QMessageBox.critical(main_window, "Installation Error", f"Installation failed: {e}")
        print(f"Installation failed: {e}")
        return False
    return True

def save_launch_script(main_window):
    """Saves the launch script based on the selected tree view."""

    selected_indexes = None
    model = None

    if main_window.umu_tree_view.selectionModel().hasSelection():
        selected_indexes = main_window.umu_tree_view.selectionModel().selectedIndexes()
        model = main_window.umu_tree_view.model()
    elif main_window.steam_tree_view.selectionModel().hasSelection():
        selected_indexes = main_window.steam_tree_view.selectionModel().selectedIndexes()
        model = main_window.steam_tree_view.model()

    if not selected_indexes or not model:
        print("No UMU ID selected")
        QMessageBox.warning(main_window, "No Game Selected", "Please search for and select a game.") #TODO: allow custom game entries
        return False  # Exit the function immediately
    else:
        # Get the first selected index
        first_index = selected_indexes[0]
        # Get the row
        row = first_index.row()

        # Get the UMU ID (third column, index 2)
        umu_id_index = model.index(row, 2)
        umu_id = model.data(umu_id_index, Qt.ItemDataRole.DisplayRole)
        print(f"UMU ID selected: {umu_id}")

        # Get the Store Value (second column, index 1)
        store_value_index = model.index(row, 1)
        store_value = model.data(store_value_index, Qt.ItemDataRole.DisplayRole)
        print(f"Store Value selected: {store_value}")

    # Get Prefix Directory (same as in run_installer)
    if main_window.use_custom_prefix_checkbox.isChecked():
        custom_prefix_dir = main_window.custom_prefix_input.text()

        if not custom_prefix_dir:
            QMessageBox.warning(main_window, "Missing Custom Prefix", "Please enter a custom prefix directory.")
            return False

        if not os.path.isdir(custom_prefix_dir):
            QMessageBox.warning(main_window, "Invalid Custom Prefix", "The specified custom prefix directory is invalid.")
            return False


    # Get Script Filename
    script_filename = main_window.launch_script_name_input.text()
    if not script_filename:
        QMessageBox.warning(main_window, "Missing Script Name", "Please enter a launch script name.")
        return False

    # Get Scripts Directory from config
    config_file_path = 'config.ini'
    if not os.path.exists(config_file_path):
        QMessageBox.warning(main_window, "Missing Config File", "The config file is missing. Please run the program at least once to generate it.")
        return False

    config = configparser.ConfigParser()
    config.read(config_file_path)

    scripts_dir = config['Directories']['scriptsDir']
    global_prefix_dir = config['Directories']['globalPrefixDir']
    umu_binary_dir = config['Directories']['umuDir']

    if not os.path.exists(umu_binary_dir):
        try:
            os.makedirs(umu_binary_dir, exist_ok=True)  # Create the directory
            print(f"Created umu directory: {umu_binary_dir}")
            #add step here to download umu-run
        except OSError as e:
            QMessageBox.critical(main_window, "Error Creating Directory", f"Failed to create umu directory: {e}")
            return False

    if 'Directories' not in config or 'scriptsDir' not in config['Directories']:
        QMessageBox.critical(main_window, "Config Error", "Missing 'ScriptsDir' in config file.")
        return False

    if global_prefix_dir != 'default' and not os.path.isdir(global_prefix_dir):
        QMessageBox.warning(main_window, "Invalid Global Prefix", "The global prefix directory specified in config.ini is invalid.")
        return False

    if not os.path.exists(scripts_dir):
        try:
            os.makedirs(scripts_dir, exist_ok=True)
            print(f"Created scripts directory: {scripts_dir}")
        except OSError as e:
            QMessageBox.critical(main_window, "Error Creating Directory", f"Failed to create scripts directory: {e}")
            return False

    script_path = os.path.join(scripts_dir, script_filename)

    # Prompt user for game executable selection
    game_executable_path, _ = QFileDialog.getOpenFileName(main_window, "Select Game Executable")
    if not game_executable_path:
        QMessageBox.warning(main_window, "No File Selected", "No file selected. File creation cancelled.")
        return False

    toml_enabled = config.has_section('Behavior') and config['Behavior'].getboolean('preferTOML', fallback=False)

    command = []
    toml_data = {}

    prefix_command = ""
    prefix_path = None
    if main_window.use_custom_prefix_checkbox.isChecked():
        prefix_path = main_window.custom_prefix_input.text()
        prefix_command = f"WINEPREFIX='{prefix_path}'"
    elif global_prefix_dir != 'default':
        prefix_path = global_prefix_dir
        prefix_command = f"WINEPREFIX='{prefix_path}'"

    umu_run_path = os.path.join(umu_binary_dir, "umu-run")
    
    if toml_enabled:
        toml_data['umu'] = {}
        if prefix_path:
            toml_data['umu']['prefix'] = prefix_path
        if umu_id:
            toml_data['umu']['game_id'] = umu_id
        if main_window.pass_store_value_checkbox.isChecked() and store_value:
            toml_data['umu']['store'] = store_value
        toml_data['umu']['exe'] = game_executable_path
        toml_data['umu']['proton'] = 'GE-Proton' #TODO add user custom proton version
        toml_file_name = main_window.launch_script_name_input.text() + ".toml"
        toml_file_path = os.path.join(scripts_dir, toml_file_name)
        try:
            with open(toml_file_path, 'w') as f:
                toml.dump(toml_data, f)
            command.append(f"'{umu_run_path}' --config '{toml_file_path}'")
        except OSError as e:
            QMessageBox.critical(main_window, "Error Saving TOML", f"Failed to save TOML file: {e}")
            return False
    else:
        command.append(f"GAMEID={umu_id}")
        if prefix_command:
            command.append(prefix_command)
        if main_window.pass_store_value_checkbox.isChecked() and store_value:
            command.append(f"STORE='{store_value}'")
        command.append(f"'{umu_run_path}'")
        command.append(f"'{game_executable_path}'")

    command_string = " ".join(command)

    try:
        with open(script_path, 'w') as script_file:
            script_file.write(f"#!/bin/bash\n{command_string}")
        os.chmod(script_path, 0o755)

        # Build message for the popup
        message = f"Launch script saved to: {script_path}\n\n"
        if umu_id:
            message += f"Game ID: {umu_id}\n"
        if store_value and main_window.pass_store_value_checkbox.isChecked():
            message += f"Store Value: {store_value}\n"
        message += f"Game Executable: {game_executable_path}\n"
        if prefix_path:
            message += f"Wine Prefix: {prefix_path}\n"
        if toml_enabled:
            message += f"TOML config saved to: {toml_file_path}\n"

        QMessageBox.information(main_window, "Script Saved", message)

    except OSError as e:
        QMessageBox.critical(main_window, "Error Saving Script", f"Failed to save script: {e}")
        return False

    return True

def add_game_to_steam(game_name, exe_path, start_dir="", icon_path=""):
    """Adds a non-Steam game shortcut to Steam's shortcuts.vdf file (Linux only)."""

    steam_path = get_steam_path()
    if not steam_path:
        print("Error: Could not find Steam installation.")
        return

    user_id = get_steam_user_id(steam_path)
    if not user_id:
        print("Error: Could not determine Steam user ID.")
        return
    
    shortcuts_path = os.path.join(steam_path, "userdata", user_id, "config", "shortcuts.vdf")

    try:
        with open(shortcuts_path, "rb") as f:
            try:
                shortcuts = vdf.binary_load(f)
            except vdf.VDFDecodeError as e:  # Catch VDF decoding errors
                print(f"Error decoding shortcuts.vdf: {e}")
                return  # Exit the function if decoding fails
    except FileNotFoundError:
        print(f"Warning: shortcuts.vdf not found. Creating a new one.")
        shortcuts = {"shortcuts": {}}  # It's okay to create a new one if it doesn't exist
    except OSError as e: # Catch other OS errors like permissions
        print(f"Error opening shortcuts.vdf: {e}")
        return

    highest_id = -1
    if shortcuts["shortcuts"]:  # Check if the shortcuts dictionary is not empty
        for shortcut_id_str in shortcuts["shortcuts"]:
            try:
                shortcut_id = int(shortcut_id_str)
                highest_id = max(highest_id, shortcut_id)
            except ValueError:
                pass

    new_shortcut_id = str(highest_id + 1)

    shortcuts["shortcuts"][new_shortcut_id] = {
        "appid": "1353230",
        "AppName": game_name,
        "Exe": "\"" + exe_path + "\"",
        "StartDir": start_dir,
        "icon": icon_path,
        "ShortcutPath": "",
        "LaunchOptions": "",
        "IsHidden": "0",
        "AllowDesktopConfig": "1",
        "AllowOverlay": "1",
        "InGame": "0",
        "LastPlayTime": "0",
        "FlatpakAppID": "",
    }

    try:
        with open(shortcuts_path, "wb") as f:
            vdf.binary_dump(shortcuts, f)  # Use binary_dump
        print(f"Successfully added '{game_name}' to Steam.")
    except Exception as e:
        print(f"Error writing to shortcuts.vdf: {e}")

def get_steam_path():
    """Attempts to find the Steam installation directory on Linux."""
    possible_paths = [
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.local/share/Steam"),
        "/usr/games/steam",
        "/usr/local/games/steam"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def get_steam_user_id(steam_path):
    """Finds the most recently active Steam user's ID."""
    userdata_path = os.path.join(steam_path, "userdata")
    if not os.path.exists(userdata_path):
        print("Error: userdata directory not found.")
        return None

    user_folders = glob.glob(os.path.join(userdata_path, "*"))
    if not user_folders:
        print("Error: No user data found.")
        return None

    most_recent_folder = None
    most_recent_time = 0

    for user_folder in user_folders:
        try:
            folder_mtime = os.path.getmtime(user_folder)
            if folder_mtime > most_recent_time:
                most_recent_time = folder_mtime
                most_recent_folder = user_folder
        except OSError:  # Handle potential errors accessing folder metadata
            continue

    if most_recent_folder:
        user_id = os.path.basename(most_recent_folder)
        if user_id.isdigit():
            return user_id
        else:
            print("Warning: Most recently modified folder name is not a valid user ID.")
            return None
    else:
        print("Warning: Could not determine most recently active user.")
        return None

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Linux Steam Shortcut Helper")

        main_layout = QVBoxLayout()

        # Search layout (for UMU) - MOVED TO TOP
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Game Name")
        self.search_bar.returnPressed.connect(self.perform_search)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.perform_search)
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)
        main_layout.addLayout(search_layout)

        # UMU Database Results section
        umu_title_label = QLabel("UMU Database Results")
        font = QFont("Arial", 12)
        font.setWeight(QFont.Weight.Bold) 
        umu_title_label.setFont(font)
        main_layout.addWidget(umu_title_label)

        self.umu_tree_view = QTreeView()
        self.umu_model = QStandardItemModel()
        self.umu_tree_view.setModel(self.umu_model)
        main_layout.addWidget(self.umu_tree_view)

        # Steam Search Results section
        steam_title_label = QLabel("Steam Search Results")
        font = QFont("Arial", 12)
        font.setWeight(QFont.Weight.Bold)
        steam_title_label.setFont(font)
        main_layout.addWidget(steam_title_label)

        self.steam_tree_view = QTreeView()
        self.steam_model = QStandardItemModel()
        self.steam_tree_view.setModel(self.steam_model)
        main_layout.addWidget(self.steam_tree_view)

        self.selection_clearing = False #Flag to prevent recursion

        # Connect selection changed signals with mutual exclusion
        self.umu_tree_view.selectionModel().selectionChanged.connect(
            lambda selected, deselected: self.on_tree_view_selection_changed(self.umu_tree_view, selected, deselected)
        )
        self.steam_tree_view.selectionModel().selectionChanged.connect(
            lambda selected, deselected: self.on_tree_view_selection_changed(self.steam_tree_view, selected, deselected)
        )

        # Pass Store Value Checkbox
        self.pass_store_value_checkbox = QCheckBox()
        self.pass_store_value_label = QLabel("Pass Store value to UMU")
        pass_store_layout = QHBoxLayout()
        pass_store_layout.addWidget(self.pass_store_value_checkbox)
        pass_store_layout.addWidget(self.pass_store_value_label)
        pass_store_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)) #Spacer added here
        main_layout.addLayout(pass_store_layout)

        # Custom Prefix Layout
        self.custom_prefix_layout = QHBoxLayout()
        self.use_custom_prefix_checkbox = QCheckBox()
        self.use_custom_prefix_label = QLabel("Use Custom Prefix Directory:")
        self.custom_prefix_input = QLineEdit()
        self.select_folder_button = QPushButton("Select Folder")

        self.custom_prefix_layout.addWidget(self.use_custom_prefix_checkbox)
        self.custom_prefix_layout.addWidget(self.use_custom_prefix_label)
        self.custom_prefix_layout.addWidget(self.custom_prefix_input)
        self.custom_prefix_layout.addWidget(self.select_folder_button)

        main_layout.addLayout(self.custom_prefix_layout)

        # Connect checkbox state change
        self.use_custom_prefix_checkbox.stateChanged.connect(self.toggle_custom_prefix_widgets)
        self.select_folder_button.clicked.connect(self.select_folder)

        # Initialize widget states based on checkbox
        self.toggle_custom_prefix_widgets(self.use_custom_prefix_checkbox.checkState())

        # Launch Script Name
        self.launch_script_name_label = QLabel("Launch Script Name:")
        self.launch_script_name_input = QLineEdit()
        self.launch_script_name_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)  # Label stays at minimum width
        self.launch_script_name_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed) # Input expands horizontally
        launch_script_layout = QHBoxLayout()
        launch_script_layout.addWidget(self.launch_script_name_label)
        launch_script_layout.addWidget(self.launch_script_name_input)

        main_layout.addLayout(launch_script_layout)

        self.umu_tree_view.selectionModel().selectionChanged.connect(lambda: self.update_launch_script_name("umu"))
        self.steam_tree_view.selectionModel().selectionChanged.connect(lambda: self.update_launch_script_name("steam"))

        # Bottom layout
        bottom_layout = QVBoxLayout() # Outer layout is now vertical
        button_row = QHBoxLayout() # Inner layout for the first two buttons
        self.run_installer_button = QPushButton("Run Installer")
        self.save_script_button = QPushButton("Save Launch Script")
        self.add_to_steam_button = QPushButton("Add Game Script to Steam")
        self.run_installer_button.clicked.connect(lambda: run_installer(self))
        self.save_script_button.clicked.connect(lambda: save_launch_script(self))
        self.add_to_steam_button.clicked.connect(lambda: add_game_to_steam("Test","/home/stefan/Games/Launch Scripts/umu-1353230.sh"))

        button_row.addWidget(self.run_installer_button) # Add to the row
        button_row.addWidget(self.save_script_button)   # Add to the row

        bottom_layout.addLayout(button_row)       # Add the row to the vertical layout
        bottom_layout.addWidget(self.add_to_steam_button) # Add the new button below

        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

    def update_launch_script_name(self, tree_view_type):
    # Get the selected tree view based on the argument
        if tree_view_type == "umu":
            tree_view = self.umu_tree_view
            model = self.umu_model
        else:
            tree_view = self.steam_tree_view
            model = self.steam_model  # Assuming you have a separate model for steam data

        selected_indexes = tree_view.selectionModel().selectedIndexes()
        if selected_indexes:
            first_index = selected_indexes[0]
            row = first_index.row()
            umu_id_index = model.index(row, 2)  # Assuming UMU/Steam ID is in the third column (index 2)
            umu_id = model.data(umu_id_index, Qt.ItemDataRole.DisplayRole)
            self.launch_script_name_input.setText(umu_id + ".sh")
        else:
            self.launch_script_name_input.clear()  # Clear the text box if nothing is selected


    def toggle_custom_prefix_widgets(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.custom_prefix_input.setEnabled(enabled)
        self.select_folder_button.setEnabled(enabled)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:  # Check if a folder was selected (user didn't cancel)
            self.custom_prefix_input.setText(folder_path)

    def closeEvent(self, event):
        event.accept()
        QApplication.instance().quit()

    def perform_search(self):
        search_term = self.search_bar.text()
        if not search_term:
            QMessageBox.warning(self, "Empty Search", "Please enter a search term.")
            return

        # Perform both searches
        umu_results = search_umu_database(search_term)
        steam_results = search_steam(search_term)

        # Update UMU Tree View
        self.update_tree_view(self.umu_tree_view, self.umu_model, umu_results)

        # Update Steam Tree View
        self.update_tree_view(self.steam_tree_view, self.steam_model, steam_results)


    def update_tree_view(self, tree_view, model, results):
        """Helper function to update a given tree view with search results."""
        model.clear()

        if isinstance(results, str):  # Error handling
            QMessageBox.critical(self, "Search Error", results)
            return

        if results.empty:
            root_node = model.invisibleRootItem()
            no_results_item = QStandardItem("No matches found.")
            no_results_item.setFlags(Qt.ItemFlag.NoItemFlags)
            root_node.appendRow(no_results_item)
            return

        model.setHorizontalHeaderLabels(results.columns.tolist())

        for _, row in results.iterrows():
            items = [QStandardItem(str(row[col])) for col in results.columns]
            for item in items:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            model.appendRow(items)

        tree_view.resizeColumnToContents(0)
        tree_view.resizeColumnToContents(1)

    def on_tree_view_selection_changed(self, source_tree_view, selected, deselected):
        if self.selection_clearing: #If we're already clearing, exit
            return

        try:
            self.selection_clearing = True #Set the flag
            if source_tree_view == self.umu_tree_view:
                other_tree_view = self.steam_tree_view
            else:
                other_tree_view = self.umu_tree_view

            other_tree_view.clearSelection() #Clear the selection of the other tree view
            self.update_launch_script_name("umu" if source_tree_view == self.umu_tree_view else "steam")
        finally:
            self.selection_clearing = False #Ensure flag is always reset
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    set_default_config()
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    sys.exit(exit_code)