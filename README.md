# Virtualenv Manager for Sublime Text

This is a plugin for Sublime Text that provides a simple and efficient way to manage Python virtual environments directly from the editor. The plugin allows you to:

- **List available virtual environments**: Automatically detects virtual environments in specified directories.
- **Activate a virtual environment**: Updates the environment variables and adds the selected virtual environment to the `PATH`.
- **Deactivate the current virtual environment**: Restores the system environment to its original state.
- **Integration with LSP-pyright and LSP-basedpyright**: Attempts to notify the LSP language server about the active virtual environment, enabling better Python language support.

## Features

1. **Quick Panel Selection**: Use a quick panel to select and activate a virtual environment.
2. **Customizable Directories**: Configure directories to search for virtual environments in the `Virtualenv.sublime-settings` file.
3. **Automatic PATH Update**: Updates the `PATH` environment variable to include the selected virtual environment.
4. **Basic LSP-pyright Integration**: Notifies LSP-pyright when the virtual environment changes, though full automatic integration with LSP-pyright is not yet functional.

## Requirements

- Sublime Text 4
- [LSP-pyright](https://github.com/sublimelsp/LSP-pyright) or [LSP-basedpyright](https://github.com/sublimelsp/LSP-basedpyright) (optional, for enhanced Python language support) 
- Python installed on your system

## Installation

1. Clone this repository into your Sublime Text `Packages` directory:
   ```
   git clone https://github.com/<your-username>/<your-repo>.git "Virtualenv"
   ```
2. Restart Sublime Text.

## Usage

### Activating a Virtual Environment

1. Open the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P` on macOS).
2. Run the command `Virtualenv: Activate Virtual Environment`.
3. Select a virtual environment from the list.

### Deactivating a Virtual Environment

1. Open the Command Palette.
2. Run the command `Virtualenv: Deactivate Virtual Environment`.

### Configuring Virtual Environment Directories

1. Open the `Virtualenv.sublime-settings` file:
   - From the Command Palette, run `Preferences: Virtualenv Settings`.
2. Add or modify the `environment_directories` setting to include paths where your virtual environments are located. For example:
   ```
   {
       "environment_directories": [
           "~/.virtualenvs",
           "~/my_other_envs"
       ]
   }
   ```

## Known Issues

- The automatic activation of Pyright using the selected virtual environment does not fully work yet. The LSP-pyright language server is notified, but it may not correctly switch environments.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests to enhance functionality or fix bugs.

## License

This plugin is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Author
- **Author:** Andrea Alberti
- **GitHub Profile:** [alberti42](https://github.com/alberti42)
- **Donations:** [![Buy Me a Coffee](https://img.shields.io/badge/Donate-Buy%20Me%20a%20Coffee-orange)](https://buymeacoffee.com/alberti)

Feel free to contribute to the development of this plugin or report any issues in the [GitHub repository](https://github.com/alberti42/sublime-virtualenv/issues).
