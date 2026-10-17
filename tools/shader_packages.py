#!/usr/bin/env python3
"""Package measured D3 NVN stages for the pinned offline translation chain."""
import collections
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work'
MAGIC = bytes.fromhex('34127698')
STAGES = {1: 'vs', 2: 'hs', 3: 'ds', 4: 'gs', 5: 'ps'}
ZH = {'vs': '顶点', 'ps': '像素', 'cs': '计算', 'hs': '外壳', 'ds': '域', 'gs': '几何'}


def stage_record(control, code):
    size = struct.unpack_from('<I', control, 0x20)[0]
    nctl = size if 0x760 <= size < 0x880 else 0x880
    control = control[:nctl]
    if len(control) != nctl or control[:4] != MAGIC:
        raise ValueError('Truncated/invalid control section')
    length = struct.unpack_from('<I', control, 0x704)[0]
    if length != len(code) or not 0 < length < 16 * 1024 * 1024:
        raise ValueError('Code length mismatch')
    if code[:4] == bytes.fromhex('78563412'):
        stage = STAGES[(struct.unpack_from('<I', code, 0x30)[0] >> 10) & 15]
    elif code[:4] == bytes.fromhex('79563412'):
        stage = 'cs'
    else:
        raise ValueError('Unsurveyed D3 code header')
    key = hashlib.sha256(control + code).hexdigest()[:16]
    return key, stage, control, code


def main():
    unique, pairs, capture_keys = {}, set(), set()
    for source in sorted((WORK / 'shaders/source').glob('*.shd')):
        data = source.read_bytes()
        offset = 0
        per_file = collections.defaultdict(set)
        while (offset := data.find(MAGIC, offset)) >= 0:
            if offset + 0x760 > len(data):
                raise ValueError(f'Truncated control: {source}')
            nctl = struct.unpack_from('<I', data, offset + 0x20)[0]
            if not 0x760 <= nctl <= 0x1000:
                raise ValueError(f'Unsurveyed control length {nctl:#x}: {source}')
            ncode = struct.unpack_from('<I', data, offset + 0x704)[0]
            start = offset + nctl
            key, stage, control, code = stage_record(data[offset:offset + nctl], data[start:start + ncode])
            if key in unique and unique[key][1:] != (stage, control, code):
                raise ValueError('Shader key collision')
            unique[key] = (source.name + f'@{offset:x}', stage, control, code)
            per_file[stage].add(key)
            offset = start + ncode
        pairs.update((v, p) for v in per_file['vs'] for p in per_file['ps'])
    matched = 0
    for path in sorted((WORK / 'run/shdump').glob('*.ctl')):
        key, stage, control, code = stage_record(path.read_bytes(), path.with_suffix('.code').read_bytes())
        if key != path.stem:
            raise ValueError(f'Runtime key mismatch: {path}')
        capture_keys.add(key)
        if key in unique:
            if unique[key][1:] != (stage, control, code):
                raise ValueError('Static extraction differs from runtime bytes')
            matched += 1
        else:
            unique[key] = ('runtime:' + path.name, stage, control, code)
    if not unique:
        raise ValueError('No original shader stages found')
    package = WORK / 'shaders/package'
    package.mkdir(parents=True, exist_ok=True)
    game = ROOT / 'third_party/nxnative/dm/games/01001B300B9BE000'
    rows, facts, counts, output = [], {}, collections.Counter(), collections.defaultdict(bytearray)
    for key in sorted(unique):
        origin, stage, control, code = unique[key]
        name = stage + '_d3.bin'
        record = bytearray(b'BTCDBTCD' + bytes(0x30))
        struct.pack_into('<II', record, 0x28, len(control), len(code))
        record += code + control
        if record.find(MAGIC) != 0x38 + len(code) or record.count(b'BTCDBTCD') != 1:
            raise ValueError('Ambiguous package record delimiter')
        rows.append(f'{name}\t{counts[stage]}\t{ZH[stage]}\t{key}\t{origin}\n')
        output[name] += record
        counts[stage] += 1
        if stage == 'cs':
            xyz = struct.unpack_from('<III', control, 0x748)
            if not all(xyz):
                raise ValueError('Zero compute local dimensions')
            facts[key] = {'local': xyz, 'shared': (struct.unpack_from('<I', control, 0x754)[0] + 15) & ~15}
    for name, data in output.items():
        (package / name).write_bytes(data)
    (game / 'shader_map.tsv').write_text('# Original D3 merged CPK and runtime stages\npackage\tindex\tstage\tdm_ctl_sha16\tsource\n' + ''.join(rows))
    (game / 'shader_facts.tsv').write_text('# Compute dimensions from original control sections\n' + ''.join(k + '\t' + json.dumps(v) + '\n' for k, v in sorted(facts.items())))
    (game / 'shader_pairs.tsv').write_text('# Conservative VS/PS combinations within each original .shd; not observed draw pairs\n' + ''.join(f'{a}\t{b}\n' for a, b in sorted(pairs)))
    receipt = {'stages': dict(counts), 'runtime_captured': len(capture_keys), 'runtime_static_byte_matches': matched,
               'runtime_missing_in_static': sorted(capture_keys - {k for k, v in unique.items() if not v[0].startswith('runtime:')}),
               'cpk_receipt_sha256': hashlib.sha256((WORK / 'shaders/cpk-receipt.json').read_bytes()).hexdigest(),
               'limitations': ['Other shader container formats unverified', 'Driver constant layout and Metal pipeline linking require execution']}
    (WORK / 'shaders/package-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
