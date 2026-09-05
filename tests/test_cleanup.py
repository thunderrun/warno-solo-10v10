import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from fixtures import profile
from profile_codec import repair

@unittest.skipUnless(sys.platform=='win32','Windows process APIs')
class FileRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Only synthetic paths are loaded; tests never attach to a process.
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/'test-config.json'
            config.write_text(json.dumps({
                'game_exe':str(Path(temp)/'WARNO.exe'),
                'profile':str(Path(temp)/'PROFILE.profile2'),
                'python_exe':sys.executable,
            }))
            with patch.dict(os.environ,{'WARNO10V10_CONFIG':str(config)}):
                cls.cleanup=importlib.import_module('profile_cleanup')

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.path=self.root/'PROFILE.profile2'
        self.original=profile()
        self.path.write_bytes(self.original)
        self.backups=self.root/'backups'
        for name,value in [('backup_root',lambda:self.backups),('ROOT',self.root)]:
            handle=patch.object(self.cleanup,name,value)
            handle.start();self.addCleanup(handle.stop)

    def test_backup_and_repaired_file_are_verified(self):
        with patch.object(self.cleanup,'game_running',return_value=False):
            result=self.cleanup.repair_file(self.path)
        self.assertTrue(result['changed'])
        self.assertEqual(Path(result['backup']).read_bytes(),self.original)
        self.assertEqual(self.path.read_bytes(),repair(self.original)[0])
        self.assertTrue((Path(result['backup']).parent/'repair.json').is_file())

    def test_running_game_blocks_all_writes(self):
        with patch.object(self.cleanup,'game_running',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'Close WARNO'):self.cleanup.repair_file(self.path)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertFalse(self.backups.exists())

    def test_game_restarting_before_replacement_is_respected(self):
        with patch.object(self.cleanup,'game_running',side_effect=[False,True]):
            with self.assertRaisesRegex(RuntimeError,'restarted'):self.cleanup.repair_file(self.path)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(list(self.root.glob('*.tmp')),[])

    def test_concurrent_profile_change_is_not_overwritten(self):
        newer=profile(nato=8,pact=8)
        def second_check():
            self.path.write_bytes(newer)
            return False
        checks=iter([lambda:False,second_check])
        with patch.object(self.cleanup,'game_running',side_effect=lambda:next(checks)()):
            with self.assertRaisesRegex(RuntimeError,'changed during repair'):self.cleanup.repair_file(self.path)
        self.assertEqual(self.path.read_bytes(),newer)

    def test_failed_replace_preserves_original_and_backup(self):
        with patch.object(self.cleanup,'game_running',return_value=False),patch.object(self.cleanup.os,'replace',side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):self.cleanup.repair_file(self.path)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(next(self.backups.glob('*/PROFILE.before-cleanup.profile2')).read_bytes(),self.original)
        self.assertEqual(list(self.root.glob('*.tmp')),[])

    def test_vanilla_profile_is_untouched(self):
        vanilla=profile(nato=3,pact=4)
        self.path.write_bytes(vanilla)
        with patch.object(self.cleanup,'game_running',return_value=False):
            self.assertFalse(self.cleanup.repair_file(self.path)['changed'])
        self.assertEqual(self.path.read_bytes(),vanilla)
        self.assertFalse(self.backups.exists())

if __name__=='__main__':unittest.main()
