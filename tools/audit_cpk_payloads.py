#!/usr/bin/env python3
"""Sequential, resumable CPK sector decode audit; no extraction or payload writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import zlib

from cpk_shaders import StrictReader
from rom_audit import validate_archive

ROOT = Path(__file__).resolve().parents[1]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def expected_sector_bytes(offsets, total, index):
    if not 0 <= index < len(offsets):
        raise ValueError('Sector index outside mapping')
    start = offsets[index]
    end = offsets[index + 1] if index + 1 < len(offsets) else total
    if not 0 <= start <= end <= total:
        raise ValueError('Invalid decompressed sector boundaries')
    return end - start


def check_decoded_sector(raw, offsets, total, index):
    expected = expected_sector_bytes(offsets, total, index)
    if len(raw) != expected:
        raise ValueError(f'Decoded sector boundary mismatch: expected={expected} actual={len(raw)}')
    return len(raw)



def audited_sector(reader, index):
    """Use the same strict decoder as resource extraction, without adaptations."""
    # Diagnostics describe the most recent decode. Force a fresh sector decode
    # even if another caller populated the random-access cache beforehand.
    reader.sector.cache_clear()
    raw = reader.sector(index)
    return raw, bool(reader.last_sector_notes['empty_encrypted_terminators'])


def decoder_identity(root):
    paths = ('tools/cpk_shaders.py', 'tools/audit_cpk_payloads.py',
             'tools/rom_audit.py', 'third_party/d3cpk/cpklib.py')
    return dict(policy='cpk-v7-verified-full-sector-lookahead-v1',
                sources={p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths})


def check_resume(state, signature, decoder):
    if state['inputs'] != signature:
        raise ValueError('Input inventory changed; use a new output directory')
    if state.get('decoder_identity') != decoder:
        raise ValueError('Decoder identity changed or absent; use a new output directory')


def check_payload_crc(data, first_sector, expected):
    """Header +0x38 covers stored compressed-sector bytes through physical EOF.

    All 51 shipped archives independently match IEEE CRC-32 with initial=0.
    The checksum includes encrypted bytes and sector padding, excludes the
    metadata/index prefix, and is checked before decryption or inflation.
    """
    if not 0 <= first_sector <= len(data):
        raise ValueError('CRC payload range outside archive')
    value = 0
    with memoryview(data) as view:
        for position in range(first_sector, len(data), 8 * 1024 * 1024):
            value = zlib.crc32(view[position:position + 8 * 1024 * 1024], value)
    if value != expected:
        raise ValueError(f'CPK stored-payload CRC mismatch: expected={expected:#x} actual={value:#x}')
    return value


def inventory(root):
    rom = root / 'work/game/RomFS'
    paths = list((rom / 'CPKs').glob('*.cpk')) + list((rom / 'Update/CPKs').glob('*.cpk'))
    paths += list((root / 'work/aoc/11').glob('*.cpk'))
    return sorted(paths, key=lambda path: (path.stat().st_size, str(path)))


def scan(path, progress=None):
    start = time.monotonic()
    row = dict(path=str(path), file_bytes=path.stat().st_size, mtime_ns=path.stat().st_mtime_ns,
               started_utc=stamp(), status='scanning', sectors_checked=0, decoded_bytes=0,
               empty_encrypted_terminators=0, verified_overlap_fragments=0, verified_overlap_bytes=0,
               overlap_fragments=[])
    reader = None
    digest = hashlib.sha256()
    last_progress = start
    try:
        reader = StrictReader(path)
        archive = reader.archive
        validate_archive(archive, path.stat().st_size)
        row.update(total_sectors=len(archive._cs2do), declared_decompressed_bytes=archive.header.decomp_fs,
                   members=len(archive.entries), header_sector_crc32=hex(archive.header.sector_crc32))
        actual_crc = check_payload_crc(reader.mapping, archive._first_sec, archive.header.sector_crc32)
        row.update(stored_payload_crc32=hex(actual_crc), stored_payload_crc32_verified=True,
                   crc_bytes=len(reader.mapping) - archive._first_sec)
        if archive._cs2do[0] != 0:
            raise ValueError('Decompressed stream does not start at zero')
        for index in range(len(archive._cs2do)):
            row['current_sector'] = index
            raw, empty_marker = audited_sector(reader, index)
            row['empty_encrypted_terminators'] += int(empty_marker)
            overlap = reader.last_sector_notes['overlap_bytes']
            if overlap:
                row['verified_overlap_fragments'] += 1
                row['verified_overlap_bytes'] += overlap
                row['overlap_fragments'].append(dict(sector=index, overlap_bytes=overlap))
            row['decoded_bytes'] += check_decoded_sector(raw, archive._cs2do, archive.header.decomp_fs, index)
            digest.update(raw)
            row['sectors_checked'] += 1
            # StrictReader has a bounded random-access cache; this streaming audit
            # retains only the current sector rather than caching previous payloads.
            reader.sector.cache_clear()
            if progress and time.monotonic() - last_progress >= 5:
                row['seconds'] = round(time.monotonic() - start, 3)
                progress(dict(row))
                last_progress = time.monotonic()
        if row['decoded_bytes'] != archive.header.decomp_fs:
            raise ValueError('Decoded stream length differs from header')
        row.update(status='decoded', decoded_sha256=digest.hexdigest())
    except Exception as error:
        row.update(status='analysis_failed', error_type=type(error).__name__, error=str(error),
                   classification='Parser/layout/decode disagreement; ROM corruption is not established.')
    finally:
        if reader is not None:
            reader.close()
        row.update(seconds=round(time.monotonic() - start, 3), finished_utc=stamp())
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-archives', type=int, default=0)
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--path', type=Path, action='append', help='Scan only these archives (absolute or root-relative)')
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.output or root / 'work/audit' / ('payload-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True, exist_ok=True)
    statefile = out / 'summary.json'
    paths = [(p if p.is_absolute() else root / p).resolve() for p in args.path] if args.path else inventory(root)
    signature = {str(p): dict(file_bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns) for p in paths}
    decoder = decoder_identity(ROOT)
    if statefile.exists():
        state = json.loads(statefile.read_text())
        check_resume(state, signature, decoder)
    else:
        state = dict(started_utc=stamp(), inputs=signature, decoder_identity=decoder, results={},
                     limitations=['Full sequential sector inflate and declared boundary checks, without extraction.',
                                  'Zero-length encrypted terminators require expected=0 and all-zero remaining sector padding.',
                                  'Zlib-stream Adler checks apply when a final marker exists. Unterminated full-sector fragments may encode overlapping lookahead only when every excess byte matches the following independently decoded logical stream.',
                                  'Header +0x38 is IEEE CRC-32 of every stored byte from the first compressed sector through physical EOF; metadata/index prefix is outside that checksum.',
                                  'Decoded SHA-256 is a receipt, not comparison to an independently trusted resource manifest.',
                                  'Successful decoding does not prove resource semantics or game compatibility.',
                                  'Resume reuses finished archives with unchanged size/mtime; an interrupted archive is rescanned from sector zero.'])
    processed = 0
    for path in paths:
        key = str(path)
        prior = state['results'].get(key)
        if prior and (prior['status'] == 'decoded' or (prior['status'] == 'analysis_failed' and not args.retry_failed)):
            continue
        state.update(status='scanning', active_archive=key, updated_utc=stamp())
        def progress(row):
            state.update(active_progress=row, updated_utc=stamp())
            save(statefile, state)
        row = scan(path, progress)
        state['results'][key] = row
        state.pop('active_progress', None)
        state.update(updated_utc=stamp())
        save(statefile, state)
        print(json.dumps(dict(path=path.name, status=row['status'], sectors=row['sectors_checked'],
                              decoded_bytes=row['decoded_bytes'], seconds=row['seconds'], error=row.get('error')), ensure_ascii=False), flush=True)
        processed += 1
        if args.max_archives and processed >= args.max_archives:
            break
    done = len(state['results']) == len(paths)
    failures = sum(row['status'] == 'analysis_failed' for row in state['results'].values())
    state.update(status=('finished_with_analysis_failures' if failures else 'decoded') if done else 'partial',
                 active_archive=None, completed_archives=len(state['results']), analysis_failures=failures,
                 total_archives=len(paths), decoded_bytes=sum(row['decoded_bytes'] for row in state['results'].values()),
                 updated_utc=stamp())
    save(statefile, state)
    print(json.dumps(dict(output=str(out), status=state['status'], completed=state['completed_archives'],
                         failures=failures, total=len(paths)), ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
