#!/usr/bin/env python3
"""Prepare cached repo projects without deleting source files or object stores.

Hook references are repaired with backups. Stale project metadata and its
worktree are moved intact into backups for normal repo reinitialization.
Missing custom hooks are retained; conflicts stop the full plan before writes.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import uuid


def inside(path, parent):
    path = Path(path).resolve()
    path.relative_to(parent)
    return path


def plan(root, projects, allow_uninitialized=False):
    root = Path(root).resolve()
    repo = inside(root / '.repo', root)
    if not (repo / 'manifest.xml').is_file():
        raise ValueError('Expected the existing Android .repo/manifest.xml')
    actions, additions = [], {}
    checked = skipped = 0
    seen = set()
    for project in projects:
        if project.use_git_worktrees:
            skipped += 1
            continue
        gitdir = inside(project.gitdir, repo)
        objdir = inside(project.objdir, repo)
        if gitdir == objdir or gitdir in seen:
            continue
        seen.add(gitdir)
        # New/remapped projects belong to repo's normal initialization. Never
        # create a partially initialized bare repository just to add hooks.
        if not gitdir.is_dir() or (not allow_uninitialized and
                (not (objdir / 'config').is_file() or not (objdir / 'objects').is_dir())):
            skipped += 1
            continue
        checked += 1
        destination = gitdir / 'hooks'
        canonical = inside(objdir / 'hooks', repo)
        if destination.resolve() == canonical:
            continue
        if os.path.lexists(canonical) and not canonical.is_dir():
            raise ValueError(f'Canonical hooks path is not a directory: {canonical}')
        if os.path.lexists(destination):
            # A dangling directory link can be safely replaced without reading
            # its old target. Existing targets must stay inside .repo.
            if destination.exists():
                inside(destination, repo)
                if not destination.is_dir():
                    raise ValueError(f'Unexpected hooks path: {destination}')
                for entry in sorted(destination.iterdir()):
                    # Git sample templates are inactive; retain them in the
                    # backup without conflicting with another Git version.
                    if entry.name.endswith('.sample'):
                        continue
                    inside(entry, repo)
                    if not entry.is_file():
                        raise ValueError(f'Unsupported hook entry; preserved for review: {entry}')
                    target = canonical / entry.name
                    data, mode = entry.read_bytes(), entry.stat().st_mode & 0o777
                    if os.path.lexists(target):
                        inside(target, repo)
                        if not target.is_file() or target.read_bytes() != data or \
                                (mode & 0o111) & ~(target.stat().st_mode & 0o111):
                            raise ValueError(f'Conflicting hook; no repair performed: {entry.name}')
                    elif target in additions:
                        if additions[target] != (data, mode):
                            raise ValueError(f'Conflicting shared hook; no repair performed: {entry.name}')
                    else:
                        additions[target] = (data, mode)
        actions.append((destination, canonical))
    return repo, actions, additions, {'checked': checked, 'skipped': skipped}


def repair(root, projects, apply=False):
    repo, actions, additions, report = plan(root, projects)
    report.update(repaired=0, planned=len(actions), backup_dir=None)
    if not apply or not actions:
        return report
    # Complete validation of every project happens above, before the first write.
    backup_parent = inside(repo / 'a23-hook-backups', repo)
    backup_parent.mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(
        prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=backup_parent))
    report['backup_dir'] = str(backup)
    (backup / 'plan.json').write_text(json.dumps([
        {'path': str(destination.relative_to(repo)), 'target': str(canonical.relative_to(repo))}
        for destination, canonical in actions], indent=2) + '\n', encoding='utf-8')
    for _, canonical in actions:
        canonical.mkdir(parents=True, exist_ok=True)
    for target, (data, mode) in additions.items():
        with target.open('xb') as stream:
            stream.write(data)
        target.chmod(mode)
    for destination, canonical in actions:
        temporary = destination.with_name('.a23-hooks-link-' + uuid.uuid4().hex)
        old = backup / destination.relative_to(repo)
        # Test symlink creation before moving the original. Never remove it.
        temporary.symlink_to(os.path.relpath(canonical, destination.parent), target_is_directory=True)
        moved = False
        try:
            if os.path.lexists(destination):
                old.parent.mkdir(parents=True, exist_ok=True)
                destination.rename(old)
                moved = True
            temporary.replace(destination)
        except OSError:
            if moved and not os.path.lexists(destination):
                old.rename(destination)
            if temporary.is_symlink():
                temporary.unlink()
            raise
        if destination.resolve() != canonical:
            raise RuntimeError(f'Hook link verification failed: {destination}')
        report['repaired'] += 1
    return report


def reinitialization_plan(root, projects):
    """Preserve stale metadata/worktrees before repo initializes a remapped project."""
    root = Path(root).resolve()
    repo = inside(root / '.repo', root)
    pending, seen = [], set()
    for project in projects:
        if project.use_git_worktrees:
            continue
        gitdir, objdir = inside(project.gitdir, repo), inside(project.objdir, repo)
        if gitdir == objdir or gitdir in seen or not gitdir.is_dir():
            continue
        seen.add(gitdir)
        reasons = []
        if not (objdir / 'config').is_file() or not (objdir / 'objects').is_dir():
            reasons.append('desired object repository is not initialized')
        for name in getattr(project, 'shareable_dirs', ('hooks', 'objects', 'rr-cache')):
            if name == 'hooks':
                continue
            current, expected = gitdir / name, objdir / name
            if os.path.lexists(current.resolve()) and current.resolve() != expected.resolve():
                reasons.append(name + ' references another object repository')
        if not reasons:
            continue
        # Never stage an object database, the Android root, runtime or output.
        relative = gitdir.relative_to(repo)
        if 'projects' not in relative.parts or 'project-objects' in relative.parts or gitdir.suffix != '.git':
            raise ValueError(f'Unexpected project metadata path: {gitdir}')
        if 'project-objects' not in objdir.relative_to(repo).parts or objdir.suffix != '.git':
            raise ValueError(f'Unexpected object repository path: {objdir}')
        worktree = inside(project.worktree, root)
        if worktree == root or worktree.is_relative_to(repo) or worktree.is_relative_to(root / 'out'):
            raise ValueError(f'Protected project worktree path: {worktree}')
        if worktree.exists() and not worktree.is_dir():
            raise ValueError(f'Unexpected project worktree: {worktree}')
        references = {name: str((gitdir / name).resolve())
                      for name in getattr(project, 'shareable_dirs', ('hooks', 'objects', 'rr-cache'))}
        pending.append({'gitdir': gitdir, 'objdir': objdir, 'worktree': worktree,
                        'reasons': reasons, 'original_shared_references': references})
    for item in pending:
        for project in projects:
            other = inside(project.worktree, root)
            if other != item['worktree'] and other.is_relative_to(item['worktree']) and other.exists():
                raise ValueError('Stale worktree contains another checkout; preserve and review it')
    return pending


def prepare(root, projects, apply=False):
    projects = list(projects)
    root = Path(root).resolve()
    repo = inside(root / '.repo', root)
    pending = reinitialization_plan(root, projects)
    # Include stale projects in hook validation; do not silently skip them.
    # Only a complete bare init may create their missing canonical directory.
    plan(root, projects, allow_uninitialized=True)
    initialized = []
    if apply:
        for item in pending:
            objdir = item['objdir']
            if (objdir / 'config').is_file() and (objdir / 'objects').is_dir():
                continue
            for name in ('config', 'HEAD', 'refs', 'objects'):
                if os.path.lexists(objdir / name):
                    inside(objdir / name, repo)
            environment = os.environ.copy()
            for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
                         'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
                environment.pop(name, None)
            result = subprocess.run(['git', '-c', 'init.defaultBranch=main', 'init', '--bare',
                                     '--template=', '--object-format=sha1', '--quiet', str(objdir)], env=environment,
                                    capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(f'Bare repository initialization failed: {objdir}: {result.stderr}')
            initialized.append(str(objdir.relative_to(repo)))
    # Retain custom hooks in the canonical store before staging old metadata.
    report = repair(root, projects, apply=apply)
    backup = None
    if apply and pending:
        parent = inside(repo / 'a23-project-backups', repo)
        parent.mkdir(exist_ok=True)
        backup = Path(tempfile.mkdtemp(
            prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=parent))
        (backup / 'plan.json').write_text(json.dumps([
            {'gitdir': str(item['gitdir'].relative_to(root)),
             'worktree': str(item['worktree'].relative_to(root)), 'reasons': item['reasons'],
             'original_shared_references': item['original_shared_references']}
            for item in pending], indent=2) + '\n', encoding='utf-8')
        for item in pending:
            for key, category in (('worktree', 'worktrees'), ('gitdir', 'metadata')):
                original = item[key]
                if not os.path.lexists(original):
                    continue
                saved = backup / category / original.relative_to(root)
                saved.parent.mkdir(parents=True, exist_ok=True)
                original.rename(saved)
    report['object_repositories_initialized'] = initialized
    report['project_backup_dir'] = str(backup) if backup else None
    report['projects_staged_for_reinit'] = len(pending) if apply else 0
    report['reinitialization_plan'] = [
        {'path': str(item['worktree'].relative_to(root)), 'reasons': item['reasons']}
        for item in pending]
    return report


def load_projects(root):
    root = Path(root).resolve()
    repo = inside(root / '.repo', root)
    runtime = inside(repo / 'repo', repo)
    if not (runtime / 'manifest_xml.py').is_file():
        raise ValueError('The existing repo runtime is unavailable')
    sys.path.insert(0, str(runtime))
    from manifest_xml import RepoClient
    return RepoClient(str(repo)).all_projects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply and (platform.system() != 'Linux' or
                       'microsoft' in platform.release().lower() or
                       os.environ.get('A23_REMOTE_BUILD') != '1'):
        parser.error('--apply is only for the designated Linux build server')
    report = prepare(args.root, load_projects(args.root), apply=args.apply)
    print('REPO_HOOK_REPAIR=' + json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print('BUILD_STATUS=FAILED stage=repo-hook-repair reason=' + str(error), file=sys.stderr)
        sys.exit(1)
