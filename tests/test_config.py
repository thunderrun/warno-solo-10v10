import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from project_config import load_config

class ConfigurationTests(unittest.TestCase):
    def test_missing_setup_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ,{'WARNO10V10_CONFIG':str(Path(temp)/'missing.json')}):
                with self.assertRaisesRegex(RuntimeError,'Setup.ps1'):load_config()

    def test_relative_paths_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.json'
            path.write_text(json.dumps({'game_exe':'WARNO.exe','profile':'PROFILE.profile2','python_exe':'python.exe'}))
            with patch.dict(os.environ,{'WARNO10V10_CONFIG':str(path)}):
                with self.assertRaisesRegex(ValueError,'game_exe'):load_config()

    def test_absolute_paths_and_powershell_bom(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.json'
            config={key:str(Path(temp)/name) for key,name in [('game_exe','WARNO.exe'),('profile','PROFILE.profile2'),('python_exe','python.exe')]}
            path.write_text(json.dumps(config),encoding='utf-8-sig')
            with patch.dict(os.environ,{'WARNO10V10_CONFIG':str(path)}):
                self.assertEqual(load_config(),config)

if __name__=='__main__':unittest.main()
