"""Cross-platform path and Tesseract-discovery rules.

Runs on Windows and Linux CI: every OS-specific branch is exercised by patching
the small predicates in the modules under test, so the Windows behaviour is
verified even when the test runs on Linux.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redaction_tool import ocr, paths, presets  # noqa: E402


class UserDataDirTests(unittest.TestCase):
    def test_windows_keeps_the_historic_userprofile_location(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(paths, "_is_windows", return_value=True), \
                    patch.object(paths.Path, "home", return_value=Path(home)):
                self.assertEqual(paths.user_data_dir(), Path(home) / ".redaction_tool")
                self.assertEqual(paths.presets_dir(),
                                 Path(home) / ".redaction_tool" / "presets")
                self.assertEqual(paths.settings_path(),
                                 Path(home) / ".redaction_tool" / "settings.json")

    def test_linux_uses_xdg_config_home(self):
        with tempfile.TemporaryDirectory() as home, \
                tempfile.TemporaryDirectory() as xdg:
            env = {"XDG_CONFIG_HOME": xdg}
            with patch.object(paths, "_is_windows", return_value=False), \
                    patch.object(paths.Path, "home", return_value=Path(home)), \
                    patch.dict(os.environ, env, clear=False):
                self.assertEqual(paths.user_data_dir(),
                                 Path(xdg) / paths.APP_DIR_NAME)

    def test_linux_defaults_to_dot_config_when_xdg_is_unset(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(paths, "_is_windows", return_value=False), \
                    patch.object(paths.Path, "home", return_value=Path(home)), \
                    patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=False):
                self.assertEqual(paths.user_data_dir(),
                                 Path(home) / ".config" / paths.APP_DIR_NAME)

    def test_relative_xdg_config_home_is_ignored(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.object(paths, "_is_windows", return_value=False), \
                    patch.object(paths.Path, "home", return_value=Path(home)), \
                    patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative/dir"}, clear=False):
                self.assertEqual(paths.user_data_dir(),
                                 Path(home) / ".config" / paths.APP_DIR_NAME)

    def test_existing_legacy_directory_wins_over_a_new_xdg_location(self):
        """Source users who already have ~/.redaction_tool keep their presets."""
        with tempfile.TemporaryDirectory() as home:
            legacy = Path(home) / ".redaction_tool"
            (legacy / "presets").mkdir(parents=True)
            with patch.object(paths, "_is_windows", return_value=False), \
                    patch.object(paths.Path, "home", return_value=Path(home)), \
                    patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=False):
                self.assertEqual(paths.user_data_dir(), legacy)

    def test_xdg_location_wins_once_it_exists(self):
        with tempfile.TemporaryDirectory() as home:
            legacy = Path(home) / ".redaction_tool"
            (legacy / "presets").mkdir(parents=True)
            xdg_dir = Path(home) / ".config" / paths.APP_DIR_NAME
            xdg_dir.mkdir(parents=True)
            with patch.object(paths, "_is_windows", return_value=False), \
                    patch.object(paths.Path, "home", return_value=Path(home)), \
                    patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=False):
                self.assertEqual(paths.user_data_dir(), xdg_dir)

    def test_presets_module_reads_and_writes_in_the_resolved_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            presets_dir = Path(tmp) / "presets"
            with patch.object(paths, "user_data_dir", return_value=Path(tmp)):
                saved = presets.save_preset("Linux Migration", ["ssn"])
                self.assertEqual(saved, presets_dir / "Linux Migration.json")
                self.assertEqual(presets.load_presets()["Linux Migration"], ["ssn"])
                self.assertTrue(presets.delete_preset("Linux Migration"))


class TesseractDiscoveryTests(unittest.TestCase):
    def _fake_tessdata(self, root: Path, *, with_tsv: bool) -> Path:
        data = root / "tessdata"
        data.mkdir(parents=True)
        (data / "eng.traineddata").write_bytes(b"stub")
        if with_tsv:
            (data / "configs").mkdir()
            (data / "configs" / "tsv").write_text("tessedit_create_tsv 1")
        return data

    def test_linux_share_tessdata_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fake_tessdata(Path(tmp), with_tsv=True)
            with patch.object(ocr, "find_tesseract", return_value=None), \
                    patch.object(ocr, "TESSDATA_DIRS", (str(data),)):
                self.assertEqual(ocr.find_tessdata(), data)

    def test_tessdata_without_the_tsv_config_is_still_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fake_tessdata(Path(tmp), with_tsv=False)
            with patch.object(ocr, "find_tesseract", return_value=None), \
                    patch.object(ocr, "TESSDATA_DIRS", (str(data),)):
                self.assertEqual(ocr.find_tessdata(), data)

    def test_tessdata_dir_is_read_from_the_tesseract_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fake_tessdata(Path(tmp), with_tsv=True)
            output = f'List of available languages in "{data}/" (2):\neng\n'
            completed = type("R", (), {"stdout": output, "stderr": "", "returncode": 0})()
            with patch.object(ocr, "TESSDATA_DIRS", ()), \
                    patch.object(ocr.subprocess, "run", return_value=completed):
                self.assertEqual(ocr.find_tessdata("/usr/bin/tesseract"), data)

    def test_env_prefix_pointing_at_the_parent_of_tessdata_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fake_tessdata(Path(tmp), with_tsv=True)
            with patch.object(ocr, "find_tesseract", return_value=None), \
                    patch.object(ocr, "TESSDATA_DIRS", ()), \
                    patch.dict(os.environ, {"TESSDATA_PREFIX": tmp}, clear=False):
                self.assertEqual(ocr.find_tessdata(), data)

    def test_bundled_posix_executable_name_is_probed(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "tesseract"
            exe.write_bytes(b"stub")
            exe.chmod(0o755)
            with patch.object(ocr, "_bundled_tesseract_paths",
                              return_value=[str(exe)]):
                self.assertEqual(ocr.find_tesseract(), str(exe))

    def test_run_ocr_skips_the_missing_tsv_config_file(self):
        """The tsv setting is passed with -c when the config file is absent."""
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fake_tessdata(Path(tmp), with_tsv=False)
            image = Path(tmp) / "page.png"
            image.write_bytes(b"not a real png")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                return type("R", (), {
                    "stdout": "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
                              "left\ttop\twidth\theight\tconf\ttext\n",
                    "stderr": "",
                    "returncode": 0,
                })()

            with patch.object(ocr, "find_tessdata", return_value=data), \
                    patch.object(ocr, "find_tesseract", return_value="/usr/bin/tesseract"), \
                    patch.object(ocr.subprocess, "run", side_effect=fake_run):
                ocr.run_ocr(image)
            self.assertEqual(calls[0][-2:], ["-c", "tessedit_create_tsv=1"])

    def test_run_ocr_uses_the_tsv_config_when_it_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fake_tessdata(Path(tmp), with_tsv=True)
            image = Path(tmp) / "page.png"
            image.write_bytes(b"not a real png")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                return type("R", (), {
                    "stdout": "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
                              "left\ttop\twidth\theight\tconf\ttext\n",
                    "stderr": "",
                    "returncode": 0,
                })()

            with patch.object(ocr, "find_tessdata", return_value=data), \
                    patch.object(ocr, "find_tesseract", return_value="/usr/bin/tesseract"), \
                    patch.object(ocr.subprocess, "run", side_effect=fake_run):
                ocr.run_ocr(image)
            self.assertEqual(calls[0][-1], "tsv")


if __name__ == "__main__":
    unittest.main(verbosity=2)
