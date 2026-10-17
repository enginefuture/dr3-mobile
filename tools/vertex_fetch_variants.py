#!/usr/bin/env python3
"""Export independent, chain-bound vertex-fetch adaptation sources and variants."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

REVISION = 1
TYPES = ('float', 'uint', 'int')
UINT_FORMATS = {0x03,0x08,0x0b,0x0f,0x14,0x17,0x1b,0x20,0x23,0x27,0x2c,0x2f}
INT_FORMATS = {0x04,0x09,0x0c,0x10,0x15,0x18,0x1c,0x21,0x24,0x28,0x2d,0x30}
FLOAT_FORMATS = {0x01,0x02,0x05,0x06,0x07,0x0a,0x0d,0x0e,0x11,0x12,0x13,0x16,
                 0x19,0x1a,0x1d,0x1e,0x1f,0x22,0x25,0x26,0x29,0x2a,0x2b,0x2e,
                 0x3d,0x69,0x3f,0x9a}


def observed_signatures(cache: Path, ledger: Path) -> set[tuple[str, int]]:
    """Native pso_skey ABI verified as 432 bytes, attributes at byte 224.

    Successful R and failed F records carry the same exact serialized state.
    Unknown ABIs fail, rather than constructing a guessed input layout.
    """
    result=set()
    for line in ledger.read_text().splitlines():
        values=line.split('\t')
        if values[0] not in ('R','F') or len(values)<2:
            continue
        record=bytes.fromhex(values[1])
        if len(record)!=432:
            raise ValueError('Unknown pso_skey ABI')
        key=record[:24].split(b'\0',1)[0].decode('ascii')
        metadata=json.loads((cache/(key+'.json')).read_text())
        signature=0
        for attribute in metadata['vertex_inputs']:
            location=attribute['location']
            if not 0<=location<16:
                continue
            fmt=struct.unpack_from('<I',record,224+location*4)[0]&255
            wanted=1 if fmt in UINT_FORMATS else 2 if fmt in INT_FORMATS else 0 if fmt in FLOAT_FORMATS else None
            original=1 if attribute['msl_type'].startswith('uint') else 2 if attribute['msl_type'].startswith('int') else 0
            if wanted is not None and wanted!=original:
                signature|=(wanted+1)<<(location*2)
        if signature:
            result.add((key,signature))
    return result


def adapt_source(source: str, signature: int) -> str:
    """Same fail-closed transform as nvn_vertex_fetch.h; signature has 2 bits/loc."""
    if not signature:
        return source
    structure = re.search(r'struct\s+main0_in\s*\{([\s\S]*?)\};', source)
    entry = source.find('vertex main0_out main0(')
    brace = source.find('{', entry) if entry >= 0 else -1
    if not structure or brace < 0:
        raise ValueError('unrecognized generated vertex entry')
    head, body = source[:brace+1], source[brace+1:]
    attribute = re.compile(r'\b(float|uint|int)([234]?)\s+(\w+)\s*\[\[attribute\((\d+)\)\]\]')
    aliases, seen = [], 0
    matches = list(attribute.finditer(source, *structure.span(1)))
    for match in reversed(matches):
        original, width, member, loc = match.groups()
        loc = int(loc)
        if loc >= 32:
            continue
        requested = (signature >> (loc*2)) & 3
        if not requested:
            continue
        if seen & (3 << (loc*2)):
            raise ValueError('duplicate vertex attribute')
        seen |= requested << (loc*2)
        new_type = TYPES[requested-1]
        if new_type == original:
            raise ValueError('redundant requested attribute transform')
        alias = 'dm_fetch_' + member
        if alias in source:
            raise ValueError('vertex alias collision')
        body, count = re.subn(r'\bin\.' + re.escape(member) + r'\b', alias, body)
        if not count:
            raise ValueError('attribute access is not recognized')
        aliases.append(f'\n    {original}{width} {alias} = as_type<{original}{width}>(in.{member});')
        a, b = match.span(1)
        head = head[:a] + new_type + head[b:]
    if seen != signature:
        raise ValueError('requested vertex location is absent')
    return head + ''.join(aliases) + body


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def export_sources(cache: Path) -> dict:
    exported = {}
    for path in sorted(cache.glob('*_b.json')):
        metadata = json.loads(path.read_text())
        if metadata.get('stage') != 'vs':
            continue
        source = path.with_suffix('.metal').read_bytes()
        output = path.with_suffix('.vsrc')
        manifest_path = path.with_suffix('.vsrc.json')
        manifest = {'chain': metadata['chain'], 'base_key': metadata['key'],
                    'revision': REVISION, 'sha256': sha(source), 'variants': {}}
        if manifest_path.exists():
            old = json.loads(manifest_path.read_text())
            if all(old.get(k) == manifest[k] for k in ('chain', 'base_key', 'revision', 'sha256')):
                manifest['variants'] = old.get('variants', {})
        atomic_write(output,source)
        atomic_write(manifest_path,(json.dumps(manifest, indent=2)+'\n').encode())
        exported[metadata['key']] = manifest
    return exported


def build_variant(cache: Path, key: str, signature: int, sdk: str = 'macosx') -> Path:
    """Call only for this cache's target platform; libraries must never cross SDKs."""
    source = (cache / (key + '.vsrc')).read_text()
    transformed = adapt_source(source, signature)
    stem = cache / f'{key}_vf{signature:016x}'
    msl = stem.with_suffix('.metal')
    air = stem.with_suffix('.air')
    lib = stem.with_suffix('.metallib')
    msl.write_text(transformed)
    subprocess.run(['xcrun', '-sdk', sdk, 'metal', '-c', str(msl), '-o', str(air)], check=True)
    subprocess.run(['xcrun', '-sdk', sdk, 'metallib', str(air), '-o', str(lib)], check=True)
    manifest_path = cache / (key + '.vsrc.json')
    manifest = json.loads(manifest_path.read_text())
    manifest['variants'][f'{signature:016x}'] = {'file': lib.name, 'source_sha256': sha(transformed.encode()),
                                             'library_sha256': sha(lib.read_bytes()), 'sdk': sdk}
    atomic_write(manifest_path,(json.dumps(manifest, indent=2)+'\n').encode())
    return lib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache', type=Path)
    parser.add_argument('--sdk', default='macosx', choices=['macosx', 'iphoneos'])
    parser.add_argument('--known-variants', action='store_true')
    parser.add_argument('--ledger',type=Path,help='Also prebuild exact layouts recorded in this native PSO ledger')
    args = parser.parse_args()
    exported = export_sources(args.cache)
    built = []
    requested=observed_signatures(args.cache,args.ledger) if args.ledger else set()
    if args.known_variants:
        requested.update([('18f2aadcec113d49_b',0x10),('88ba806f61d19fae_b',0x4)])
    for key,signature in sorted(requested):
        built.append(str(build_variant(args.cache,key,signature,args.sdk)))
    print(json.dumps({'sources': len(exported), 'variants': built}, indent=2))


if __name__ == '__main__':
    main()
