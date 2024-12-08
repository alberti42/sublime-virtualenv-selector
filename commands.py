from LSP.plugin.core.windows import WindowRegistry
import sublime
import sublime_plugin
import os
import sys
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List, Type, TypedDict, Literal, TYPE_CHECKING, cast
import logging

# --- Type checking -------------------------------------------------------------------------

class VirtualEnvInfo(TypedDict):
    env: str
    dir: str

class ActivatedVirtualEnvInfo(TypedDict):
    env: Optional[str]
    added_path: Optional[str]
    VIRTUAL_ENV: str

LSPPluginType = Literal["LSP-pyright","LSP-basedpyright","None"]

# --- Logging functions (BEGIN) ------------------------------------------------------------

# Configure the "Virtualenv" logger directly
logger = logging.getLogger("Virtualenv")

LogLevels = list(logging._nameToLevel.keys())
LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# --- Logging functions (END) ---------------------------------------------------------------


# --- Loading/unloading the plugin (BEGIN) --------------------------------------------------

def plugin_loaded() -> None:
    """Initialize the plugin by loading the Virtual Environment Manager."""

    # Create a singleton instance of VirtualenvManager
    VirtualenvManager()

# --- Loading/unloading the plugin (END) ----------------------------------------------------


# --- Virtual Environment Manager (BEGIN) ---------------------------------------------------

class VirtualenvManager:
    """Singleton class to manage virtual environments in Sublime Text."""

    _instance:Optional["VirtualenvManager"] = None  # Class-level variable to store the singleton instance
    _activated_envs:List["ActivatedVirtualEnvInfo"] = [] # Tracks the active virtual environment

    _settings_filename:Optional[str] = None # File name of settings
    _settings:Optional[sublime.Settings] = None # Cache the current settings
    _log_level:Optional[LogLevelType] = None # Cache the current log level
    _LSP_plugin:Optional["LSPPluginType"] = None # Cache the selected LSP plugin

    def __new__(cls):
        if cls._instance is None:
            # Create a new instance if one doesn't already exist
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize the class."""

        # Load settings
        self._settings = self.load_settings()
        
        # Add a listener for changes to the "log_level" setting
        self._settings.clear_on_change("VirtualenvCommand")
        self._settings.add_on_change("VirtualenvCommand", self.on_settings_changed)

        # React to the current "log_level" value
        self.on_settings_changed()

        # Initialize active environment info
        if "VIRTUAL_ENV" in os.environ:
            self._activated_envs = [{
                "env": None,
                "added_path":None,
                "VIRTUAL_ENV":os.environ["VIRTUAL_ENV"]
            }]
        else:
            self._activated_envs = []

    @property
    def settings_filename(self) -> str:
        """Compute the settings file key based on the platform."""
        
        if self._settings_filename is not None:
            return self._settings_filename

        platform_mapping = {
            "win": "Windows",
            "osx": "OSX",
            "linux": "Linux"
        }

        platform = platform_mapping[sublime.platform()]

        filename = f'Virtualenv ({platform}).sublime-settings'
        
        # Ensure expanded is a string
        if not isinstance(filename, str):
            raise ValueError("Expanded settings filename must be a string.")

        # Cache the filename
        self._settings_filename = filename

        return filename

    @property
    def settings(self) -> sublime.Settings:
        """Return self._settings and check that it is correctly configured."""
        if self._settings is None:
            raise RuntimeError("Unexpected error where Settings was not loaded")
        return self._settings

    def load_settings(self) -> sublime.Settings:
        """Load the platform-specific plugin settings and set up listeners."""
        
        # sublime.load_settings() returns a reference to the live settings object managed by Sublime
        return sublime.load_settings(self.settings_filename)

    @staticmethod
    def validate_LSP_plugin(LSP_plugin: Any) -> Optional[LSPPluginType]:
        """Validate setting LSP_plugin."""

        valid_LSP_plugins = ["LSP-pyright","LSP-basedpyright","None"]
        
        if isinstance(LSP_plugin,str):
            if LSP_plugin == "None":
                return None
            if LSP_plugin in valid_LSP_plugins:
                return cast(LSPPluginType,LSP_plugin)
    
        # Fallback to "NOTSET" for invalid cases
        logger.warning(f"Invalid LSP_plugin setting: {LSP_plugin}")
        return None

    @staticmethod
    def validate_log_level(level: Any) -> Optional[LogLevelType]:
        """
        Normalize the provided log level to a valid logging level.

        Args:
            level (Any): The level to validate and normalize.

        Returns:
            LogLevelType: The log level in normalized form ("DEBUG", "INFO", etc.).
        """
        
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

        # Ensure level is a string
        if isinstance(level, str):
            if level in valid_log_levels:
                #  We apply the dictionary back and forth to get rid of synonymes in the log levels
                return cast(LogLevelType,logging._levelToName[logging._nameToLevel[level]])

        # Fallback to None for invalid cases
        logger.warning(f"Invalid log_level setting: {level}")
        return None

    def on_settings_changed(self) -> None:
        """React to changes in the settings."""

        new_log_level:Optional[LogLevelType] = self.validate_log_level(self.settings.get("log_level"))  # Default to "INFO"
        if new_log_level and new_log_level != self._log_level:
            if new_log_level is not logging.NOTSET:
                # Change the logging level only if a valid log level is provided
                self.handle_log_level_change(new_log_level)

        new_LSP_plugin:Optional[LSPPluginType] = self.validate_LSP_plugin(self.settings.get("LSP_plugin"))
        if new_LSP_plugin and new_LSP_plugin != self._LSP_plugin:
            self.handle_LSP_plugin_change(new_LSP_plugin)

    def handle_log_level_change(self, new_log_level:LogLevelType) -> None:
        """Handle changes to the log level setting."""
        
        if self._log_level is not None:
            logger.info(f"Log level changed to: {new_log_level}")
        self._log_level = new_log_level
        logger.setLevel(self._log_level)

    def handle_LSP_plugin_change(self,new_LSP_plugin:LSPPluginType) -> None:
        """Handle changes to the LSP plugin setting."""

        if self._LSP_plugin is not None:
            logger.info(f"LSP plugin changed to: {new_LSP_plugin}")

        self._LSP_plugin = new_LSP_plugin

        # Load the last activated environment
        if len(self._activated_envs) == 0:
            return
        active_env = self._activated_envs[-1]

        # Create python path
        pythonPath = self.get_python_path(self.get_bin_path(active_env["VIRTUAL_ENV"]))

        # Notify the LSP plugin
        self.notify_LSP(pythonPath)

    @property
    def venv_directories(self) -> List[str]:
        settings = self.settings
        directories = settings.get('environment_directories', [])
        if not isinstance(directories, list):
            raise ValueError(f"'environment_directories' should be a list, but got {type(directories)}.")

        # Ensure all entries are valid strings
        validated_directories = []
        for directory in directories:
            if isinstance(directory, str):
                validated_directories.append(os.path.expanduser(directory))
            else:
                sublime.error_message(f"Ignored invalid entry in 'environment_directories': {directory}")

        return validated_directories

    def get_venvs(self,window:sublime.Window) -> List["VirtualEnvInfo"]:
        """List all virtual environments in the venv directories."""
        environments: List["VirtualEnvInfo"] = []

        # Add virtual environments from the configured directories
        for directory in self.venv_directories:
            try:
                environments.extend(
                    {"env": env, "dir": directory}
                    for env in os.listdir(directory) if os.path.isdir(os.path.join(directory, env))
                )
            except FileNotFoundError:
                # Skip directories that don't exist
                continue

        # Check for `.venv` in project folders and add it
        project_folders = window.folders()
        for folder in project_folders:
            venv_path = os.path.join(folder, '.venv')
            if os.path.isdir(venv_path):
                environments.append({"env": ".venv", "dir": folder})

        return environments

    @staticmethod
    def get_bin_path(venv_path:str) -> str:
        return os.path.join(venv_path, "Scripts" if sublime.platform == "win" else "bin")

    @staticmethod
    def get_python_path(venv_bin_path:str) -> str:
        return os.path.join(venv_bin_path,'python')

    def activate_virtualenv(self,selected_venv:"VirtualEnvInfo") -> None:
        
        venv_path = os.path.join(selected_venv['dir'], selected_venv['env'])
        if not os.path.exists(venv_path):
            sublime.error_message(f"Virtualenv '{venv_path}' does not exist.")
            return

        # Keep track of the added environment name
        env = selected_venv["env"]

        # Path to be added
        venv_bin_path = self.get_bin_path(venv_path)

        # Remove from PATH the path of previously activated environment
        if len(self._activated_envs)>0:
            old_added_path = self._activated_envs[-1]["added_path"]
            # If the old added path differs from the currently added path, then remove it
            if old_added_path and old_added_path != venv_bin_path:
                self.remove_first_occurrence_in_PATH(old_added_path)

        # Add to PATH the virtualenv's bin directory
        added_path = None
        if self.add_to_PATH(venv_bin_path):
            added_path = venv_bin_path

        # Set VIRTUAL_ENV
        VIRTUAL_ENV = venv_path
        os.environ["VIRTUAL_ENV"] = VIRTUAL_ENV

        self._activated_envs.append({
            "env": env,
            "VIRTUAL_ENV": VIRTUAL_ENV,
            "added_path": added_path
        })

        # Python path
        pythonPath = self.get_python_path(venv_bin_path)

        # Notify the LSP plugin
        self.notify_LSP(pythonPath)

        msg = f'Activated virtualenv: {selected_venv["env"]}'
        sublime.status_message(msg)
        logger.info(msg)

    def notify_LSP(self,pythonPath:str) -> None:
        """Notify the LSP plugin that a virtual environment has been activated."""

        if self._LSP_plugin is None:
            return

        lsp_pyright_plugin_handler = LSP_pythonPluginHandler(self._LSP_plugin)
        
        if lsp_pyright_plugin_handler.is_plugin_available:
            reconfigure_lsp_pyright(self._LSP_plugin,pythonPath)
        
    def deactivate_virtualenv(self) -> None:
        """Clear the virtual environment from the environment variables."""

        if len(self._activated_envs)==0:
            logger.debug("No venv to be deactivated")
            return

        # Environment to deactivate, remove it from the queue
        env_to_be_deactivated = self._activated_envs.pop()

        # Last activated environment
        env_prev_activated = Optional[ActivatedVirtualEnvInfo]
        if len(self._activated_envs)>0:
            logger.debug(f'venv {self._activated_envs[-1]["env"]} found that was previously activated')
            env_prev_activated = self._activated_envs[-1]
        else:
            env_prev_activated = None

        # Remove the added path
        if env_to_be_deactivated["added_path"]:
            self.remove_first_occurrence_in_PATH(env_to_be_deactivated["added_path"])

        # Restore the VIRTUAL_ENV variable
        if env_prev_activated:
            os.environ["VIRTUAL_ENV"] = env_prev_activated["VIRTUAL_ENV"]
            logger.debug(f'Updated VIRTUAL_ENV: {env_prev_activated["VIRTUAL_ENV"]}')
        else:
            os.environ.pop("VIRTUAL_ENV",None)
            logger.debug("Removed VIRTUAL_ENV variable")

        # Restore the old added path
        if env_prev_activated and env_prev_activated["added_path"]:
            was_path_added = self.add_to_PATH(env_prev_activated["added_path"])
            if was_path_added is False:
                env_prev_activated["added_path"] = None
    
        # Create python path
        pythonPath = self.get_python_path(self.get_bin_path(env_prev_activated["VIRTUAL_ENV"])) if env_prev_activated else ""

        # Notify the LSP plugin
        self.notify_LSP(pythonPath)

        msg = "Deactivated virtualenv."
        logger.info(msg)
        sublime.status_message(msg)

    @staticmethod
    def add_to_PATH(path_to_add:str) -> bool:
        """Add path_to_add to PATH."""

        current_path:Optional[str] = os.environ.get("PATH")
        current_path_items:Optional[List[str]] = None
        if current_path is not None and current_path.strip() != "":
            current_path_items = current_path.strip().split(":")
        
        if current_path_items is None:
            current_path_items = []

        if len(current_path_items)==0 or current_path_items[0] != path_to_add:
            current_path_items.insert(0, path_to_add)
            os.environ["PATH"] = os.pathsep.join(current_path_items)
            return True

        return False

    @staticmethod
    def remove_first_occurrence_in_PATH(path_to_remove:str) -> bool:
        """Remove first occurence of path_to_remove in PATH."""

        is_path_removed = False

        # Filter out the virtual environment's bin directory from PATH
        current_path:Optional[str] = os.environ.get("PATH")
        current_path_items:Optional[List[str]] = None
        if current_path is not None and current_path.strip() != "":
            current_path_items = current_path.strip().split(":")
        
        # Remove first occurrence of added_path in PATH items
        if current_path_items is not None:
            for index,current_path_item in enumerate(current_path_items):
                if current_path_item == path_to_remove:
                    del current_path_items[index]
                    is_path_removed = True
                    break

            if is_path_removed:
                os.environ["PATH"] = os.pathsep.join(current_path_items)

        return is_path_removed

# --- OptionalPluginHandler (BEGIN) ------------------------------------------------------------

if TYPE_CHECKING:
    from LSP.plugin.core.sessions import Session as LSPSessionType
    from LSP.plugin.core.protocol import Notification as LSPNotificationType
else:
    LSPSessionType = None       # Fallback to None for runtime
    LSPNotificationType = None  # Fallback to None for runtime

class OptionalPluginHandler(ABC):
    """
    Abstract base class for handling optional plugins with required classes.
    """
    _instance = None
    _is_available: Optional[bool] = None
    _cached_classes: Dict[str, Any] = {}  # Cache for class references

    @property
    @abstractmethod
    def required_members(self) -> List[Dict[str, str]]:
        """
        Define the required classes and their respective modules.
        Must be overridden in subclasses.
        """
        pass

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(OptionalPluginHandler, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the class by pre-checking if the plugin is available."""
        _ = self.is_plugin_available  # Trigger the property to cache availability

    @property
    def is_plugin_available(self) -> bool:
        """
        Check if the required classes are loaded and cache their references.

        Returns:
            bool: True if the plugin's required classes are available, False otherwise.
        """
        if self._is_available is None:
            all_available = True

            for required_class in self.required_members:
                module_name = required_class["module"]
                class_name = required_class["member"]
                key = f"{module_name}.{class_name}".replace(".", "_")

                if module_name in sys.modules:
                    module = sys.modules[module_name]
                    try:
                        # Cache the class reference
                        self._cached_classes[key] = getattr(module, class_name)
                    except AttributeError:
                        logger.error(f"Class '{class_name}' not found in module '{module_name}'.")
                        all_available = False
                        self._cached_classes[key] = None
                else:
                    logger.error(f"Module '{module_name}' not found.")
                    all_available = False
                    self._cached_classes[key] = None

            self._is_available = all_available
        return self._is_available

    def get_cached_class(self, module_name: str, class_name: str) -> Optional[Any]:
        """
        Retrieve a cached class reference by module and class name.

        Args:
            module_name (str): The module name.
            class_name (str): The class name.

        Returns:
            Optional[Any]: The cached class reference, or None if not found.
        """
        key = f"{module_name}.{class_name}".replace(".", "_")
        return self._cached_classes.get(key, None)

# --- OptionalPluginHandler (END) ------------------------------------------------------------

# --- Derived classes (BEGIN) ------------------------------------------------------------

class LSPPluginHandler(OptionalPluginHandler):
    """
    Concrete implementation for handling the LSP plugin.
    """
    @property
    def required_members(self) -> List[Dict[str, str]]:
        return [
            {"member": "windows", "module": "LSP.plugin.core.registry"},
            {"member": "Notification", "module": "LSP.plugin.core.protocol"},
        ]

    @property
    def windows(self) -> WindowRegistry:
        """Retrieve the windows registry."""
        windows = self.get_cached_class("LSP.plugin.core.registry", "windows")
        if windows is None:
            raise RuntimeError("windows not found in LSP.plugin.core.registry")
        return windows

    @property
    def Notification(self) -> Type["LSPNotificationType"]:
        """Retrieve the Notification class."""
        Notification = self.get_cached_class("LSP.plugin.core.protocol", "Notification")
        if Notification is None:
            raise RuntimeError("Notification not found in LSP.plugin.core.protocol")
        return Notification

class LSP_pythonPluginHandler(OptionalPluginHandler):
    """
    Concrete implementation for handling the LSP plugin.
    """
    _LSP_plugin: Optional[str]

    def __init__(self,LSP_plugin:LSPPluginType):
        self._LSP_plugin = LSP_plugin

    @property
    def required_members(self) -> List[Dict[str, str]]:
        if self._LSP_plugin == "LSP-pyright":
            return [
                {"member": "LspPyrightCreateConfigurationCommand", "module": "LSP-pyright.plugin"},
            ]
        elif self._LSP_plugin == "LSP-basedpyright":
            return [
                {"member": "LspBasedpyrightCreateConfigurationCommand", "module": "LSP-basedpyright.plugin"},
            ]
        else:
            return []

    def is_plugin_available(self) -> bool:
        if self._LSP_plugin == "None":
            return False

        # Check that both plugins are available, LSP and LSP-pyright
        lsp_plugin_handler = LSPPluginHandler()
        return lsp_plugin_handler.is_plugin_available and super().is_plugin_available

# --- Derived classes (END) ------------------------------------------------------------

# --- LSP functions (BEGIN) ------------------------------------------------------------

def get_lsp_session(LSP_plugin:LSPPluginType)->Optional[LSPSessionType]:
    """Retrieve the active LSP session for the LSP plugin {LSP-pyright or LSP-basedpyright}."""

    lsp_plugin_handler = LSPPluginHandler()
    LSP_windows = lsp_plugin_handler.windows

    window = sublime.active_window()  # Use Sublime's active window
    
    lsp_window = LSP_windows.lookup(window)  # LSP's registry lookup
    if not lsp_window:
        logger.error("No LSP window context found.")
        return None

    session:Optional[LSPSessionType] = lsp_window.get_session(LSP_plugin, "syntax")
    if session is None:
        logger.error(f"No active {LSP_plugin} session found.")
        return None
    else:
        return session

def send_did_change_configuration(session: LSPSessionType, config: dict)->None:
    """Send a workspace/didChangeConfiguration notification to the LSP server."""

    lsp_plugin_handler = LSPPluginHandler()
    Notification = lsp_plugin_handler.Notification

    params = {"settings": config}
    notification = Notification("workspace/didChangeConfiguration", params)
    session.send_notification(notification)

def reconfigure_lsp_pyright(LSP_plugin:LSPPluginType, python_path:str)->None:
    """Trigger the workspace/configuration request to update LSP-pyright."""

    session = get_lsp_session(LSP_plugin)
    if not session:
        return

    # Create the configuration
    new_config = {
        "python": {
            "pythonPath": python_path,
            # "analysis": {
            #     "typeCheckingMode": "basic",
            #     "reportOptionalSubscript": "error"
            # }
        }
    }

    logger.debug(f"pythonPath: {python_path}")
    
    send_did_change_configuration(session, new_config)

# --- LSP functions (END) ------------------------------------------------------------

# --- ActivateVirtualenvCommand (BEGIN) ----------------------------------------------

class ActivateVirtualenvCommand(sublime_plugin.WindowCommand):
    """Command to list and activate virtual environments."""

    _venvs:Optional[List["VirtualEnvInfo"]] = None
    _manager:Optional["VirtualenvManager"] = None

    def run(self) -> None:
        """Show a quick panel with available virtual environments."""

        # Load the Virtual Environment Manager
        self._manager = VirtualenvManager()

        # Get the list of available virtual environments
        self._venvs = self._manager.get_venvs(self.window)

        panel_items:List[sublime.QuickPanelItem]
        if self._venvs:
            panel_items=[sublime.QuickPanelItem(venv["env"],"<i>"+venv["dir"]+"</i>") for venv in self._venvs]
        else:
            panel_items=[sublime.QuickPanelItem("No virtual environments found","<i>Add any directory containing virtual environments to <b>environment_directories</b> in the settings.</i>")]

        self.window.show_quick_panel(
            panel_items, self.on_select, placeholder="Select a virtualenv to activate"
        )

    def on_select(self, index:int) -> None:
        """Handle selection from the quick panel."""
        if index == -1:
            return
        
        if self._manager is None:
            raise RuntimeError("Unexpected error: VirtualenvManager not loaded") 

        if self._venvs is None:
            # If no virtual environments were found, opens the Virtualenv user settings file
            sublime.active_window().run_command("open_file", {"file": "${packages}/User/" + self._manager.settings_filename})
            return
        
        selected_venv = self._venvs[index]

        # Notify the manager of activation of venv
        self._manager.activate_virtualenv(selected_venv)


# --- ActivateVirtualenvCommand (END) ----------------------------------------------

# --- DeactivateVirtualenvCommand (BEGIN) ------------------------------------------

class DeactivateVirtualenvCommand(sublime_plugin.WindowCommand):
    """Command to deactivate the current virtual environment."""

    def run(self):
        """Deactivate the currently active virtual environment."""
        
        # Deactive the virtual environment
        VirtualenvManager().deactivate_virtualenv()
            
# --- DeactivateVirtualenvCommand (END) --------------------------------------------
