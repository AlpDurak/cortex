from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_installer(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class InstallScriptTests(unittest.TestCase):
    def test_windows_installer_defaults_to_home_scoped_install_dir(self):
        script = read_installer("install.ps1")

        self.assertIn('$INSTALL_ROOT = Join-Path $env:USERPROFILE ".cortex"', script)
        self.assertIn('$INSTALL_DIR  = Join-Path $INSTALL_ROOT "cortex"', script)
        self.assertNotIn('$INSTALL_DIR = "cortex"', script)

    def test_windows_installer_bootstraps_pip_after_creating_venv(self):
        script = read_installer("install.ps1")

        self.assertIn('-m venv --without-pip "$INSTALL_DIR\\.venv"', script)
        self.assertIn("-m ensurepip --upgrade --default-pip", script)

    def test_windows_installer_updates_user_and_current_process_path(self):
        script = read_installer("install.ps1")

        self.assertIn('[Environment]::SetEnvironmentVariable("PATH", $newUserPath, "User")', script)
        self.assertIn('$env:PATH = "$venvScripts;$env:PATH"', script)
        self.assertIn('SendMessageTimeout', script)
        self.assertIn('"Environment"', script)

    def test_unix_installer_defaults_to_home_scoped_install_dir(self):
        script = read_installer("install.sh")

        self.assertIn('INSTALL_ROOT="$HOME/.cortex"', script)
        self.assertIn('INSTALL_DIR="$INSTALL_ROOT/cortex"', script)
        self.assertNotIn('INSTALL_DIR="cortex"', script)

    def test_unix_installer_bootstraps_pip_after_creating_venv(self):
        script = read_installer("install.sh")

        self.assertIn('"$PYTHON_CMD" -m venv --without-pip "$INSTALL_DIR/.venv"', script)
        self.assertIn("-m ensurepip --upgrade --default-pip", script)

    def test_unix_installer_adds_local_bin_to_shell_startup_files(self):
        script = read_installer("install.sh")

        self.assertIn('ensure_path_file "$HOME/.profile"', script)
        self.assertIn('ensure_path_file "$HOME/.bashrc"', script)
        self.assertIn('ensure_path_file "$HOME/.zprofile"', script)
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', script)
        self.assertIn('CORTEX PATH', script)


if __name__ == "__main__":
    unittest.main()
