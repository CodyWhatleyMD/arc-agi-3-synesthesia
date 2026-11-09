#!/usr/bin/env python3
"""Decompress a zstd stream to stdout with the Python `zstandard` module (the Kaggle image has no zstd binary).

GNU tar runs it as `<program> -d` with the archive on stdin (--use-compress-program), so `-d` is accepted and
ignored; a path argument reads that file instead. Input is read 16 MiB at a time: on Kaggle's NFS mounts
(read_ahead_kb=128) small sequential reads are latency-bound, and pigz reads 32 KiB at a time.
copy_stream runs ZSTD_decompressStream until the input ends, so concatenated frames are decompressed too.
"""
import sys

import zstandard

READ_SIZE = 16 << 20
WRITE_SIZE = 1 << 20
MAX_WINDOW = 1 << 27  # zstd --long=27; the module's default limit, stated so a larger window fails loudly


def main(argv: list[str]) -> int:
    paths = [arg for arg in argv[1:] if arg != '-d']
    if len(paths) > 1:
        print('usage: zstd_decompress.py [-d] [file]', file=sys.stderr)
        return 2
    source = open(paths[0], 'rb') if paths else sys.stdin.buffer
    decompressor = zstandard.ZstdDecompressor(max_window_size=MAX_WINDOW)
    with source:
        decompressor.copy_stream(source, sys.stdout.buffer, read_size=READ_SIZE, write_size=WRITE_SIZE)
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
