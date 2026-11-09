#!/usr/bin/env python3
"""Time one arm of the runtime unpack bench inside the Kaggle image: extract layer 8, then layer 100, into a root.

Usage: bench_unpack.py <arm> <root> <out.json>

A layer is one or more tar jobs started together; the layer ends when the last job exits. A0 is the harness's
extract_layer command line exactly (kaggle.py:1126-1133). Times are taken the way install_image_runtime prints
them: one monotonic clock started after the root is created, read when each layer finishes. Whiteout replay is
not run (it is the same in every arm).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SRC = '/src'
BLOBS = '/blobs'
L8 = f'{SRC}/layer-8-a48fcd63b1db0c7dce7f0a272f7ab6166de8f12c77a1a6bcd5732d73e00f39e9.tar.gz.blob'
L100 = f'{SRC}/layer-100-d905036361721a0ec6c091b177201ecd8388fa2625f098ce665ca656a0e866c5.tar.gz.blob'
ZSTD_HELPER = 'python3 -I /bench/zstd_decompress.py'
GZ_PARTS = [f'{BLOBS}/parts_gzip/l100.part{k}.tar.gz' for k in range(4)]
ZST_PARTS = [f'{BLOBS}/parts_zstd/l100.part{k}.tar.zst' for k in range(4)]
ARMS = {
    'A0': [[(L8, 'pigz')], [(L100, 'pigz')]],
    'A1': [[(L8, 'gzip')], [(L100, 'gzip')]],
    'A2': [[(f'{BLOBS}/l8.tar.zst', 'zstd')], [(f'{BLOBS}/l100.tar.zst', 'zstd')]],
    'A3': [[(L8, 'pigz')], [(f'{BLOBS}/l100.tar', 'none')]],
    'A4': [[(L8, 'pigz')], [(part, 'pigz') for part in GZ_PARTS]],
    'A5': [[(f'{BLOBS}/l8.tar.zst', 'zstd')], [(part, 'zstd') for part in ZST_PARTS]],
    'T8': [[(L8, 'pigz')]],  # driver smoke test only: layer 8, as A0
}
LAYER_NAMES = ['8', '100']


def tar_command(blob: str, codec: str, root: str) -> list[str]:
    base = ['tar', '-xf', blob, '-C', root, '--no-same-owner']
    return base + {'pigz': ['--use-compress-program=pigz'], 'gzip': ['-z'],
                   'zstd': [f'--use-compress-program={ZSTD_HELPER}'], 'none': []}[codec]


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ARMS:
        raise SystemExit(__doc__)
    arm, root, out = argv[1], Path(argv[2]), Path(argv[3])
    if root.exists():
        raise SystemExit(f'{root} exists; the driver must remove it first')
    for layer in ARMS[arm]:
        for blob, _ in layer:
            if not os.path.isfile(blob):
                raise SystemExit(f'missing input {blob}')
    root.mkdir(parents=True)
    record = {'arm': arm, 'root': str(root), 'nice': os.nice(0), 'cpus': sorted(os.sched_getaffinity(0)),
              'loadavg_before': os.getloadavg(), 'layers': []}
    started = time.monotonic()
    previous = 0.0
    ok = True
    for name, layer in zip(LAYER_NAMES, ARMS[arm]):
        jobs = []
        layer_start = time.monotonic()
        for blob, codec in layer:
            command = tar_command(blob, codec, str(root))
            jobs.append((blob, codec, command, time.monotonic(),
                         subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)))
        results = []
        for blob, codec, command, job_start, proc in jobs:
            _, err = proc.communicate()
            results.append({'blob': blob, 'codec': codec, 'command': command, 'returncode': proc.returncode,
                            'job_s': round(time.monotonic() - job_start, 3),
                            'stderr': err.decode(errors='replace')[-2000:]})
            ok &= proc.returncode == 0
        done = time.monotonic() - started
        record['layers'].append({'layer': name, 'seconds': round(done - previous, 3), 'after_s': round(done, 3),
                                 'layer_wall_s': round(time.monotonic() - layer_start, 3), 'jobs': results})
        previous = done
    record['total_s'] = round(time.monotonic() - started, 3)
    record['loadavg_after'] = os.getloadavg()
    record['ok'] = ok
    out.write_text(json.dumps(record, indent=1))
    print(json.dumps({'arm': arm, 'ok': ok, 'total_s': record['total_s'],
                      'layers': {layer['layer']: layer['seconds'] for layer in record['layers']}}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
