# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One Burger pin source, readable mismatches and Isaac 6.0.1 tolerance.

Unit/API checks on copies of the tracked public files only; no Isaac, network
or Windows run. The checkout's own asset bytes are only read, never changed.
"""
from hashlib import sha256
from io import BytesIO
from itertools import combinations
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))

from twinpulse_app import room_recipe
from twinpulse_app.api import _sanitize_supervisor_status
from twinpulse_app.project_catalog import ProjectCatalog
from twinpulse_app.project_store import ProjectStore
from twinpulse_app.simulation_assets import (
    BURGER_MANIFEST, PUBLIC_ASSET_RELATIVE, PUBLIC_BURGER_MANIFEST, _inventory,
    digest_mismatch_detail, verify_public_burger_assets)
from twinpulse_app.startup_checks import REVIEWED_ISAAC_VERSION, file_checklist, package_checklist

PUBLIC = ROOT / PUBLIC_ASSET_RELATIVE
CODE = 'SIM_BURGER_ASSET_DIGEST_MISMATCH: '
NEITHER = ' (matches neither the public nor the original pins)'
REVIEWED = '6.0.1-rc.7+release.42383.32955d8d.gl'


def digests(folder):
    return {p.relative_to(folder).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


class BurgerPinTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.copy = self.root / PUBLIC_ASSET_RELATIVE
        shutil.copytree(PUBLIC, self.copy)

    def burger_row(self):
        return next(r for r in package_checklist(self.root) if r['id'] == 'burger_asset_manifest')

    def test_clean_checkout_public_folder_verifies_and_enables_project_visual(self):
        before = digests(PUBLIC)
        self.assertEqual(before, PUBLIC_BURGER_MANIFEST)
        self.assertEqual(verify_public_burger_assets(self.copy), PUBLIC_BURGER_MANIFEST)
        self.assertEqual(verify_public_burger_assets(str(self.copy)), PUBLIC_BURGER_MANIFEST)
        self.assertEqual(_inventory(self.copy), PUBLIC_BURGER_MANIFEST)
        self.assertEqual(room_recipe._checked_burger_files(self.copy), PUBLIC_BURGER_MANIFEST)
        self.assertTrue(ProjectCatalog._burger_visual_available())
        row = self.burger_row()
        self.assertEqual(row['state'], 'ready');self.assertIsNone(row['action'])
        self.assertEqual(digests(PUBLIC), before)

    def test_manual_room_with_burger_visual_pins_public_bytes(self):
        buffer = BytesIO();Image.new('RGB', (8, 8), 'red').save(buffer, format='PNG')
        state = self.root / 'state';state.mkdir()
        result = ProjectCatalog(state, 'default').create_from_manual_room(
            'with_burger', prompt='My room; dimensions entered by user', photo=buffer.getvalue(),
            media_type='image/png', width_m=3.2, length_m=4.4, wall_height_m=2.4,
            include_burger_visual=True, request_id=str(uuid4()))
        self.assertTrue(result['burger_visual_included'])
        draft = ProjectStore.for_project(state, 'with_burger').load().site_draft
        manifest, assets = room_recipe.load_project_room_visual(state, 'with_burger', draft)
        self.assertEqual(manifest['asset_files_sha256'], PUBLIC_BURGER_MANIFEST)
        self.assertFalse(manifest['execution_authority'])
        self.assertEqual(digests(assets), PUBLIC_BURGER_MANIFEST)

    def test_modified_byte_names_that_file_and_is_not_repaired(self):
        target = self.copy / 'payloads/base.usda'
        changed = bytearray(target.read_bytes());changed[0] ^= 1;target.write_bytes(bytes(changed))
        expected = CODE + 'payloads/base.usda' + NEITHER
        for check in (_inventory, verify_public_burger_assets):
            with self.assertRaises(ValueError) as caught:check(self.copy)
            self.assertEqual(str(caught.exception), expected)
        with self.assertRaises(ValueError) as caught:room_recipe._checked_burger_files(self.copy)
        self.assertEqual(str(caught.exception), 'project Burger asset hash changed: payloads/base.usda' + NEITHER)
        row = self.burger_row()
        self.assertEqual((row['state'], row['detail']), ('needs_action', expected))
        self.assertIn('re-extract or reinstall', row['action'])
        shown = _sanitize_supervisor_status({'status': 'running', 'startup_checks': [row]})['startup_checks']
        self.assertEqual(shown[0]['detail'], expected)
        self.assertEqual(target.read_bytes(), bytes(changed))

    def test_crlf_copy_names_the_changed_text_files(self):
        for path in self.copy.rglob('*.usda'):
            path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        expected = CODE + 'turtlebot3_burger.usda, payloads/base.usda and 6 more (match neither the public nor the original pins)'
        with self.assertRaises(ValueError) as caught:_inventory(self.copy)
        self.assertEqual(str(caught.exception), expected)
        self.assertEqual(self.burger_row()['detail'], expected)
        with self.assertRaisesRegex(ValueError, 'hash changed: turtlebot3_burger.usda, payloads/base.usda and 6 more'):
            room_recipe._checked_burger_files(self.copy)

    def test_original_pins_still_accepted_but_not_as_the_public_build_input(self):
        target = self.copy / 'payloads/robot.usda'
        target.write_bytes(target.read_bytes() + b'\n')
        original = digests(self.copy)
        with patch.dict(BURGER_MANIFEST, original, clear=True):
            self.assertEqual(_inventory(self.copy), original)
            self.assertEqual(room_recipe._checked_burger_files(self.copy), original)
            self.assertEqual(self.burger_row()['state'], 'ready')
            with self.assertRaises(ValueError) as caught:verify_public_burger_assets(self.copy)
            self.assertEqual(str(caught.exception), CODE + 'payloads/robot.usda (matches the original pins, not the public pins)')
        with self.assertRaises(ValueError) as caught:verify_public_burger_assets(self.copy)
        self.assertEqual(str(caught.exception), CODE + 'payloads/robot.usda' + NEITHER)
        with patch('twinpulse_app.simulation_assets._inventory', return_value=dict(BURGER_MANIFEST)):
            with self.assertRaisesRegex(ValueError, r': turtlebot3_burger\.usda, payloads/base\.usda and 7 more '
                                                    r'\(match the original pins, not the public pins\)\Z'):
                verify_public_burger_assets(self.copy)

    def test_mixed_public_and_original_files_are_refused_by_name(self):
        base, robot = self.copy / 'payloads/base.usda', self.copy / 'payloads/robot.usda'
        original = dict(PUBLIC_BURGER_MANIFEST,
                        **{'payloads/base.usda': sha256(base.read_bytes() + b'\n').hexdigest(),
                           'payloads/robot.usda': sha256(robot.read_bytes() + b'\n').hexdigest()})
        base.write_bytes(base.read_bytes() + b'\n')
        with patch.dict(BURGER_MANIFEST, original, clear=True):
            expected = CODE + 'payloads/base.usda (mixes public and original pins)'
            for check in (_inventory, verify_public_burger_assets):
                with self.assertRaises(ValueError) as caught:check(self.copy)
                self.assertEqual(str(caught.exception), expected)
            with self.assertRaisesRegex(ValueError, r'hash changed: payloads/base\.usda \(mixes'):
                room_recipe._checked_burger_files(self.copy)

    def test_every_changed_subset_is_named_within_ui_truncation(self):
        names = list(PUBLIC_BURGER_MANIFEST)
        longest = ''
        for count in range(1, len(names) + 1):
            for changed in combinations(names, count):
                unpinned = dict(PUBLIC_BURGER_MANIFEST, **{name: '0' * 64 for name in changed})
                mixed = dict(PUBLIC_BURGER_MANIFEST, **{name: BURGER_MANIFEST[name] for name in changed})
                for inventory, minority in ((unpinned, changed), (mixed, changed if 2 * count <= len(names)
                                            else [n for n in names if n not in changed])):
                    if inventory == BURGER_MANIFEST:
                        continue
                    message = CODE + digest_mismatch_detail(inventory)
                    shown = message[len(CODE):].split(' (')[0].split(' and ')[0].split(', ')
                    self.assertTrue(set(shown) <= set(minority), message)
                    self.assertEqual(len(shown), min(2, len(minority)), message)
                    if len(minority) > 2:
                        self.assertIn(f' and {len(minority) - 2} more (', message)
                    self.assertEqual(message.split(':', 1)[0], 'SIM_BURGER_ASSET_DIGEST_MISMATCH')
                    longest = max(longest, message, key=len)
        # goal_scene_rejected keeps 160 characters, the checklist API 240.
        self.assertLessEqual(len(longest), 160, longest)
        with patch('twinpulse_app.simulation_assets._inventory', side_effect=ValueError(longest)):
            self.assertEqual(self.burger_row()['detail'], longest)

    def test_other_errors_keep_bare_codes_and_paths_stay_hidden(self):
        (self.copy / 'payloads/robot.usda').unlink()
        self.assertEqual(self.burger_row()['detail'], 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED')
        # Only the fixed Burger file names may follow the code: no path, user name or token.
        for text in ('SIM_BURGER_ASSET_DIGEST_MISMATCH: /home/user/private.usda', 'C:\\Users\\name\\x.usda',
                     CODE + 'Users/alice/AppData/Local/x.usda' + NEITHER, CODE + 'payloads/base.usda, alice' + NEITHER,
                     CODE + 'sk-abc123 Bearer abc123'):
            with patch('twinpulse_app.simulation_assets._inventory', side_effect=ValueError(text)):
                self.assertEqual(self.burger_row()['detail'], 'ValueError')
        # Other rows still show bare codes only, never free text after a code.
        with patch('twinpulse_app.startup_checks._extension_contract',
                   side_effect=ValueError('EXTENSION_CONTRACT_INVALID: alice typed this (see notes)')):
            row = next(r for r in package_checklist(self.root) if r['id'] == 'extension_contract')
        self.assertEqual((row['state'], row['detail']), ('needs_action', 'ValueError'))


class FileManagerMetadataTests(unittest.TestCase):
    """desktop.ini, Thumbs.db and .DS_Store are ignored in the Burger folder; nothing else is."""
    def setUp(self):
        temporary = TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.copy = self.root / PUBLIC_ASSET_RELATIVE
        shutil.copytree(PUBLIC, self.copy)
        # Each folder of the closure, in the letter case Explorer or Finder writes and in two others.
        self.metadata = [self.copy / folder / name for folder, names in (
            ('', ('desktop.ini', 'Thumbs.db', '.DS_Store')), ('payloads', ('Desktop.ini', 'thumbs.db', '.ds_store')),
            ('payloads/Physics', ('DESKTOP.INI', 'THUMBS.DB', '.DS_STORE'))) for name in names]
        for path in self.metadata:
            path.write_bytes(b'[.ShellClassInfo]\r\n')

    def burger_row(self):
        return next(r for r in package_checklist(self.root) if r['id'] == 'burger_asset_manifest')

    def test_every_burger_check_accepts_the_folder_and_never_reads_the_metadata(self):
        # Never read, so an oversized metadata file does not meet the per-file size limit either.
        with (self.copy / 'payloads/thumbs.db').open('r+b') as stream:
            stream.truncate(33 * 1024 * 1024)
        self.assertEqual(_inventory(self.copy), PUBLIC_BURGER_MANIFEST)
        self.assertEqual(verify_public_burger_assets(self.copy), PUBLIC_BURGER_MANIFEST)
        self.assertEqual(room_recipe._checked_burger_files(self.copy), PUBLIC_BURGER_MANIFEST)
        row = self.burger_row()
        self.assertEqual((row['state'], row['action']), ('ready', None))
        with patch('twinpulse_app.bedroom_review.ROOT', self.root):
            self.assertTrue(ProjectCatalog._burger_visual_available())
        self.assertTrue(all(path.is_file() for path in self.metadata))  # skipped, not removed

    def test_any_other_extra_file_or_a_missing_file_is_still_refused_with_the_same_code(self):
        closure = 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED'
        for extra in ('desktop.ini.bak', 'payloads/ehthumbs.db', 'payloads/._base.usda', 'payloads/notes.txt',
                      'materials/Thumbs.db/base.usda'):  # the last one: a file in a folder named like metadata
            with self.subTest(extra=extra):
                path = self.copy / extra
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'x')
                with self.assertRaises(ValueError) as caught:_inventory(self.copy)
                self.assertEqual(str(caught.exception), closure)
                with self.assertRaisesRegex(ValueError, r'\Aproject Burger asset files are missing, extra or linked\Z'):
                    room_recipe._checked_burger_files(self.copy)
                self.assertEqual(self.burger_row()['detail'], closure)
                path.unlink()
        self.assertEqual(_inventory(self.copy), PUBLIC_BURGER_MANIFEST)  # each refusal above was that one file
        (self.copy / 'payloads/Physics/mujoco.usda').unlink()  # metadata never stands in for a pinned file
        with self.assertRaises(ValueError) as caught:_inventory(self.copy)
        self.assertEqual(str(caught.exception), closure)
        with self.assertRaisesRegex(ValueError, r'\Aproject Burger asset files are missing, extra or linked\Z'):
            room_recipe._checked_burger_files(self.copy)

    def test_a_link_is_refused_even_under_a_metadata_name(self):
        link = self.metadata[0]  # desktop.ini, pointing at a pinned file inside the folder
        link.unlink()
        try:
            link.symlink_to(self.copy / 'turtlebot3_burger.usda')
        except (OSError, NotImplementedError):
            self.skipTest('symbolic links are not available to this user')
        with self.assertRaises(ValueError) as caught:_inventory(self.copy)
        self.assertEqual(str(caught.exception), 'SIM_ASSET_DEPENDENCY_UNSAFE')
        with self.assertRaisesRegex(ValueError, r'\Aproject Burger asset files are missing, extra or linked\Z'):
            room_recipe._checked_burger_files(self.copy)
        self.assertEqual(self.burger_row()['detail'], 'SIM_ASSET_DEPENDENCY_UNSAFE')

    def test_a_project_copy_carries_only_the_pinned_files_and_later_metadata_is_skipped(self):
        buffer = BytesIO();Image.new('RGB', (8, 8), 'red').save(buffer, format='PNG')
        state = self.root / 'state';state.mkdir()
        with patch('twinpulse_app.bedroom_review.ROOT', self.root):  # the copy above is the bundled source
            result = ProjectCatalog(state, 'default').create_from_manual_room(
                'with_burger', prompt='My room; dimensions entered by user', photo=buffer.getvalue(),
                media_type='image/png', width_m=3.2, length_m=4.4, wall_height_m=2.4,
                include_burger_visual=True, request_id=str(uuid4()))
        self.assertTrue(result['burger_visual_included'])
        draft = ProjectStore.for_project(state, 'with_burger').load().site_draft
        manifest, assets = room_recipe.load_project_room_visual(state, 'with_burger', draft)
        self.assertEqual(digests(assets), PUBLIC_BURGER_MANIFEST)  # no metadata file was copied
        self.assertEqual(manifest['asset_files_sha256'], PUBLIC_BURGER_MANIFEST)
        # Explorer may write its metadata into the project's copy later: skipped too. Any other file is not.
        (assets / 'payloads/desktop.ini').write_bytes(b'[.ShellClassInfo]\r\n')
        self.assertEqual(room_recipe.load_project_room_visual(state, 'with_burger', draft), (manifest, assets))
        (assets / 'payloads/notes.txt').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'missing, extra or linked'):
            room_recipe.load_project_room_visual(state, 'with_burger', draft)


class IsaacVersionTests(unittest.TestCase):
    def row(self, text, *, raw=None):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'VERSION').write_bytes(raw if raw is not None else text.encode('utf-8'))
            rows = file_checklist({}, state_dir=folder, isaac_python=folder / 'python.bat')
        return next(r for r in rows if r['id'] == 'isaac_version')

    def test_reviewed_build_and_other_6_0_1_builds_are_ready(self):
        self.assertEqual(REVIEWED_ISAAC_VERSION, REVIEWED)  # the one constant other checks compare with
        exact = self.row(REVIEWED)
        self.assertEqual(exact['state'], 'ready');self.assertIn('Matches the reviewed local runtime.', exact['detail'])
        for text in ('6.0.1', '6.0.1+release.51234.0a1b2c3d.gl', '6.0.1-rc.9+release.43000.32955d8d.gl'):
            with self.subTest(text=text):
                row = self.row(text)
                self.assertEqual((row['state'], row['action']), ('ready', None))
                self.assertIn(f'Observed Isaac version: {text}.', row['detail'])
                self.assertIn(REVIEWED, row['detail'])
        bom = self.row(None, raw=b'\xef\xbb\xbf' + REVIEWED.encode() + b'\r\n')
        self.assertEqual((bom['state'], bom['detail']), ('ready', exact['detail']))

    def test_other_versions_stay_a_non_blocking_warning(self):
        for text in ('6.1.0', '6.0.10', '6.0.11-rc.1', '6.0.1x', '5.1.0-rc.19+release.1.abcdef.gl', 'unknown-version'):
            with self.subTest(text=text):
                row = self.row(text)
                self.assertEqual(row['state'], 'needs_action')
                self.assertIn('not been qualified', row['detail']);self.assertIn('6.0.1', row['action'])
        with TemporaryDirectory() as directory:
            rows = file_checklist({}, state_dir=Path(directory), isaac_python=Path(directory) / 'python.bat')
        self.assertEqual(next(r for r in rows if r['id'] == 'isaac_version')['state'], 'needs_action')


if __name__ == '__main__':
    unittest.main()
