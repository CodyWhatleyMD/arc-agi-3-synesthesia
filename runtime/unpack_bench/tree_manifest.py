#!/usr/bin/env python3
"""Canonical manifests of an extracted runtime tree, and of what the layer archives say that tree must hold.

  manifest <root> <out.tsv>                          walk an extracted tree (run as root, as the harness does)
  expected <members_l8.json> <members_l100.json> <out.tsv>   the tree tar must produce from those archives, in order
  diff <a.tsv> <b.tsv>                               mismatches by kind, with examples

A manifest has two sections. CORE covers every entry except the root: path, kind (f, d, l), mode (st_mode & 0o7777),
uid, gid, size, mtime in whole seconds, symlink target, sha256 and hard-link group. Directories leave out their
mtime, and a symlink's size is its target. DIRMTIME holds directory mtimes, kept apart because parallel tars change
a directory's mtime after its owner has set it, and nothing in the runtime reads it (.pyc checks use file mtimes).
The summary JSON gives one sha256 per section, so two trees can be compared by digest.

The expected tree follows what GNU tar does as root with --no-same-owner: owner 0:0, archive modes, archive mtimes.
A later layer's entry replaces an earlier one, a hard link takes its target's inode, and a symlink lstat's as 0777.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CHUNK = 1 << 22
THREADS = int(os.environ.get('MANIFEST_THREADS', '4'))


def sha256_path(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(rows: dict[str, tuple], dir_mtimes: dict[str, int], out: str) -> dict:
    core = hashlib.sha256()
    dirs = hashlib.sha256()
    counts: dict[str, int] = {}
    with open(out, 'w') as handle:
        handle.write('#CORE\n')
        for path in sorted(rows):
            line = '\t'.join([path, *map(str, rows[path])]) + '\n'
            core.update(line.encode('utf-8', 'surrogateescape'))
            handle.write(line)
            counts[rows[path][0]] = counts.get(rows[path][0], 0) + 1
        handle.write('#DIRMTIME\n')
        for path in sorted(dir_mtimes):
            line = f'{path}\t{dir_mtimes[path]}\n'
            dirs.update(line.encode('utf-8', 'surrogateescape'))
            handle.write(line)
    return {'manifest': out, 'entries': len(rows), 'counts': counts, 'core_sha256': core.hexdigest(),
            'dirmtime_sha256': dirs.hexdigest()}


def cmd_manifest(root: str, out: str) -> None:
    entries = []
    for current, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            full = os.path.join(current, name)
            entries.append((os.path.relpath(full, root), full, os.lstat(full)))
    regular = [full for _, full, info in entries if stat.S_ISREG(info.st_mode)]
    with ThreadPoolExecutor(THREADS) as pool:
        digests = dict(zip(regular, pool.map(sha256_path, regular)))
    groups: dict[tuple, list[str]] = {}
    for rel, _, info in entries:
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            groups.setdefault((info.st_dev, info.st_ino), []).append(rel)
    group_of = {rel: min(paths) for paths in groups.values() for rel in paths}
    rows, dir_mtimes = {}, {}
    for rel, full, info in entries:
        mode = f'{stat.S_IMODE(info.st_mode):04o}'
        if stat.S_ISDIR(info.st_mode):
            rows[rel] = ('d', mode, info.st_uid, info.st_gid, '-', '-', '-', '-', '-')
            dir_mtimes[rel] = int(info.st_mtime)
        elif stat.S_ISLNK(info.st_mode):
            rows[rel] = ('l', mode, info.st_uid, info.st_gid, '-', int(info.st_mtime), os.readlink(full), '-', '-')
        elif stat.S_ISREG(info.st_mode):
            rows[rel] = ('f', mode, info.st_uid, info.st_gid, info.st_size, int(info.st_mtime), '-', digests[full],
                         group_of.get(rel, '-'))
        else:
            rows[rel] = ('other', mode, info.st_uid, info.st_gid, '-', int(info.st_mtime), '-', '-', '-')
    print(json.dumps(write_manifest(rows, dir_mtimes, out)))


def cmd_expected(*paths_and_out: str) -> None:
    *member_files, out = paths_and_out
    rows, dir_mtimes = {}, {}
    for member_file in member_files:
        members = json.loads(Path(member_file).read_text())['members']
        links = []
        for entry in members:
            name = entry['name']
            if not name:
                continue
            mode = f'{entry["mode"] & 0o7777:04o}'
            if entry['kind'] == 'd':
                rows[name] = ('d', mode, 0, 0, '-', '-', '-', '-', '-')
                dir_mtimes[name] = int(entry['mtime'])
            elif entry['kind'] == 'l':
                rows[name] = ('l', '0777', 0, 0, '-', int(entry['mtime']), entry['linkname'], '-', '-')
            elif entry['kind'] == 'f':
                rows[name] = ('f', mode, 0, 0, entry['size'], int(entry['mtime']), '-', entry['sha256'], '-')
            elif entry['kind'] == 'h':
                links.append((name, entry['linkname'].removeprefix('./').rstrip('/')))
            else:
                raise SystemExit(f'expected: unhandled member kind {entry["kind"]} for {name}')
        parent: dict[str, str] = {}

        def find(path: str) -> str:
            while parent.setdefault(path, path) != path:
                path = parent[path]
            return path

        for name, target in links:
            parent[find(name)] = find(target)
        groups: dict[str, list[str]] = {}
        for path in list(parent):
            groups.setdefault(find(path), []).append(path)
        for paths in groups.values():
            files = [path for path in paths if path in rows and rows[path][0] == 'f']
            if not files:
                raise SystemExit(f'expected: hard-link group without a regular file: {sorted(paths)}')
            base, group = rows[files[0]], min(paths)
            for path in paths:
                rows[path] = base[:8] + (group,)
    print(json.dumps(write_manifest(rows, dir_mtimes, out)))


def read_manifest(path: str) -> tuple[dict, dict]:
    rows, dirs, section = {}, {}, None
    with open(path) as handle:
        for line in handle:
            line = line.rstrip('\n')
            if line in ('#CORE', '#DIRMTIME'):
                section = line
                continue
            fields = line.split('\t')
            if section == '#CORE':
                rows[fields[0]] = fields[1:]
            else:
                dirs[fields[0]] = fields[1]
    return rows, dirs


def cmd_diff(left: str, right: str) -> None:
    a_rows, a_dirs = read_manifest(left)
    b_rows, b_dirs = read_manifest(right)
    names = ['kind', 'mode', 'uid', 'gid', 'size', 'mtime', 'link', 'sha256', 'hardlink_group']
    report: dict[str, list] = {'only_left': sorted(set(a_rows) - set(b_rows)),
                               'only_right': sorted(set(b_rows) - set(a_rows))}
    for path in sorted(set(a_rows) & set(b_rows)):
        for index, (x, y) in enumerate(zip(a_rows[path], b_rows[path])):
            if x != y:
                report.setdefault(names[index], []).append([path, x, y])
    report['dir_mtime'] = [[p, a_dirs[p], b_dirs[p]] for p in sorted(set(a_dirs) & set(b_dirs)) if a_dirs[p] != b_dirs[p]]
    print(json.dumps({key: {'count': len(value), 'examples': value[:5]} for key, value in report.items()}))


def main(argv: list[str]) -> None:
    if len(argv) >= 4 and argv[1] == 'manifest' and len(argv) == 4:
        cmd_manifest(argv[2], argv[3])
    elif len(argv) >= 4 and argv[1] == 'expected':
        cmd_expected(*argv[2:])
    elif len(argv) == 4 and argv[1] == 'diff':
        cmd_diff(argv[2], argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
