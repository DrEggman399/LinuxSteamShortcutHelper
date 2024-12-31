# main.py

import sys
import subprocess
import os
import configparser
import requests
import csv
import pandas as pd
import toml

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QTreeView, QMessageBox,
                             QCheckBox, QLabel, QFileDialog, QSpacerItem, QSizePolicy)
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtCore import Qt
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

    if results.empty:
        print(f"No results found in UMU database. Searching Steam...")
        steam_results = search_steam(search_string)
        if not steam_results.empty:  # Correct check: check if DataFrame is NOT empty
            return steam_results
        else:
            return f"No results found in UMU database or Steam for: {search_string}"
    else:
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

    # Check if an item is selected in the tree view
    selected_indexes = main_window.tree_view.selectionModel().selectedIndexes()
    if not selected_indexes:
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
        # Get the model
        model = main_window.tree_view.model()

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
        my_env["GAMEID"] = 0

    # Add STORE environment variable if checkbox is checked
    if main_window.pass_store_value_checkbox.isChecked() and store_value:
        my_env["STORE"] = store_value
        print(f"STORE environment variable set to: {store_value}")
    elif main_window.pass_store_value_checkbox.isChecked() and not store_value:
        QMessageBox.warning(main_window, "Missing Store Value", "Pass Store value to UMU is checked, but no store value is selected. Installation cancelled.")
        return False

    command = [umu_run_path, file_path] #Command is now just the executable and the file path

    # Run the command
    try:
        print("Running command:", command)  # Print the command for debugging
        subprocess.run(command, check=True, env=my_env)  # Pass the modified environment
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
    """Saves the launch script to the scripts directory."""

    # Get UMU ID (same as in run_installer)
    selected_indexes = main_window.tree_view.selectionModel().selectedIndexes()
    if not selected_indexes:
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
        # Get the model
        model = main_window.tree_view.model()

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

    prefix_command = ""
    prefix_path = None
    if main_window.use_custom_prefix_checkbox.isChecked():
        prefix_path = main_window.custom_prefix_input.text()
        prefix_command = f"WINEPREFIX='{prefix_path}'"
    elif global_prefix_dir != 'default':
        prefix_path = global_prefix_dir
        prefix_command = f"WINEPREFIX='{prefix_path}'"

    toml_data = {}

    if toml_enabled:
        toml_data['umu'] = {}
        if prefix_path:
            toml_data['umu']['prefix'] = prefix_path
        if umu_id:
            toml_data['umu']['game_id'] = umu_id
        if main_window.pass_store_value_checkbox.isChecked() and store_value:
            toml_data['umu']['STORE'] = store_value
        toml_data['umu']['exe'] = game_executable_path

    command = []

    if prefix_command:
        command.append(prefix_command)

    umu_run_path = os.path.join(umu_binary_dir, "umu-run")
    toml_file_name = main_window.launch_script_name_input.text() + ".toml"
    toml_file_path = os.path.join(scripts_dir, toml_file_name)

    if toml_enabled:
        try:
            with open(toml_file_path, 'w') as f:
                toml.dump(toml_data, f)
            command.append(f"'{umu_run_path}' --config '{toml_file_path}'")
        except OSError as e:
            QMessageBox.critical(main_window, "Error Saving TOML", f"Failed to save TOML file: {e}")
            return False
    else:
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
    
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Linux Steam Shortcut Helper")

        main_layout = QVBoxLayout()

        # Search layout
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Game Name")
        self.search_bar.returnPressed.connect(self.perform_search) # Connect Enter key
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.perform_search)
        search_layout.addWidget(self.search_bar)
        search_layout.addWidget(self.search_button)
        main_layout.addLayout(search_layout)

        self.tree_view = QTreeView()
        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)
        main_layout.addWidget(self.tree_view)

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
        # Connect tree view selection changed signal
        self.tree_view.selectionModel().selectionChanged.connect(self.update_launch_script_name)

        # Bottom layout
        bottom_layout = QHBoxLayout()
        self.run_installer_button = QPushButton("Run Installer")
        self.save_script_button = QPushButton("Save Launch Script")
        self.run_installer_button.clicked.connect(lambda: run_installer(self))
        self.save_script_button.clicked.connect(lambda: save_launch_script(self))
        bottom_layout.addWidget(self.run_installer_button)
        bottom_layout.addWidget(self.save_script_button)
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

    def update_launch_script_name(self):
        selected_indexes = self.tree_view.selectionModel().selectedIndexes()
        if selected_indexes:
            first_index = selected_indexes[0]
            row = first_index.row()
            model = self.tree_view.model()
            umu_id_index = model.index(row, 2)  # Assuming UMU ID is in the third column (index 2)
            umu_id = model.data(umu_id_index, Qt.ItemDataRole.DisplayRole)
            self.launch_script_name_input.setText(umu_id + ".sh")
        else:
            self.launch_script_name_input.clear() #Clear the text box if nothing is selected


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

        results = search_umu_database(search_term)

        if isinstance(results, str):
            QMessageBox.critical(self, "Search Error", results)
            return

        self.model.clear()

        if results.empty:
            root_node = self.model.invisibleRootItem()
            no_results_item = QStandardItem("No matches found.")
            no_results_item.setFlags(Qt.ItemFlag.NoItemFlags)
            root_node.appendRow(no_results_item)
            return

        self.model.setHorizontalHeaderLabels(results.columns.tolist())

        for _, row in results.iterrows():
            items = [QStandardItem(str(row[col])) for col in results.columns]
            for item in items:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.model.appendRow(items)

        self.tree_view.resizeColumnToContents(0)
        self.tree_view.resizeColumnToContents(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    set_default_config()
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    sys.exit(exit_code)