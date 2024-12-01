from LSP.plugin.core.windows import WindowRegistry
import sublime
import sublime_plugin
import os
import sys
from abc import ABC, abstractmethod
from typing import Callable, Union, Optional, Any, Dict, List, Type, Literal, TYPE_CHECKING, cast
import logging

# --- Logging functions (BEGIN) ------------------------------------------------------------

# Configure the "Virtualenv" logger directly
logger = logging.getLogger("Virtualenv")
logger.setLevel(logging.INFO)  # Set the logging level
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.handlers.clear() # Remove existing handlers (if any)
logger.addHandler(handler)

LogLevels = list(logging._nameToLevel.keys())
Typing_LogLevel = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

def get_normalized_log_level(level: Any) -> Typing_LogLevel:
    """
    Normalize the provided log level to a valid logging level.

    Args:
        level (Union[str, int, None]): The level to validate and normalize.

    Returns:
        Typing_LogLevel: The log level in normalized form ("NOTSET", "DEBUG", etc.).
    """
    # Ensure level is a string and normalize it
    if isinstance(level, str):
        normalized_level = level.strip().upper()
        if normalized_level in logging._nameToLevel.keys():
            #  We apply the dictionary back and forth to get rid of synonymes in the log levels
            return cast(Typing_LogLevel,logging._levelToName[logging._nameToLevel[normalized_level]])

    # Fallback to "NOTSET" for invalid cases
    return "NOTSET"

# --- Logging functions (END) ------------------------------------------------------------

# --- OptionalPluginHandler (BEGIN) ------------------------------------------------------------

if TYPE_CHECKING:
    from LSP.plugin.core.sessions import Session as Typing_LSP_Session
    from LSP.plugin.core.protocol import Notification as Typing_LSP_Notification
else:
    Typing_LSP_Session = None       # Fallback to None for runtime
    Typing_LSP_Notification = None  # Fallback to None for runtime

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
                        print(f"Class '{class_name}' not found in module '{module_name}'.")
                        all_available = False
                        self._cached_classes[key] = None
                else:
                    print(f"Module '{module_name}' not found.")
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
    def Notification(self) -> Type["Typing_LSP_Notification"]:
        """Retrieve the Notification class."""
        Notification = self.get_cached_class("LSP.plugin.core.protocol", "Notification")
        if Notification is None:
            raise RuntimeError("Notification not found in LSP.plugin.core.protocol")
        return Notification

class LSP_pyrightPluginHandler(OptionalPluginHandler):
    """
    Concrete implementation for handling the LSP plugin.
    """
    @property
    def required_members(self) -> List[Dict[str, str]]:
        return [
            {"member": "LspPyrightCreateConfigurationCommand", "module": "LSP-pyright.plugin"},
        ]

    def is_plugin_available(self) -> bool:
        # Check that both plugins are available, LSP and LSP-pyright
        lsp_plugin_handler = LSPPluginHandler()
        return lsp_plugin_handler.is_plugin_available and super().is_plugin_available

# --- Derived classes (END) ------------------------------------------------------------

# --- LSP functions (BEGIN) ------------------------------------------------------------

def get_lsp_session()->Optional[Typing_LSP_Session]:
    """Retrieve the active LSP session for LSP-pyright."""

    lsp_plugin_handler = LSPPluginHandler()
    LSP_windows = lsp_plugin_handler.windows

    window = sublime.active_window()  # Use Sublime's active window
    
    lsp_window = LSP_windows.lookup(window)  # LSP's registry lookup
    if not lsp_window:
        logger.error("No LSP window context found.")
        return None

    session = lsp_window.get_session("LSP-pyright", "syntax")
    if session is not None:
        return session
    else:
        logger.error("No active LSP-pyright session found.")
        return None

def send_did_change_configuration(session: Typing_LSP_Session, config: dict)->None:
    """Send a workspace/didChangeConfiguration notification to the LSP server."""

    lsp_plugin_handler = LSPPluginHandler()
    Notification = lsp_plugin_handler.Notification

    params = {"settings": config}
    notification = Notification("workspace/didChangeConfiguration", params)
    session.send_notification(notification)

def reconfigure_lsp_pyright(python_path:str)->None:
    """Trigger the workspace/configuration request to update LSP-pyright."""

    session = get_lsp_session()
    if not session:
        return

    # Create the configuration
    new_config = {
        "python": {
            "pythonPath": python_path,
            "analysis": {
                "typeCheckingMode": "basic",
                "reportOptionalSubscript": "error"
            }
        }
    }

    logger.debug(f"NEW CONFIG: {new_config}")
    
    send_did_change_configuration(session, new_config)

# --- LSP functions (END) ------------------------------------------------------------


class VirtualenvCommand(sublime_plugin.WindowCommand):
    """Base class for handling Python virtual environments."""

    _settings:Optional[sublime.Settings] = None # Cache the current settings
    _log_level:Typing_LogLevel = "INFO" # Cache the current log level

    def __init__(self, window: sublime.Window):
        super().__init__(window)

        self.load_settings()

    def settings_filename(self):
        """Compute the settings file key based on the platform."""
        env_vars = self.window.extract_variables()
        filename = 'Virtualenv (${platform}).sublime-settings'
        expanded = sublime.expand_variables(filename, env_vars)
        
        # Ensure expanded is a string
        if not isinstance(expanded, str):
            raise ValueError("Expanded settings filename must be a string.")

        return expanded

    @property
    def settings(self) -> sublime.Settings:
        if self._settings is None:
            raise RuntimeError("Unexpected error where Settings was not loaded")
        return self._settings

    def load_settings(self):
        """Load the platform-specific plugin settings and set up listeners."""
        settings_filename = self.settings_filename()
        # sublime.load_settings() returns a reference to the live settings object managed by Sublime
        self._settings = sublime.load_settings(settings_filename)
        
        # Add a listener for changes to the "log_level" setting
        self._settings.clear_on_change("VirtualenvCommand")
        self._settings.add_on_change("VirtualenvCommand", self.on_settings_changed)

        # React to the current "log_level" value
        self.on_settings_changed()

    def on_settings_changed(self):
        """React to changes in the settings."""
        if self.settings:
            new_log_level = self.settings.get("log_level", "INFO")  # Default to "INFO"
            if new_log_level != self._log_level:
                normalizedLogLevel = get_normalized_log_level(new_log_level)
                if normalizedLogLevel is not logging.NOTSET:
                    # Change the logging level only if a valid log level is provided
                    self._log_level = normalizedLogLevel
                    self.handle_log_level_change(new_log_level)

    def handle_log_level_change(self, new_log_level):
        """Handle changes to the log level setting."""
        logger.info(f"Log level changed to: {new_log_level}")
        logger.setLevel(self._log_level)

    @property
    def venv_directories(self):
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

    @property
    def venvs(self):
        """List all virtual environments in the venv directories."""
        environments = []
        for directory in self.venv_directories:
            try:
                environments.extend(
                    {"env":env, "dir":directory}
                    for env in os.listdir(directory) if os.path.isdir(os.path.join(directory, env))
                )
            except FileNotFoundError:
                # Skip directories that don't exist
                continue
        return environments

    def activate_virtualenv(self, venv_index):
        """Set environment variables to activate the selected virtualenv."""
        selected_venv = self.venvs[venv_index]
        venv_path = os.path.join(selected_venv['dir'], selected_venv['env'])
        if not os.path.exists(venv_path):
            sublime.error_message(f"Virtualenv '{venv_path}' does not exist.")
            return

        # Set $VIRTUAL_ENV
        os.environ["VIRTUAL_ENV"] = venv_path

        # Add to PATH the virtualenv's bin directory
        venv_bin_path = os.path.join(venv_path, "Scripts" if os.name == "nt" else "bin")
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join([venv_bin_path, current_path])
        logger.debug(f'PATH: {os.environ["PATH"]}')

        lsp_pyright_plugin_handler = LSP_pyrightPluginHandler()
        if lsp_pyright_plugin_handler.is_plugin_available:
            reconfigure_lsp_pyright(os.path.join(venv_bin_path,'python'))
        
        msg = f'Activated virtualenv: {selected_venv["env"]}'
        sublime.status_message(msg)
        logger.info(msg)

    def deactivate_virtualenv(self):
        """Clear the virtual environment from the environment variables."""
        os.environ.pop("VIRTUAL_ENV", None)

        # Filter out the virtual environment's bin directory from PATH
        venv_bin_paths = [os.path.join(directory, env, "bin") for directory in self.venv_directories for env in os.listdir(directory) if os.path.isdir(os.path.join(directory, env))]
        current_path = os.environ.get("PATH", "").split(os.pathsep)
        filtered_path = [path for path in current_path if path not in venv_bin_paths]
        os.environ["PATH"] = os.pathsep.join(filtered_path)

        sublime.status_message("Deactivated virtualenv.")



class ActivateVirtualenvCommand(VirtualenvCommand):
    """Command to list and activate virtual environments."""

    def run(self):
        """Show a quick panel with available virtual environments."""
        venvs = self.venvs
        if not venvs:
            sublime.error_message("No virtual environments found in ~/.virtualenvs.")
            return

        self.window.show_quick_panel(
            [sublime.QuickPanelItem(venv["env"],"<i>"+venv["dir"]+"</i>") for venv in venvs], self.on_select, placeholder="Select a virtualenv to activate"
        )

    def on_select(self, index):
        """Handle selection from the quick panel."""
        if index == -1:
            return
        self.activate_virtualenv(index)


class DeactivateVirtualenvCommand(VirtualenvCommand):
    """Command to deactivate the current virtual environment."""

    def run(self):
        """Deactivate the currently active virtual environment."""
        self.deactivate_virtualenv()
