# Pre-statement: a faster unpack of the vLLM runtime dataset (local CPU bench), 2026-11-01

Written before any timing in this bench. The result goes in `notes/runtime_unpack_2026-10-31.md`. Nothing here
ships: no dataset version, no harness or notebook change, no Kaggle run.

## Facts checked before writing (inventory, not timings)
- The Kaggle image: all 13 Kaggle runs whose logs we hold (C2-C7, A1-A3, Gc, Gs, NE, XZ; BOOT lines) ran
  `gcr.io/kaggle-gpu-images/python@sha256:9a6bcfda6d03...`. The local `gcr.io/kaggle-gpu-images/python:latest` has
  that same repo digest (`docker image inspect`).
- That image ships **pigz 2.8 at /usr/bin/pigz**; `shutil.which('pigz')` finds it on the image's PATH. The harness's
  `extract_layer` (kaggle.py:1126, unchanged since 8552964) uses pigz whenever `which` finds it. So the Kaggle unpack
  already runs pigz, not single-threaded `tar -z`. This is inferred from the digest and the code, because the
  harness does not log which decompressor ran.
- Also in the image: GNU tar 1.35, gzip 1.12, xz, the Python `zstandard` 0.25.0 C extension (libzstd 1.5.7), and
  cramjam 2.12.1 (zstd/lz4/gzip, no ISA-L). Not in the image: a `zstd`/`unzstd`/`pzstd` binary, lz4, pixz, igzip,
  rapidgzip.
- pigz -d reads its input 32 KiB at a time; gzip -d reads 256 KiB at a time (strace, host pigz 2.8 / gzip 1.12).
- The local copy of the dataset is `/mnt/data/arc3_runtime313/dataset`. Its runtime-manifest.json is byte-identical to
  the one kagglehub fetched from Kaggle (version 1), and its 8 files have the names and sizes that `kaggle datasets files`
  lists. Layer 100 is 6,920,985,983 B gzip and layer 8 is 1,453,071,769 B gzip.
- Kaggle layer times from those 13 runs. The harness prints when each layer finishes; layer 100 time = its line minus
  layer 8's line. Layer 8: 10-48 s. Layer 100: 86, 98, 98, 103, 110, 110, 125, 130, 144, 151, 158, 175, 209 s.
  The machine is an AMD EPYC 9B45 with 46 usable vCPUs; busy cores read ~4.1 GHz (host probe v2).
- Local layer times from 58 earlier local runs (same image, same harness code, unpinned CPUs, the blob in page cache):
  layer 8 = 5 s in all 58; layer 100 = 31 s (6 runs), 32 s (37), 33 s (14), 34 s (1).

## Conditions (all arms)
- Everything runs in the Kaggle image above, as root (as on Kaggle), with `--network none`, `--cpuset-cpus 16-19`
  (4 E-cores at 4.9 GHz max), `--cpu-shares 2` and `nice -n 19`. Host-side builds use `taskset -c 16-19 nice -n 19`.
- Input comes from RAM in every arm: the original blobs come from page cache, warmed and checked by a full sha256
  read, and the variant blobs sit in `/dev/shm`. So the bench measures CPU plus write cost. It cannot measure
  Kaggle's NFS read.
- Output goes to `/media/ignaz/claude-extra` (ext4 on a USB SSD), one tree at a time. Between repeats: manifest the
  tree, delete it, syncfs, and wait for Dirty+Writeback below 512 MB. No repeat starts with under 22 GB free, and a
  repeat is aborted if free space falls below 3 GB.
- Each repeat extracts layer 8, then layer 100, into one root, as `install_image_runtime` does. Whiteout replay is
  skipped. It is identical in every arm and touches only layer 8's 64 markers.
- Repeats: 3 per arm. Block 1 alternates A3 and A0 (A3 needs the 16.5 GB raw tar in RAM, deleted after the block).
  Block 2 runs 3 rotated rounds of A0, A1, A2, A4, A5. Every repeat is reported.

## Arms (each differs from its comparator in one thing)
- **A0, current:** `tar -xf <blob> -C <root> --no-same-owner --use-compress-program=pigz`. This is kaggle.py's command.
- **A1:** as A0 with `-z` (single-threaded gzip), the harness's no-pigz fallback. Comparator: A0.
- **A2:** layers 8 and 100 hold the same raw tar streams recompressed with zstd, and decompress through the image's
  Python `zstandard` (`--use-compress-program="python3 zstd_decompress.py"`). Comparator: A0. The level comes from a
  1 GiB sample sweep, reported with the result.
- **A3:** layer 100 is the uncompressed raw tar (`tar -xf`), layer 8 as in A0. This is the floor for any single tar
  stream, and it tells decompression cost from tar's own write cost. Comparator: A0.
- **A4:** layer 100 is split at member boundaries into 4 contiguous gzip parts (pigz -6, the original's level), with
  4 `tar ... pigz` running at once. Layer 8 as in A0. Comparator: A0.
- **A5:** as A4 with zstd parts and the zstd helper. Layer 8 as in A2. Comparator: A2.

## Hypotheses and what refutes them (layer 100, median of 3 unless stated)
- **H1 (the Kaggle unpack is not inflate-bound).** Local A0 on these 4 E-cores takes <= 50 s, under 0.6x Kaggle's
  fastest 86 s. **Refuted** if A0 >= 70 s. In that case CPU alone could explain Kaggle's times.
- **H2 (pigz beats gzip).** A1 >= 1.15x A0. **Refuted** if A1 <= 1.05x A0.
- **H3 (zstd, single stream).** A2 <= 0.6x A0. **Refuted** if A2 > 0.8x A0.
- **H4 (diagnostic, no pass/fail).** A3 versus A2: if A3 is within 15% of A2, tar's write path, not zstd, bounds A2.
- **H5 (4 gzip parts).** A4 <= 0.5x A0. **Refuted** if A4 > 0.75x A0.
- **H6 (4 zstd parts).** A5 <= 0.5x A2. **Refuted** if A5 > 0.75x A2.
- **H7 (identity, a gate).** In every repeat of every arm, the tree's core manifest must equal A0 repeat 1's: paths,
  types, modes, uid/gid, sizes, file and symlink mtimes, symlink targets, hardlink groups, and sha256 of every regular
  file. A0 repeat 1 must itself equal the manifest read from the archives' members, layer 100 over layer 8. Any
  mismatch makes that arm **VOID** (not shippable) whatever its speed. Directory mtimes are reported separately.
  They are expected to differ in A4/A5, where parallel tars write into directories after another tar has set their
  times. Nothing reads them: .pyc checks use file mtimes.

## Kaggle estimate (method fixed now)
No Kaggle run is made, so the estimate is a band between two models, given for each of the 13 Kaggle sessions.
- **CPU-bound:** Kaggle time x (local arm / local A0).
- **Read-bound single stream:** Kaggle time x (arm's compressed bytes / 6.92 GB) for single-file arms. For N-part
  arms the read speedup lies between 1x and Nx and is unknown.

The note will say which model the local data favour (H1), and that only a Kaggle validation run settles the question.

## Amendment 1 (11-01 04:38 CDT, before any arm was timed): scope cut by the orchestrator
At 04:31 the orchestrator asked me to stop the zstd -19 builds, use -3 (or -9 at most) at -T4 and nice 19, measure
decompress wall time and the byte-identical tree check, and finish in about 30 minutes. These changes were made before
any full-arm timing. Only two things had run: the 1 GiB sample sweep and a layer-8 smoke test of the driver (14.3 s,
tree = archive manifest).
- A2 and A5 use zstd level 3 with --long=27. Sample sweep: 1 GiB = 4 x 256 MiB slices of layer 100, Kaggle image,
  4 E-cores. Bytes per GiB: -3 314.8 MB, -9 290.2, -15 279.1, -19 258.0, pigz -6 389.4. Decode, zstandard helper to
  /dev/null: -3 0.73-0.75 s, -19 0.84 s, pigz -d 2.07 s. With sha256 in the pipe, gzip -d took 3.93-3.96 s. The -19
  single streams had finished before the stop (layer 100: 4,546,611,315 B in 1,781 s; layer 8: 1,090,404,772 B in
  291 s). They enter only as sizes, in the read-bound estimate. The -19 part builds were stopped and deleted.
- Repeats: 2 each for A0, A2, A4 and A5, and 1 for A3. A1 is dropped: the image has pigz, so the gzip fallback never
  runs there, and H2 goes untested. Order: A0 A2 A5 A4 A3 A0 A2 A5 A4.
- With 2 repeats, a verdict needs both repeats on the same side of its threshold; otherwise it is NOT RESOLVED.
  Thresholds are unchanged. H4 uses A3's single repeat.
- The separate variant-decode check is dropped. The tree-manifest gate (H7) is the identity check.

## Amendment 2 (11-01 04:50 CDT, after A0 r1, A2 r1, A5 r1 and A4 r1; before any rerun)
- **A4 r1 is excluded**, not treated as a measurement of the arm. Layer 100 took 121.9 s. While it ran, something
  outside the bench took about 57 GB of shared memory: at 04:46:30 `free` showed 97 GB shared against my 38 GB in
  /dev/shm. The kernel pushed my /dev/shm variants out to swap: at 04:46:44 resident Shmem was 0.87 GB while /dev/shm
  still held 40 GB, and swap use had grown from about 20 GB to 62 GB. So A4 read its gzip parts back from swap. Its
  tree check never finished, because I stopped the chain during the manifest. The record is kept aside and reported
  in the result. I did not identify the outside process.
- The repeats before it ran at 04:39:42-04:41:51 and match the earlier local history (A0 34.3 s vs 31-34 s), but
  there is no swap counter for them.
- A3 is dropped and its raw tar deleted: re-warming the swapped 18 GB would cost the time budget. H4 goes untested.
- Driver change for every rerun: before each repeat the arm's /dev/shm inputs are read back in, alongside the
  originals. pswpin/pswpout are recorded around each extraction, and **a repeat with pswpin > 0 during its extraction
  is excluded.**
- Reruns: A4 r2, A0 r2, A2 r2, A5 r2, A4 r3. Verdict rules are unchanged; A4's are judged on r2 and r3.

## Correction to amendment 2 (found while summarizing, 11-01 ~04:55)
Two of its statements were wrong when written, and are corrected in notes/runtime_unpack_2026-10-31.md:
- A4 r1's tree check DID finish (04:47:22, core manifest equal to the archives).
- A3 r1 HAD run (04:47:2x-04:48:06, input mostly in swap, load 10.9; tree check not finished), so it is excluded,
  not "dropped".

The swap rule (pswpin > 0) is system-wide. Applied as written, it would exclude all five reruns; the result note
reports both readings.
