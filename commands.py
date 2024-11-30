import sublime
import sublime_plugin
import os
import sys
from typing import Callable, Union

reconfigure_lsp_pyright:Union[Callable[[str], None], None] = None

if all([module in sys.modules for module in [
        "LSP.plugin.core.registry",
        "LSP.plugin.core.sessions",
        "LSP.plugin.core.protocol",
        "LSP-pyright"
]]):
    try:
        import LSP.plugin.core.sessions as LSP_plugin_core_sessions
        import LSP.plugin.core.protocol as LSP_plugin_core_protocol
        import LSP.plugin.core.registry as LSP_plugin_core_registry
    except ImportError:
        raise RuntimeError("LSP-pyright is not installed.")
    
    def get_lsp_session()->Union[LSP_plugin_core_sessions.Session,None]:
        """Retrieve the active LSP session for LSP-pyright."""
        
        window = sublime.active_window()  # Use Sublime's active window
        if not window:
            return None

        lsp_window = LSP_plugin_core_registry.windows.lookup(window)  # LSP's registry lookup
        if not lsp_window:
            print("No LSP window context found.")
            return None

        session = lsp_window.get_session("LSP-pyright", "syntax")
        if isinstance(session, LSP_plugin_core_sessions.Session):
            return session
        else:
            print("No active LSP-pyright session found.")
            return None

    def send_did_change_configuration(session: LSP_plugin_core_sessions.Session, config: dict)->None:
        """Send a workspace/didChangeConfiguration notification to the LSP server."""
        params = {"settings": config}
        notification = LSP_plugin_core_protocol.Notification("workspace/didChangeConfiguration", params)
        session.send_notification(notification)

    def reconfigure_lsp_pyright_with_LSP(python_path:str)->None:
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

        print("NEW CONFIG")
        print(new_config)

        # print(f"[DEBUG] Sending configuration: {new_config}")
        send_did_change_configuration(session, new_config)
    
    reconfigure_lsp_pyright = reconfigure_lsp_pyright_with_LSP


class VirtualenvCommand(sublime_plugin.WindowCommand):
    """Base class for handling Python virtual environments."""

    @property
    def settings(self):
        """Load the platform-specific plugin settings for commands to use."""
        env_vars = self.window.extract_variables()
        filename = 'Virtualenv (${platform}).sublime-settings'  # the template ${platform} will be replaced by sublime.expand_variables
        expanded = sublime.expand_variables(filename, env_vars)
        
        # Ensure expanded is a string
        if not isinstance(expanded, str):
            raise ValueError("Expanded settings filename must be a string.")

        return sublime.load_settings(expanded)

    @property
    def venv_directories(self):
        directories = self.settings.get('environment_directories', [])
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
        venv_bin_path = os.path.join(venv_path, "bin")
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join([venv_bin_path, current_path])

        if reconfigure_lsp_pyright:
            # Notify LSP-pyright of the virtual environment change
            reconfigure_lsp_pyright(os.path.join(venv_bin_path,'python'))

        sublime.status_message(f"Activated virtualenv: {venv_index}")

        print("DONE")

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
