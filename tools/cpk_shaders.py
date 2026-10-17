#!/usr/bin/env python3
"""Extract the merged D3 .shd inventory with bounded, strict sector decoding."""
import argparse
import bisect
from functools import lru_cache
import hashlib
import json
import mmap
from pathlib import Path, PureWindowsPath
import re
import struct
import sys
import zlib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'third_party/d3cpk'))
from cpklib import CPKArchive


def decrypt(chunk):
    source = np.frombuffer(chunk, dtype=np.uint8)
    output = np.empty_like(source)
    n = min(8, len(source))
    # Preserve the numeric initializer in the reference v7 extractor; its hex
    # comment and cpklib's copied literal disagree with that numeric value.
    initial = ((-8702387258687105183) & ((1 << 64) - 1)).to_bytes(8, 'little')
    output[:n] = source[:n] ^ np.frombuffer(initial, dtype=np.uint8)[:n]
    output[8:] = source[8:] ^ source[:-8]
    return output.tobytes()


class StrictReader:
    """Reference table reader, independent bounded random-access decompression.

    The reference decoder silently inserts zeroes after inflate failures. This
    tool never calls that decoder or global_stream; any decode/gap error fails.
    """
    def __init__(self, path):
        self.file = path.open('rb')
        self.mapping = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.archive = CPKArchive(self.mapping, str(path))
        h = self.archive.header
        if h.version != 7 or h.comp_sector != 16384 or h.fmt_const not in (2, 10):
            raise ValueError('Unsurveyed CPK layout')
        if any(a > b for a, b in zip(self.archive._cs2do, self.archive._cs2do[1:])):
            raise ValueError('Non-monotonic CPK sector table')

    def _sector(self, index):
        """Decode one physical sector, retaining verified logical boundaries.

        The game's bounded inflate may stop before an unfinished DEFLATE
        fragment's last output.  A full physical sector can therefore encode a
        prefix of the next logical sector too.  Return that lookahead separately
        so sector() can check it against the independently restarted next stream.
        """
        a, data = self.archive, self.mapping
        h = a.header
        if not 0 <= index < len(a._cs2do):
            raise ValueError('Sector outside CPK')
        position = a._first_sec + index * h.comp_sector
        end = min(position + h.comp_sector, len(data))
        # In this Switch build sector zero starts with a normal chunk. The
        # reference reader skips it as an index preamble, dropping 41548 bytes
        # in ClientCommon. Its decoded length plus the following chunk equals
        # cs2do[1] exactly; keep it and verify the adjacent-sector boundary.
        output = bytearray()
        lookahead = b''
        notes = dict(empty_encrypted_terminators=0, overlap_bytes=0)
        while position + 6 <= end:
            low, high, packed = struct.unpack_from('<HHH', data, position)
            if not packed:
                break
            length = packed & 0x7fff
            expected = high << 16 | low
            position += 6
            if packed == 0x8000 and expected == 0:
                if any(data[position:end]):
                    raise ValueError('Nonzero bytes after empty encrypted terminator')
                notes['empty_encrypted_terminators'] += 1
                break
            if not length or position + length > end or expected > 16 * 1024 * 1024:
                raise ValueError('Invalid CPK compressed chunk bounds')
            chunk = data[position:position + length]
            if packed & 0x8000:
                chunk = decrypt(chunk)
            decoder = zlib.decompressobj()
            try:
                raw = decoder.decompress(chunk, 32 * 1024 * 1024 + 1)
            except zlib.error as error:
                raise ValueError(f'CPK inflate error: {self.archive.path} sector={index} position={position} packed={packed:#x} expected={expected} chunk_head={chunk[:8].hex()}') from error
            # main 2607a74f, 0x76307c / 0x763084: the CPK reader sets
            # z_stream.avail_out to the requested logical length and calls
            # inflate without requiring Z_STREAM_END. Full-sector fragments may
            # encode additional output; it must match the next restarted stream,
            # never be silently discarded. Complete streams must still be exact.
            fragment_overlap = (len(raw) > expected and length == h.comp_sector - 6
                                and position + length == end and not decoder.eof
                                and expected > 0 and len(raw) <= 32 * 1024 * 1024)
            if ((len(raw) != expected and not fragment_overlap)
                    or decoder.unused_data or decoder.unconsumed_tail):
                raise ValueError(f'CPK inflate mismatch: {self.archive.path} sector={index} offset={position} expected={expected} actual={len(raw)} eof={decoder.eof} unused={len(decoder.unused_data)} tail={len(decoder.unconsumed_tail)}')
            output.extend(raw[:expected])
            if fragment_overlap:
                lookahead = raw[expected:]
                notes['overlap_bytes'] = len(lookahead)
            if len(output) > 32 * 1024 * 1024:
                raise ValueError('CPK sector output exceeds budget')
            position += length
        offsets = a._cs2do
        if hasattr(h, 'decomp_fs'):
            next_offset = offsets[index + 1] if index + 1 < len(offsets) else h.decomp_fs
            if len(output) != next_offset - offsets[index]:
                raise ValueError(f'CPK sector boundary mismatch: sector={index} expected={next_offset - offsets[index]} actual={len(output)}')
        return bytes(output), lookahead, notes

    @lru_cache(maxsize=128)
    def sector(self, index):
        raw, lookahead, notes = self._sector(index)
        remaining = lookahead
        following = index + 1
        while remaining:
            if following >= len(self.archive._cs2do):
                raise ValueError(f'CPK fragment overlap outside logical stream: sector={index}')
            prefix, _, _ = self._sector(following)
            take = min(len(prefix), len(remaining))
            if not take or prefix[:take] != remaining[:take]:
                raise ValueError(f'CPK fragment overlap mismatch: sector={index} following={following} bytes={len(lookahead)}')
            remaining = remaining[take:]
            following += 1
        self.last_sector_notes = notes
        return raw

    def read(self, entry):
        if entry.size > 64 * 1024 * 1024 or entry.loc_count != 1:
            raise ValueError('Unsupported shader extent')
        position, end = entry.offset, entry.offset + entry.size
        if end > self.archive.header.decomp_fs:
            raise ValueError('Shader extent outside decompressed stream')
        result = bytearray()
        while position < end:
            index = bisect.bisect_right(self.archive._cs2do, position) - 1
            if index < 0:
                raise ValueError('Shader precedes first sector')
            start = self.archive._cs2do[index]
            raw = self.sector(index)
            take = min(end - position, len(raw) - (position - start))
            if take <= 0:
                raise ValueError(f'CPK shader gap: {self.archive.path} name={entry.name} entry={entry.offset}+{entry.size} position={position} index={index} sector={start}+{len(raw)} next={self.archive._cs2do[index+1:index+2]}')
            result.extend(raw[position - start:position - start + take])
            position += take
        return bytes(result)

    def close(self):
        self.sector.cache_clear()
        self.mapping.close()
        self.file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    work = ROOT / 'work'
    rom = work / 'game/RomFS'
    paths = sorted((rom / 'CPKs').glob('*.cpk'))
    paths += sorted((rom / 'Update/CPKs').glob('*.cpk'), key=lambda p: tuple(map(int, re.findall(r'\d+', p.name))))
    entries = {}
    for path in paths:
        reader = StrictReader(path)
        for entry in reader.archive.entries:
            if entry.ext == 'shd':
                entries[entry.name.lower()] = (path, entry)
        reader.close()
    output = work / 'shaders/source'
    output.mkdir(parents=True, exist_ok=True)
    report = []
    grouped = {}
    for name, (path, entry) in entries.items():
        grouped.setdefault(path, []).append(entry)
    for path, group in grouped.items():
        reader = StrictReader(path)
        try:
            for entry in group:
                windows = PureWindowsPath(entry.name)
                if windows.is_absolute() or '..' in windows.parts:
                    raise ValueError('Unsafe shader archive name')
                raw = reader.read(entry)
                key = hashlib.sha256(raw).hexdigest()
                target = output / (key + '.shd')
                target.write_bytes(raw)
                report.append({'archive': str(path.relative_to(rom)), 'name': entry.name, 'bytes': len(raw),
                               'sha256': key, 'output': target.name})
                if len(report) % 100 == 0:
                    print(f'{len(report)}/{len(entries)} shaders extracted', flush=True)
                if args.limit and len(report) >= args.limit:
                    break
        finally:
            reader.close()
        if args.limit and len(report) >= args.limit:
            break
    (work / 'shaders/cpk-receipt.json').write_text(json.dumps({'found': len(entries), 'extracted': report,
         'complete': len(report) == len(entries), 'scope': 'merged .shd only; other shader containers remain unverified'}, indent=2) + '\n')
    print(f'Extracted {len(report)}/{len(entries)} merged shader files')


if __name__ == '__main__':
    main()
