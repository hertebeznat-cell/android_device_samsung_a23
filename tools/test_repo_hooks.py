"""Small metadata fixtures only; no source downloads, sync or compiler.

Windows uses native directory junctions to exercise real directory references
without requiring symlink privilege. The production CLI applies only on Linux.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from repair_repo_hooks import plan, repair


@contextmanager
def directory_links():
    if os.name != 'nt':
        yield
        return
    import _winapi

    def junction(path, target, target_is_directory=False):
        target = Path(target)
        if not target.is_absolute():
            target = path.parent / target
        _winapi.CreateJunction(str(target.resolve()), str(path))

    with patch.object(Path, 'symlink_to', junction):
        yield


class RepoHookTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[4]
        self.temporary = tempfile.TemporaryDirectory(prefix='.repo-hook-test-', dir=workspace)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / '.repo'
        self.repo.mkdir()
        (self.repo / 'manifest.xml').write_text('<manifest/>')
        self.project = self.make_project('frameworks/base', 'frameworks_base')
        self.destination = Path(self.project.gitdir) / 'hooks'
        self.canonical = Path(self.project.objdir) / 'hooks'
        self.destination.mkdir()
        self.canonical.mkdir()
        for directory in (self.destination, self.canonical):
            (directory / 'commit-msg').write_bytes(b'#!/bin/sh\nexit 0\n')
        self.sentinels = {}
        for name in ('.repo/projects/frameworks/base.git/HEAD',
                     '.repo/projects/frameworks/base.git/index',
                     '.repo/project-objects/frameworks_base.git/objects/keep',
                     'frameworks/base/keep', 'out/keep'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(('original ' + name).encode())
            self.sentinels[target] = target.read_bytes()

    def make_project(self, path, name):
        gitdir = self.repo / 'projects' / (path + '.git')
        objdir = self.repo / 'project-objects' / (name + '.git')
        gitdir.mkdir(parents=True)
        (objdir / 'objects').mkdir(parents=True)
        (objdir / 'config').write_text('[core]\n bare = true\n')
        return SimpleNamespace(gitdir=str(gitdir), objdir=str(objdir), use_git_worktrees=False)

    def assert_sources_preserved(self):
        for path, expected in self.sentinels.items():
            self.assertEqual(path.read_bytes(), expected)

    def apply(self, projects=None):
        with directory_links():
            return repair(self.root, projects or [self.project], apply=True)

    def test_copied_hook_directory_is_backed_up_and_linked_idempotently(self):
        report = self.apply()
        self.assertEqual(report['repaired'], 1)
        self.assertEqual(self.destination.resolve(), self.canonical.resolve())
        old = Path(report['backup_dir']) / self.destination.relative_to(self.repo)
        self.assertEqual((old / 'commit-msg').read_bytes(), b'#!/bin/sh\nexit 0\n')
        self.assert_sources_preserved()
        again = self.apply()
        self.assertEqual(again['planned'], 0)
        self.assertIsNone(again['backup_dir'])

    def test_dry_run_does_not_write_anything(self):
        report = repair(self.root, [self.project])
        self.assertEqual(report['planned'], 1)
        self.assertEqual(report['repaired'], 0)
        self.assertFalse((self.repo / 'a23-hook-backups').exists())
        self.assertNotEqual(self.destination.resolve(), self.canonical.resolve())
        self.assert_sources_preserved()

    def test_missing_custom_hook_remains_active_and_backed_up(self):
        (self.destination / 'post-checkout').write_bytes(b'#!/bin/sh\necho custom\n')
        report = self.apply()
        self.assertEqual((self.canonical / 'post-checkout').read_bytes(), b'#!/bin/sh\necho custom\n')
        old = Path(report['backup_dir']) / self.destination.relative_to(self.repo)
        self.assertEqual((old / 'post-checkout').read_bytes(), (self.canonical / 'post-checkout').read_bytes())
        self.assert_sources_preserved()

    def test_conflicting_hook_stops_all_changes(self):
        second = self.make_project('art', 'art')
        old = Path(second.gitdir) / 'hooks'
        canonical = Path(second.objdir) / 'hooks'
        old.mkdir()
        canonical.mkdir()
        (old / 'commit-msg').write_bytes(b'custom')
        (canonical / 'commit-msg').write_bytes(b'other custom')
        with self.assertRaisesRegex(ValueError, 'Conflicting hook'):
            self.apply([self.project, second])
        self.assertNotEqual(self.destination.resolve(), self.canonical.resolve())
        self.assertFalse((self.repo / 'a23-hook-backups').exists())
        self.assert_sources_preserved()

    def test_conflicting_missing_hooks_for_a_shared_object_store_are_rejected(self):
        second = self.make_project('duplicate', 'unused')
        second.objdir = self.project.objdir
        old = Path(second.gitdir) / 'hooks'
        old.mkdir()
        (self.destination / 'post-checkout').write_bytes(b'first custom hook')
        (old / 'post-checkout').write_bytes(b'second custom hook')
        with self.assertRaisesRegex(ValueError, 'Conflicting shared hook'):
            self.apply([self.project, second])
        self.assertFalse((self.repo / 'a23-hook-backups').exists())
        self.assertFalse((self.canonical / 'post-checkout').exists())

    def test_different_inactive_samples_are_preserved_in_backup(self):
        (self.destination / 'pre-commit.sample').write_bytes(b'old Git template')
        (self.canonical / 'pre-commit.sample').write_bytes(b'new Git template')
        report = self.apply()
        old = Path(report['backup_dir']) / self.destination.relative_to(self.repo)
        self.assertEqual((old / 'pre-commit.sample').read_bytes(), b'old Git template')
        self.assertEqual((self.canonical / 'pre-commit.sample').read_bytes(), b'new Git template')

    def test_missing_hook_directory_is_created_as_a_reference(self):
        (self.destination / 'commit-msg').unlink()
        self.destination.rmdir()
        self.assertEqual(self.apply()['repaired'], 1)
        self.assertEqual(self.destination.resolve(), self.canonical.resolve())
        self.assert_sources_preserved()

    def test_other_internal_hook_reference_is_replaced_without_changing_target(self):
        other = self.repo / 'old-hooks'
        self.destination.rename(other)
        with directory_links():
            self.destination.symlink_to(other, target_is_directory=True)
            report = repair(self.root, [self.project], apply=True)
        self.assertEqual(report['repaired'], 1)
        self.assertEqual(self.destination.resolve(), self.canonical.resolve())
        self.assertEqual((other / 'commit-msg').read_bytes(), b'#!/bin/sh\nexit 0\n')

    def test_external_hook_reference_is_rejected_without_touching_it(self):
        outside = self.root / 'outside-metadata'
        self.destination.rename(outside)
        with directory_links():
            self.destination.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                repair(self.root, [self.project], apply=True)
        self.assertEqual((outside / 'commit-msg').read_bytes(), b'#!/bin/sh\nexit 0\n')
        self.assertFalse((self.repo / 'a23-hook-backups').exists())

    def test_symlink_failure_preserves_original_directory(self):
        with patch.object(Path, 'symlink_to', side_effect=PermissionError('fixture refusal')):
            with self.assertRaises(PermissionError):
                repair(self.root, [self.project], apply=True)
        self.assertEqual((self.destination / 'commit-msg').read_bytes(), b'#!/bin/sh\nexit 0\n')
        self.assertNotEqual(self.destination.resolve(), self.canonical.resolve())
        self.assert_sources_preserved()

    def test_new_project_does_not_create_a_partial_object_repository(self):
        new = SimpleNamespace(gitdir=str(self.repo / 'projects/new.git'),
                              objdir=str(self.repo / 'project-objects/new.git'),
                              use_git_worktrees=False)
        report = self.apply([new])
        self.assertEqual(report['skipped'], 1)
        self.assertEqual(report['planned'], 0)
        self.assertFalse(Path(new.objdir).exists())

    def test_git_worktrees_are_left_to_repo(self):
        self.project.use_git_worktrees = True
        report = self.apply()
        self.assertEqual(report['skipped'], 1)
        self.assertFalse((self.repo / 'a23-hook-backups').exists())

    def test_paths_outside_metadata_are_rejected(self):
        self.project.objdir = str(self.root / 'not-repo-metadata')
        with self.assertRaises(ValueError):
            plan(self.root, [self.project])
        self.assert_sources_preserved()


if __name__ == '__main__':
    unittest.main()
