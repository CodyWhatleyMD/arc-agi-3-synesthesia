#!/usr/bin/env python3
"""Build the runtime-layer variants the unpack bench compares, from the shipped gzip layer blobs.

Every variant carries the same tar bytes as the shipped layer, only packaged differently, so an extraction can be
checked against the original member by member:

  raw     <blob.tar.gz> <out.tar>                 the decompressed tar stream (sha256 and size printed as JSON)
  scan    <raw.tar> <members.json>                 every member with its raw byte range and content sha256
  plan    <members.json> <parts> <plan.json>       member-aligned cut points giving parts of near-equal raw bytes
  parts   <raw.tar> <plan.json> <gzip|zstd> <dir>  one self-contained tar per part, compressed (<= 4 at once)
  single  <raw.tar> <zstd> <out>                   the whole stream recompressed (zstd -T4)

A part is the raw bytes of a contiguous run of members plus a fresh end-of-archive (two zero blocks, padded to a
10240-byte record), so each part is an ordinary tar that GNU tar extracts on its own. Members are never re-serialized.
A scan refuses archives whose bytes are not covered member by member (a pax global header would be dropped by a cut).
Hard links stay in the same part as their target or the plan fails (layer 100 has none; checked by the scan).

Compression levels: gzip parts use pigz -6 (the level build_runtime_py313.py produced layer 100 with: pigz default);
zstd uses ZSTD_LEVEL (default 3) with --long=27, a 128 MiB window, the largest the Python zstandard decoder accepts
without raising max_window_size. Level 19 was tried first and stopped on 11-01 (29.7 min for layer 100 at -T4 on 4
E-cores; decode speed barely depends on the level: 1 GiB sample, -3 0.73-0.75 s, -19 0.84 s), but it reads fewer
bytes: layer 100 at -19 is 4,546,611,315 B.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import threading
from pathlib import Path

BLOCK = 512
RECORD = 10240
CHUNK = 1 << 22
ZSTD_LEVEL = int(os.environ.get('ZSTD_LEVEL', '3'))
ZSTD_LONG = int(os.environ.get('ZSTD_LONG', '27'))
KIND = {tarfile.REGTYPE: 'f', tarfile.AREGTYPE: 'f', tarfile.CONTTYPE: 'f', tarfile.DIRTYPE: 'd',
        tarfile.SYMTYPE: 'l', tarfile.LNKTYPE: 'h', tarfile.CHRTYPE: 'c', tarfile.BLKTYPE: 'b',
        tarfile.FIFOTYPE: 'p'}


def end_marker(length: int) -> bytes:
    """Two zero blocks, then zeros up to the next full record, as GNU tar writes an archive's end."""
    total = length + 2 * BLOCK
    return b'\0' * (2 * BLOCK + (-total) % RECORD)


def cmd_raw(blob: str, out: str) -> None:
    digest = hashlib.sha256()
    size = 0
    with subprocess.Popen(['pigz', '-dc', blob], stdout=subprocess.PIPE) as proc, open(out, 'wb') as handle:
        for block in iter(lambda: proc.stdout.read(CHUNK), b''):
            digest.update(block)
            handle.write(block)
            size += len(block)
    if proc.returncode != 0:
        raise SystemExit(f'pigz -dc {blob} failed: {proc.returncode}')
    print(json.dumps({'blob': blob, 'raw': out, 'raw_size': size, 'raw_sha256': digest.hexdigest()}))


def normalize(name: str) -> str:
    name = name[2:] if name.startswith('./') else name
    return name.rstrip('/')


def cmd_scan(raw: str, out: str) -> None:
    members = []
    with tarfile.open(raw, 'r:') as tar:
        for info in tar:
            kind = KIND.get(info.type, 'other:' + info.type.decode('ascii', 'replace'))
            entry = {'name': normalize(info.name), 'kind': kind, 'mode': info.mode, 'uid': info.uid,
                     'gid': info.gid, 'size': info.size, 'mtime': info.mtime, 'linkname': info.linkname,
                     'offset': info.offset, 'offset_data': info.offset_data, 'sparse': bool(info.sparse)}
            if info.isreg():
                digest = hashlib.sha256()
                stream = tar.extractfile(info)
                for block in iter(lambda: stream.read(CHUNK), b''):
                    digest.update(block)
                entry['sha256'] = digest.hexdigest()
            members.append(entry)
        end = tar.offset
    raw_size = os.path.getsize(raw)
    problems = []
    if members and members[0]['offset'] != 0:
        problems.append(f'first member at {members[0]["offset"]}, not 0 (global header?)')
    for previous, current in zip(members, members[1:]):
        expected = previous['offset_data'] + -(-previous['size'] // BLOCK) * BLOCK
        if not previous['sparse'] and expected != current['offset']:
            problems.append(f'gap before {current["name"]}: {expected} != {current["offset"]}')
    tail = None
    if raw_size - end < (1 << 20):
        with open(raw, 'rb') as handle:
            handle.seek(end)
            tail = handle.read()
    if tail is None or tail.strip(b'\0'):
        problems.append('bytes after the last member are not all zero')
    kinds: dict[str, int] = {}
    for entry in members:
        kinds[entry['kind']] = kinds.get(entry['kind'], 0) + 1
    names = [entry['name'] for entry in members]
    summary = {'raw': raw, 'raw_size': raw_size, 'end_offset': end, 'members': len(members), 'kinds': kinds,
               'duplicate_names': len(names) - len(set(names)), 'sparse': sum(e['sparse'] for e in members),
               'regular_bytes': sum(e['size'] for e in members if e['kind'] == 'f'), 'problems': problems[:20],
               'problem_count': len(problems)}
    Path(out).write_text(json.dumps({'summary': summary, 'members': members}))
    print(json.dumps(summary))
    if problems:
        raise SystemExit('scan found problems; a member-aligned split is not safe')


def cmd_plan(members_json: str, parts: int, out: str) -> None:
    data = json.loads(Path(members_json).read_text())
    members, end = data['members'], data['summary']['end_offset']
    cuts = [0]
    for k in range(1, parts):
        target = end * k // parts
        index = next(i for i, entry in enumerate(members) if entry['offset'] >= target and i > cuts[-1])
        cuts.append(index)
    ranges = []
    for k, start in enumerate(cuts):
        stop = cuts[k + 1] if k + 1 < len(cuts) else len(members)
        begin = members[start]['offset']
        finish = members[stop]['offset'] if stop < len(members) else end
        ranges.append({'part': k, 'first_member': start, 'members': stop - start, 'begin': begin, 'end': finish,
                       'raw_bytes': finish - begin})
    owner = {}
    for k, part in enumerate(ranges):
        for entry in members[part['first_member']:part['first_member'] + part['members']]:
            owner[entry['name']] = k
    crossing = [entry['name'] for k, part in enumerate(ranges)
                for entry in members[part['first_member']:part['first_member'] + part['members']]
                if entry['kind'] == 'h' and owner.get(normalize(entry['linkname'])) != k]
    if crossing:
        raise SystemExit(f'{len(crossing)} hard links would cross parts, e.g. {crossing[:3]}')
    Path(out).write_text(json.dumps({'members_json': members_json, 'end_offset': end, 'parts': ranges}, indent=1))
    print(json.dumps(ranges))


def compressor(codec: str) -> list[str]:
    if codec == 'gzip':
        return ['pigz', '-6', '-p', '1', '-c']
    if codec == 'zstd':
        return ['zstd', f'-{ZSTD_LEVEL}', f'--long={ZSTD_LONG}', '-T1', '-q', '-c']
    raise SystemExit(f'unknown codec {codec}')


def write_part(raw: str, part: dict, codec: str, path: Path, results: list) -> None:
    digest = hashlib.sha256()
    with open(path, 'wb') as sink, subprocess.Popen(compressor(codec), stdin=subprocess.PIPE, stdout=sink) as proc:
        with open(raw, 'rb') as source:
            source.seek(part['begin'])
            left = part['raw_bytes']
            while left:
                block = source.read(min(CHUNK, left))
                if not block:
                    raise SystemExit(f'{raw} ended inside part {part["part"]}')
                digest.update(block)
                proc.stdin.write(block)
                left -= len(block)
            tail = end_marker(part['raw_bytes'])
            digest.update(tail)
            proc.stdin.write(tail)
        proc.stdin.close()
    if proc.returncode != 0:
        raise SystemExit(f'compressor failed on part {part["part"]}: {proc.returncode}')
    results.append({'part': part['part'], 'file': str(path), 'size': path.stat().st_size,
                    'raw_bytes': part['raw_bytes'] + len(end_marker(part['raw_bytes'])),
                    'raw_sha256': digest.hexdigest()})


def cmd_parts(raw: str, plan_json: str, codec: str, outdir: str) -> None:
    plan = json.loads(Path(plan_json).read_text())
    suffix = {'gzip': 'tar.gz', 'zstd': 'tar.zst'}[codec]
    stem = Path(raw).name.removesuffix('.tar')
    results: list = []
    threads = [threading.Thread(target=write_part,
                                args=(raw, part, codec, Path(outdir) / f'{stem}.part{part["part"]}.{suffix}', results))
               for part in plan['parts']]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if len(results) != len(threads):
        raise SystemExit('a part failed')
    results.sort(key=lambda item: item['part'])
    print(json.dumps(results))


def cmd_single(raw: str, codec: str, out: str) -> None:
    if codec != 'zstd':
        raise SystemExit('single supports zstd only (the gzip single stream is the shipped blob)')
    subprocess.run(['zstd', f'-{ZSTD_LEVEL}', f'--long={ZSTD_LONG}', '-T4', '-q', '-f', raw, '-o', out], check=True)
    print(json.dumps({'raw': raw, 'file': out, 'size': os.path.getsize(out), 'level': ZSTD_LEVEL,
                      'long': ZSTD_LONG}))


def main(argv: list[str]) -> None:
    commands = {'raw': (cmd_raw, 2), 'scan': (cmd_scan, 2), 'plan': (cmd_plan, 3), 'parts': (cmd_parts, 4),
                'single': (cmd_single, 3)}
    if len(argv) < 2 or argv[1] not in commands or len(argv) - 2 != commands[argv[1]][1]:
        raise SystemExit(__doc__)
    function, _ = commands[argv[1]]
    args = argv[2:]
    if argv[1] == 'plan':
        args = [args[0], int(args[1]), args[2]]
    function(*args)


if __name__ == '__main__':
    main(sys.argv)
