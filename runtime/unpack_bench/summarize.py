#!/usr/bin/env python3
"""Tables for the unpack bench: every repeat, medians, pre-stated verdicts, identity, Kaggle rates and the saving band.

Usage: summarize.py <results dir>
The results dir holds run_<arm>_r<rep>.json and man_<arm>_r<rep>.json (run_bench.sh), expected_summary.json
(`tree_manifest.py expected` for layer 100 over layer 8), and the build records single_l100.json, single_l8.json,
parts_zstd.json, parts_gzip.json (zstd level 3) and single_l100_level19.json, single_l8_level19.json.

Verdicts follow notes/prestate_runtime_unpack_2026-11-01.md and its amendment 1. Each repeat's layer-100 time is
divided by the comparator's median, and a verdict needs every repeat on the same side of its threshold; otherwise it
is NOT RESOLVED. Kaggle band for one session: CPU-bound = its time x (local arm / local A0), per layer.
Read-bound = its time x (arm bytes / shipped gzip bytes); for 4-part arms that is divided by 1 (no parallel read
gain) up to 4 (a 4x gain).
"""
import json
import statistics
import sys
from pathlib import Path

KAGGLE = [  # (session, layer 8 s, layer 100 s): harness 'Extracted runtime layer' lines; all image 9a6bcfda
    ('C7', 10, 86), ('C4', 17, 98), ('C5', 17, 98), ('C2', 17, 103), ('C6', 17, 110), ('XZ', 27, 110),
    ('NE', 27, 125), ('C3', 28, 130), ('Gc', 29, 144), ('Gs', 35, 151), ('A1', 35, 158), ('A2', 34, 175),
    ('A3', 48, 209),
    # found after the pre-statement was written (same image, same extract_layer):
    ('dflash2-fork', 8, 75), ('v37', 17, 94), ('pool-clock-v2', 20, 112), ('pool-clock-v1', 22, 122)]
GZ = {'8': 1453071769, '100': 6920985983}
RAW = {'8': 2958304768, '100': 18273095680}
THRESHOLDS = {  # hypothesis: (arm, comparator, confirm if ratio <= a, refute if ratio > b)
    'H3 zstd single stream': ('A2', 'A0', 0.6, 0.8),
    'H5 4 gzip parts': ('A4', 'A0', 0.5, 0.75),
    'H6 4 zstd parts': ('A5', 'A2', 0.5, 0.75),
}


def last_json(path: Path):
    try:
        return json.loads(path.read_text().strip().splitlines()[-1])
    except (OSError, json.JSONDecodeError, IndexError):
        return None


def main(argv: list[str]) -> None:
    results = Path(argv[1])
    expected = last_json(results / 'expected_summary.json')
    build = {name: json.loads((results / f'{name}.json').read_text())
             for name in ('single_l100', 'single_l8', 'parts_zstd', 'parts_gzip', 'single_l100_level19',
                          'single_l8_level19')}
    runs = {}
    for path in sorted(results.glob('run_A*_r*.json')):
        arm, rep = path.stem.removeprefix('run_').rsplit('_r', 1)
        runs[(arm, int(rep))] = (json.loads(path.read_text()), last_json(results / f'man_{arm}_r{rep}.json') or {})
    reference = runs.get(('A0', 1), (None, {}))[1]

    print('## Every repeat (seconds; a layer = the time between its "Extracted" line and the one before)')
    print('| arm | rep | layer 8 | layer 100 | both | tar ok | core manifest | dir mtimes | load (1 min) before |')
    print('|---|---|---|---|---|---|---|---|---|')
    order = sorted(runs, key=lambda key: (key[1], ['A0', 'A2', 'A5', 'A4', 'A3'].index(key[0])))
    identity_ok = {}
    for key in order:
        record, manifest = runs[key]
        layers = {layer['layer']: layer['seconds'] for layer in record['layers']}
        same = bool(manifest) and manifest.get('core_sha256') == reference.get('core_sha256')
        label = '= A0 r1' if same else ('MISSING' if not manifest else 'DIFFERS ' + str(manifest.get('core_sha256'))[:12])
        identity_ok.setdefault(key[0], []).append(same and record['ok'])
        dirs = 'same' if manifest.get('dirmtime_sha256') == reference.get('dirmtime_sha256') else 'differ'
        print(f'| {key[0]} | {key[1]} | {layers.get("8")} | {layers.get("100")} | {record["total_s"]} | '
              f'{record["ok"]} | {label} | '
              f'{dirs} | {record["loadavg_before"][0]:.2f} |')
    print()
    ref_vs_archive = expected and reference.get('core_sha256') == expected.get('core_sha256')
    print(f'- A0 r1 core manifest {str(reference.get("core_sha256"))[:16]} vs archive members (layer 100 over 8) '
          f'{str(expected and expected.get("core_sha256"))[:16]}: {"EQUAL" if ref_vs_archive else "DIFFERENT"}; '
          f'dir mtimes {"equal" if expected and reference.get("dirmtime_sha256") == expected.get("dirmtime_sha256") else "different"}; '
          f'entries {reference.get("entries")} (tree) vs {expected and expected.get("entries")} (archives)')
    for arm, oks in sorted(identity_ok.items()):
        print(f'- H7 identity {arm}: {"PASS" if ref_vs_archive and all(oks) else "VOID"} ({sum(oks)}/{len(oks)} repeats = A0 r1)')
    print()

    def series(arm: str, layer: str) -> list[float]:
        return [l['seconds'] for (a, _), (record, _) in sorted(runs.items()) if a == arm and record['ok']
                for l in record['layers'] if l['layer'] == layer]

    medians = {}
    print('## Per arm')
    print('| arm | layer 8 repeats | layer 100 repeats | layer 100 median | layer 100 raw MB/s (median) |')
    print('|---|---|---|---|---|')
    for arm in ('A0', 'A2', 'A3', 'A4', 'A5'):
        l8, l100 = series(arm, '8'), series(arm, '100')
        if not l100:
            continue
        medians[arm] = {'8': statistics.median(l8), '100': statistics.median(l100)}
        print(f'| {arm} | {", ".join(f"{x:.1f}" for x in l8)} | {", ".join(f"{x:.1f}" for x in l100)} | '
              f'{medians[arm]["100"]:.1f} | {RAW["100"] / medians[arm]["100"] / 1e6:.0f} |')
    print()
    print('## Pre-stated verdicts (layer 100; each repeat / comparator median)')
    a0 = series('A0', '100')
    if a0:
        h1 = 'CONFIRMED' if all(x <= 50 for x in a0) else 'REFUTED' if all(x >= 70 for x in a0) else 'NOT RESOLVED'
        print(f'- H1 not inflate-bound on Kaggle (A0 <= 50 s; refuted if >= 70 s): A0 = {a0} -> {h1}')
    for name, (arm, base, confirm, refute) in THRESHOLDS.items():
        if arm not in medians or base not in medians:
            continue
        ratios = [x / medians[base]['100'] for x in series(arm, '100')]
        verdict = ('CONFIRMED' if all(r <= confirm for r in ratios) else
                   'REFUTED' if all(r > refute for r in ratios) else 'NOT RESOLVED')
        print(f'- {name}: {arm}/{base} = {", ".join(f"{r:.3f}" for r in ratios)} '
              f'(confirm <= {confirm}, refute > {refute}) -> {verdict}')
    if 'A3' in medians and 'A2' in medians:
        gap = abs(medians['A3']['100'] - medians['A2']['100']) / medians['A2']['100']
        print(f'- H4 diagnostic: A3 {medians["A3"]["100"]:.1f} s vs A2 {medians["A2"]["100"]:.1f} s, gap {gap:.1%} '
              f'-> {"within 15%: the tar write path, not zstd, bounds A2" if gap <= 0.15 else "over 15%: decode still costs time in A2"}')
    print()
    sizes = {
        'A0': {'8': GZ['8'], '100': GZ['100']},
        'A2': {'8': build['single_l8']['size'], '100': build['single_l100']['size']},
        'A3': {'8': GZ['8'], '100': RAW['100']},
        'A4': {'8': GZ['8'], '100': sum(p['size'] for p in build['parts_gzip'])},
        'A5': {'8': build['single_l8']['size'], '100': sum(p['size'] for p in build['parts_zstd'])},
        'A2 at -19': {'8': build['single_l8_level19']['size'], '100': build['single_l100_level19']['size']},
    }
    print('## Bytes read (layer 8 / layer 100; fraction of the shipped gzip)')
    for arm, size in sizes.items():
        print(f'- {arm}: {size["8"]:,} B ({size["8"] / GZ["8"]:.3f}) / {size["100"]:,} B ({size["100"] / GZ["100"]:.3f})')
    print(f'- 4-part sizes, gzip: {[p["size"] for p in build["parts_gzip"]]}; zstd: {[p["size"] for p in build["parts_zstd"]]}')
    print()
    print('## Kaggle sessions: rates implied by the logged times (pigz)')
    print('| session | layer 8 s | layer 100 s | l100/l8 | l8 read MB/s | l100 read MB/s | l100 raw write MB/s |')
    print('|---|---|---|---|---|---|---|')
    for session, l8, l100 in sorted(KAGGLE, key=lambda row: row[2]):
        print(f'| {session} | {l8} | {l100} | {l100 / l8:.1f} | {GZ["8"] / l8 / 1e6:.0f} | {GZ["100"] / l100 / 1e6:.0f} | '
              f'{RAW["100"] / l100 / 1e6:.0f} |')
    print(f'- reference ratios: compressed bytes l100/l8 = {GZ["100"] / GZ["8"]:.2f}; raw bytes = {RAW["100"] / RAW["8"]:.2f}; '
          f'local A0 time = {medians["A0"]["100"] / medians["A0"]["8"]:.2f}' if 'A0' in medians else '')
    print()
    print('## Kaggle band: seconds saved on layers 8 + 100 against each session\'s own pigz time')
    arms = [arm for arm in ('A2', 'A4', 'A5') if arm in medians]
    header = ' | '.join(f'{arm} CPU-bound | {arm} read-bound' for arm in arms)
    print(f'| session | now (8+100) | {header} | A2 at -19 read-bound |')
    print('|---|---|' + '---|---|' * len(arms) + '---|')
    for session, l8, l100 in KAGGLE:
        now = l8 + l100
        cells = []
        for arm in arms:
            cpu = sum(t * (1 - medians[arm][layer] / medians['A0'][layer]) for layer, t in (('8', l8), ('100', l100)))
            read_hi = sum(t * (1 - sizes[arm][layer] / GZ[layer]) for layer, t in (('8', l8), ('100', l100)))
            if arm in ('A4', 'A5'):
                read_4x = l8 * (1 - sizes[arm]['8'] / GZ['8']) + l100 * (1 - sizes[arm]['100'] / GZ['100'] / 4)
                cells.append(f'{cpu:.0f} | {read_hi:.0f}..{read_4x:.0f}')
            else:
                cells.append(f'{cpu:.0f} | {read_hi:.0f}')
        a19 = sum(t * (1 - sizes['A2 at -19'][layer] / GZ[layer]) for layer, t in (('8', l8), ('100', l100)))
        print(f'| {session} | {now} | {" | ".join(cells)} | {a19:.0f} |')
    print('- write-bound (raw bytes or file creation on the overlay limit the unpack): 0 s for every arm above, '
          'since every arm writes the same tree')


if __name__ == '__main__':
    main(sys.argv)
