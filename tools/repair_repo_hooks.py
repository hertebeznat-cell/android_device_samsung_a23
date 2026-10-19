#!/usr/bin/env python3
"""Restore repo's shared hook directory links without resetting any checkout.

Only .repo metadata is changed. Old hook directories/links are backed up;
missing custom hooks are retained, and conflicting active hooks stop the repair.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import uuid


def inside(path, parent):
    path = Path(path).resolve()
    path.relative_to(parent)
    return path


def plan(root, projects):
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
        if not gitdir.is_dir() or not (objdir / 'config').is_file() or not (objdir / 'objects').is_dir():
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
    report = repair(args.root, load_projects(args.root), apply=args.apply)
    print('REPO_HOOK_REPAIR=' + json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print('BUILD_STATUS=FAILED stage=repo-hook-repair reason=' + str(error), file=sys.stderr)
        sys.exit(1)
