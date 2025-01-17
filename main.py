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
import shutil
import time
import hashlib
import random
import struct
import re
import json
import datetime
import tarfile
import uuid

from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from steam_web_api import Steam
from steamgrid import *
from zipfile import ZipFile

SESSION_ID = None

def initialize_session():
    global SESSION_ID  # Important: Declare that you're modifying the global one
    SESSION_ID = str(uuid.uuid4())
    print("Session initialized:", SESSION_ID)

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
        'steam-api': '0',
        'steamgriddb': '0'
    }
    config['AutoUpdateURL'] = {
        'umu-launcher': 'https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest',
        'umu-database': 'https://raw.githubusercontent.com/Open-Wine-Components/umu-database/refs/heads/main/umu-database.csv',
    }
    config['AutoUpdateDate'] = {
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

    today = datetime.date.today()

    last_updated_str = config['AutoUpdateDate'].get('umu-database', '0')

    try:
        last_updated = datetime.datetime.strptime(last_updated_str, '%Y-%m-%d').date()
    except ValueError:
        last_updated = datetime.date(1970, 1, 1) #Set to an old date to force an update

    if last_updated < today:
        print(f"Updating umu-database...")
        url = config['AutoUpdateURL'].get('umu-database')
        if url: # Check if url exists
            if download_file(url, overwrite=True):
                config['AutoUpdateDate']['umu-database'] = today.strftime('%Y-%m-%d')
            else:
                print(f"Failed to download umu-database from {url}")
        else:
            print(f"No URL found for umu-database in AutoUpdateURL")

    else:
        print(f'umu-database up to date, last updated {config["AutoUpdateDate"]["umu-database"]}')

    launcher_update_date = update_umu_launcher(config)

    if launcher_update_date is None:
        print(f'umu-launcher up to date, last updated {config["AutoUpdateDate"]["umu-launcher"]}')
    else:
        config["AutoUpdateDate"]["umu-launcher"] = launcher_update_date
        
    try:
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
    except OSError as e:
        print(f"Error writing to config file: {e}")

def update_umu_launcher(config):

    url = "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if config['AutoUpdateDate'].get('umu-launcher') == data.get("published_at"):
            return None
        assets = data.get("assets")
        if not assets:
            raise Exception("No assets found in the release")

        for asset in assets:
            if asset["name"] == "Zipapp.zip":
                umu_run_url = asset["browser_download_url"]

    if not umu_run_url:
        raise Exception("No download URL found for Zipapp.zip")

    if download_file(umu_run_url, 'Zipapp.zip', config['Directories'].get('umuDir'), overwrite=True):
        try:
            unpack_umu_run(config['Directories'].get('umuDir'))
            print("umu-run executable successfully extracted!")
            return data.get("published_at")
        except OSError as e:
            print(f"Error unpacking umu-run: {e}")
    else:
        raise Exception("Failed to download umu-launcher/Zipapp.zip")

def unpack_umu_run(directory):
    """
    Unpacks the `umu-run` executable from Zipapp.zip and Zipapp.tar to the given directory.

    Args:
        directory: The directory path where the extracted executable should be saved.

    Raises:
        OSError: If any issue occurs during extraction.
    """
    # Check if directory exists
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Extract Zipapp.zip
    try:
        with ZipFile(os.path.join(directory, "Zipapp.zip"), 'r') as zip_ref:
            zip_ref.extractall(directory)
    except FileNotFoundError:
        raise OSError("Zipapp.zip not found")
    except Exception as e:
        raise OSError(f"Error extracting Zipapp.zip: {e}")

    # Extract umu-run from Zipapp.tar
    try:
        with tarfile.open(os.path.join(directory, "Zipapp.tar"), 'r') as tar_ref:
            for member in tar_ref.getmembers():
                if member.name == "umu-run":
                    tar_ref.extract(member, directory)
                    break
    except FileNotFoundError:
        raise OSError("Zipapp.tar not found")
    except Exception as e:
        raise OSError(f"Error extracting umu-run from Zipapp.tar: {e}")
    
def download_file(url, filename=None, folder_path=None, overwrite=False):
    """Downloads a file from a URL, optionally saving it to a specified folder.

    Args:
        url: The URL of the file to download.
        filename: (Optional) The name to save the file as. If None, extracts it from the URL.
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

        if filename is None:
            # Extract filename from URL without urllib
            try:
                filename = url.split("/")[-1]
                if not filename: # handle cases where url ends with /
                    print(f"Could not determine filename from URL: {url}")
                    return False
                # Handle query parameters in the URL
                filename = filename.split("?")[0]
            except IndexError:
                print(f"Could not determine filename from URL: {url}")
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
    except Exception as e: # Catching a more general exception for unexpected errors during filename extraction
        print(f"An unexpected error occurred: {e}")
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

    if not all(col in df.columns for col in ['TITLE', 'STORE', 'CODENAME', 'UMU_ID']):
        return "Error: The CSV must contain columns 'TITLE', 'STORE', 'CODENAME', and 'UMU_ID'."

    mask = df['TITLE'].str.contains(search_string, case=False, na=False)
    results = df.loc[mask, ['TITLE', 'STORE', 'CODENAME', 'UMU_ID']]
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
                        "UMU_ID": f"umu-{game_id}",
                        "CODENAME": None
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

def add_game_to_steam(main_window, print_status):
    """Adds a non-Steam game shortcut to Steam's shortcuts.vdf file (Linux only)."""

    selected_indexes = None
    model = None
    codename = False

    if main_window.umu_tree_view.selectionModel().hasSelection():
        selected_indexes = main_window.umu_tree_view.selectionModel().selectedIndexes()
        model = main_window.umu_tree_view.model()
        codename = True
    elif main_window.steam_tree_view.selectionModel().hasSelection():
        selected_indexes = main_window.steam_tree_view.selectionModel().selectedIndexes()
        model = main_window.steam_tree_view.model()

    if not selected_indexes or not model:
        print("No UMU ID selected")
        QMessageBox.warning(main_window, "No Game Selected", "Please search for and select a game.") #TODO: allow custom game entries
        return False  # Exit the function immediately

    # Get the first selected index
    first_index = selected_indexes[0]

    #If UMU-ID selected, store the codename for comparison later
    if codename:
        selected_item = model().itemFromIndex(first_index)
        codename = selected_item.data(Qt.ItemDataRole.UserRole)
        print_status(f"Selected CODENAME: {codename}")

    # Get the row
    row = first_index.row()

    # Get the game Title (first column, index 0)
    game_title_index = model.index(row, 0)
    game_title = model.data(game_title_index, Qt.ItemDataRole.DisplayRole)
    print_status(f"Selected Title: {game_title}")

    # Get the Store Value (second column, index 1)
    store_value_index = model.index(row, 1)
    store_value = model.data(store_value_index, Qt.ItemDataRole.DisplayRole)
    print_status(f"Store Value selected: {store_value}") 

    # Get the UMU ID (third column, index 2)
    umu_id_index = model.index(row, 2)
    umu_id = model.data(umu_id_index, Qt.ItemDataRole.DisplayRole)
    print_status(f"UMU ID selected: {umu_id}")

    steam_path = get_steam_path()
    if not steam_path:
        print("Error: Could not find Steam installation.")
        QMessageBox.warning(main_window, "No Steam Installation Found", "Could not find Steam installation.")
        return

    user_id = get_steam_user_id(steam_path)
    if not user_id:
        print("Error: Could not determine Steam user ID.")
        QMessageBox.warning(main_window, "Unable to Identify Folder", "Could not determine Steam user ID.")
        return
    
    shortcuts_path = os.path.join(steam_path, "userdata", user_id, "config", "shortcuts.vdf")

    try:
        with open(shortcuts_path, "rb") as f:
            try:
                shortcuts = vdf.binary_load(f)
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                QMessageBox.warning(main_window, "Error Opening Shortcuts.vdf", "Could not open shortcuts.vdf.")
                return  # Exit the function if decoding fails
    except FileNotFoundError:
        print_status(f"Warning: shortcuts.vdf not found. Creating a new one.")
        shortcuts = {"shortcuts": {}}  # It's okay to create a new one if it doesn't exist
    except OSError as e: # Catch other OS errors like permissions
        print(f"Error opening shortcuts.vdf: {e}")
        QMessageBox.warning(main_window, "Error Opening Shortcuts.vdf", "Could not open shortcuts.vdf.")
        return

    highest_id = -1
    if shortcuts["shortcuts"]:  # Check if the shortcuts dictionary is not empty
        for shortcut_id_str in shortcuts["shortcuts"]:
            try:
                shortcut_id = int(shortcut_id_str)
                highest_id = max(highest_id, shortcut_id)
            except ValueError:
                pass

    config = configparser.ConfigParser()
    config.optionxform = str
    config.read('config.ini')
    scripts_dir = config['Directories']['scriptsDir']

    # Get Script Filename
    script_filename = main_window.launch_script_name_input.text()
    if not script_filename:
        QMessageBox.warning(main_window, "Missing Script Name", "Please enter a launch script name.")
        return False

    exe_path = os.path.join(scripts_dir, script_filename)

    if not os.path.exists(exe_path):
        QMessageBox.warning(main_window, "Missing Launch Script", "The launch script file is missing. Please make sure you use the Save Launch Script button first.")
        return False
    
    new_shortcut_id = str(highest_id + 1)
    exe_id = generate_exeid(exe_path)
    steam_file_id = signed_to_unsigned(exe_id)

    artwork_path = os.path.join(steam_path, "userdata", user_id, "config", "grid")
    is_int_appid, app_id = validate_umu_id(umu_id)

    icon_path = get_icon_from_steam(artwork_path, steam_file_id, app_id, print_status)
    
    if not icon_path:
        icon_path = "" #If no icon, use a null string to prevent errors saving VDF; it can't handle None types

    shortcuts["shortcuts"][new_shortcut_id] = {
        "appid": exe_id,
        "AppName": game_title,
        "Exe": "\"" + exe_path + "\"",
        "StartDir": scripts_dir,
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

    backup_and_save(shortcuts_path, shortcuts, game_title, main_window, icon_path, print_status)

    #Logic: Check store. If non-steam, check umu_id. If second portion is all numbers, check if number matches codename. If not, search steam store. If yes, it's a non-steam game (e.g. gog)

    if store_value == 'Steam' or (is_int_appid and app_id != codename):
        #fetch_artwork_sgdb(artwork_path, exe_id, app_id, store_value)
        get_artwork_from_steam(artwork_path, steam_file_id, app_id, print_status)

def backup_and_save(shortcuts_path, shortcuts, game_title, main_window, icon_path, print_status):
    """Backs up the shortcuts file and saves the new version."""

    backup_dir = "shortcuts_backups"
    max_backups = 5

    os.makedirs(backup_dir, exist_ok=True)

    backup_path = os.path.join(backup_dir, f"shortcuts_{SESSION_ID}.vdf")



    # Limit number of backups
    backup_files = sorted(glob.glob(os.path.join(backup_dir, "shortcuts_*.vdf")), key=os.path.getmtime, reverse=True)
    while len(backup_files) >= max_backups:
        os.remove(backup_files[-1])
        backup_files.pop()

    try:
        # Check if a backup with the current session ID already exists
        if os.path.exists(backup_path):
            print_status(f"Backup with session ID '{SESSION_ID}' already exists.")
        elif os.path.exists(shortcuts_path):
            shutil.copy2(shortcuts_path, backup_path)
            print_status(f"Created backup: {backup_path}")
        else:
            print_status("No existing shortcuts file found. Creating a new one.")

        with open(shortcuts_path, "wb") as f:
            vdf.binary_dump(shortcuts, f)
        print_status(f"Successfully added '{game_title}' to Steam.")
        return True

    except Exception as e:
        print(f"Error writing to shortcuts.vdf: {e}")
        QMessageBox.warning(main_window, "Error Opening Shortcuts.vdf", "Could not open shortcuts.vdf.")

        if icon_path:
            try:
                if os.path.exists(icon_path):
                    os.remove(icon_path)
                    print(f"Deleted icon: {icon_path}")
                else:
                    print(f"Icon not found: {icon_path}")
            except OSError as e:
                print(f"Error deleting icon {icon_path}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
        return False

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
    """Finds the most recently active Steam user's ID, excluding 'anonymous'."""
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
        user_id = os.path.basename(user_folder)
        if user_id == "anonymous":  # Skip the "anonymous" folder
            continue

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
        print("Warning: Could not determine most recently active user (excluding anonymous).") # Updated message
        return None

def generate_exeid(exe_path):
    
    try:
        with open(exe_path, "rb") as f:
            file_hash = hashlib.sha256()
            while chunk := f.read(8192):
                file_hash.update(chunk)
        file_digest = file_hash.digest()
    except FileNotFoundError:
        print(f"Error: File not found: {exe_path}")
        return None
    except OSError as e:
        print(f"Error reading file: {e}")
        return None

    hash_bytes = file_digest[:4]
    hash_int = int.from_bytes(hash_bytes, byteorder='little')

    # Correct way to create a negative number:
    negative_id = -(hash_int & 0x7FFFFFFF) - 1 #Masks the sign bit and then inverts the number

    if negative_id == 0:
      negative_id = (random.getrandbits(31) | (1<<31))

    packed_id = struct.pack("<i", negative_id)
    unpacked_id = struct.unpack("<i", packed_id)[0]

    print(f"Raw bytes: {packed_id.hex()}")
    print(f"Unpacked (signed): {unpacked_id}")
    print(f"Original Value (displayed by python): {negative_id}")
    print(f"Is negative: {negative_id < 0}") #This will now correctly show true

    return negative_id

def fetch_artwork_sgdb(artwork_path, exe_id, app_id, store):

    config = configparser.ConfigParser()
    config.optionxform = str
    config.read('config.ini')

    if config['Keys']['steamgriddb'] == 0:
        QMessageBox.warning(main_window, "No SGDB API Key Set", "Please obtain an API Key from SteamGridDB and save it in your config.ini file.")
        return False
    
    sgdb = SteamGridDB(config['Keys']['steamgriddb'])
    
    if store == 'Steam':
        grids = sgdb.get_grids_by_platform(game_ids=[app_id], platform=PlatformType.Steam)

    return True

def fetch_icon_sgdb(artwork_path, exe_id, app_id, store):
    #Icon has to be a separate function, because it's needed at VDF build time. If VDF build fails, the randomized non-steam exeid will change, and the stored file wouldn't be valid anymore.
    #It could possibly be mitigated by using steam's real appid instead, but not sure what chaos that could cause

    config = configparser.ConfigParser()
    config.optionxform = str
    config.read('config.ini')

    if config['Keys']['steamgriddb'] == 0:
        QMessageBox.warning(main_window, "No SGDB API Key Set", "Please obtain an API Key from SteamGridDB and save it in your config.ini file.")
        return False
    
    sgdb = SteamGridDB(config['Keys']['steamgriddb'])
    
    grids = sgdb.get_grids_by_platform(game_ids=[app_id], platform=PlatformType.Steam)

    print("t")

    return True

def validate_umu_id(umu_id):
    """
    Validates umu_id and returns (valid, x_part).
    Extracts x_part even if the format is invalid.
    """
    if not isinstance(umu_id, str):
        return False, None  # Or "" if you prefer an empty string

    match = re.match(r"^umu-(.+)$", umu_id) #Match anything after umu-

    if match:
        x_part = match.group(1)

        #Now we do the more specific validation on x_part
        if re.fullmatch(r"[1-9]\d*", x_part):
            return True, x_part # Valid format and x_part
        else:
            return False, x_part #Invalid format, but we still return x_part
    else:
        return False, None # No match at all

def get_artwork_from_steam(artwork_path, steam_file_id, app_id, print_status):
  """Downloads and saves 4 Steam artwork files.

  Args:
    artwork_path: The path to save the downloaded files.
    steam_file_id: The executable ID of the Steam game. Unsigned 32-bit int conversion of the stored, signed 32-bit int
    app_id: The Steam application ID.

  Raises:
    OSError: If an error occurs while creating the directory or saving a file.
  """

  # Create the artwork directory if it doesn't exist
  os.makedirs(artwork_path, exist_ok=True)

  base_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/"

  files = [
    ("header.jpg", f"{steam_file_id}.jpg"),
    ("library_600x900_2x.jpg", f"{steam_file_id}p.jpg"),
    ("logo_2x.png", f"{steam_file_id}_logo.png"),
    ("library_hero_2x.jpg", f"{steam_file_id}_hero.jpg")
  ]

  for filename, save_name in files:
    url = os.path.join(base_url, filename)
    full_path = os.path.join(artwork_path, save_name)

    # Download the file and handle errors
    try:
      with open(full_path, "wb") as f:
        # Use requests library for efficient downloading (install with "pip install requests")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        for chunk in response.iter_content(1024):
          f.write(chunk)

      print_status(f"Downloaded artwork: {save_name}")
    except (requests.exceptions.RequestException, OSError) as e:
      print_status(f"Error downloading {filename}: {e}")

def get_icon_from_steam(artwork_path, steam_file_id, app_id, print_status):
    """
    Retrieves the client icon from the Steam API and saves it to the specified path using requests.

    Args:
        artwork_path (str): Path to store the downloaded icon.
        steam_file_id: The executable ID of the Steam game. Unsigned 32-bit int conversion of the stored, signed 32-bit int
        app_id: The Steam application ID.

    Returns:
        str: Path to the saved icon file or None if not found or error occurred.
    """
    url = f"https://api.steamcmd.net/v1/info/{app_id}"

    try:
        response = requests.get(url)
        response.raise_for_status()

        data = json.loads(response.text)
        client_icon_hash = data.get("data", {}).get(app_id, {}).get("common", {}).get("clienticon")

        if client_icon_hash:
            icon_url = f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{app_id}/{client_icon_hash}.ico"
            filename = os.path.join(artwork_path, f"{steam_file_id}_icon.ico") # Use os.path.join for cross-platform compatibility

            try:
                icon_response = requests.get(icon_url, stream=True) # stream=True is important for large files
                icon_response.raise_for_status()

                with open(filename, 'wb') as f:
                    for chunk in icon_response.iter_content(chunk_size=8192): # Iterate over the response in chunks
                        f.write(chunk)

                print_status(f"Icon saved to: {filename}")
                return filename

            except requests.exceptions.RequestException as e:
                print_status(f"Error downloading icon: {e}")
                return None

        else:
            print_status(f"Client icon not found for app ID: {app_id}")
            return None

    except requests.exceptions.RequestException as e:
        print_status(f"Error retrieving information from SteamCMD API: {e}")
        return None

def signed_to_unsigned(signed_int):
    """Converts a signed 32-bit integer to its unsigned representation."""
    return signed_int & 0xFFFFFFFF

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
        self.add_to_steam_button.clicked.connect(self.show_modal_and_add_game) # Corrected connection

        button_row.addWidget(self.run_installer_button) # Add to the row
        button_row.addWidget(self.save_script_button)   # Add to the row

        bottom_layout.addLayout(button_row)       # Add the row to the vertical layout
        bottom_layout.addWidget(self.add_to_steam_button) # Add the new button below

        main_layout.addLayout(bottom_layout)

        self.status_modal = StatusModal(self)
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

        display_columns = ['TITLE', 'STORE', 'UMU_ID']

        model.setHorizontalHeaderLabels(display_columns)

        for _, row in results.iterrows():
            items = [QStandardItem(str(row[col])) for col in display_columns]

            # Store the CODENAME as data in the first item of the row (TITLE)
            items[0].setData(row['CODENAME'], Qt.ItemDataRole.UserRole)  # Store CODENAME

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

    def show_modal_and_add_game(self):
        self.status_modal.clear()
        self.status_modal.show()
        self.status_modal.raise_()
        self.status_modal.activateWindow()
        add_game_to_steam(self, self.status_modal.message_received.emit) # Corrected call

class StatusModal(QDialog):
    """Modal dialog for displaying status messages."""

    message_received = pyqtSignal(str)  # Signal for receiving messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Status")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint) # Remove ? button
        self.layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)  # Make it read-only
        self.layout.addWidget(self.text_edit)
        self.resize(400, 300) # set initial size
        self.message_received.connect(self.append_message)

    def append_message(self, message):
        """Appends a message to the text edit."""
        self.text_edit.append(message)
        self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum()) # Scrolls to bottom

    def clear(self):
        self.text_edit.clear()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    set_default_config()
    update_dependencies()
    initialize_session()
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    sys.exit(exit_code)