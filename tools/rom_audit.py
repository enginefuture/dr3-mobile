#!/usr/bin/env python3
"""Bounded local ROM/host capability inventory; never decompress archive payloads."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import struct
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from nso import load_nso


def checked_slice(data, offset, size, label):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f'{label} outside file')
    return data[offset:offset + size]


class MachO:
    """Thin arm64 Mach-O + validated DYLD_CHAINED_PTR_64_OFFSET registry reader."""
    def __init__(self, data):
        self.data = data
        h = struct.unpack('<8I', checked_slice(data, 0, 32, 'Mach-O header'))
        if h[0] != 0xfeedfacf or h[1] != 0x100000c:
            raise ValueError('Expected thin little-endian arm64 Mach-O')
        ncmd, sizecmd = h[4:6]
        commands = checked_slice(data, 32, sizecmd, 'load commands')
        self.segments, self.sections, self.fixups = [], {}, set()
        offset, chain = 0, None
        for _ in range(ncmd):
            cmd, size = struct.unpack('<II', checked_slice(commands, offset, 8, 'load command'))
            c = checked_slice(commands, offset, size, 'load command body')
            if size < 8 or size % 8:
                raise ValueError('Invalid load command size')
            if cmd == 0x19:
                if size < 72:
                    raise ValueError('Truncated segment')
                name = c[8:24].split(b'\0')[0].decode('ascii')
                vm, vmsz, fo, fs = struct.unpack_from('<QQQQ', c, 24)
                nsects = struct.unpack_from('<I', c, 64)[0]
                if size != 72 + nsects * 80 or fs > vmsz:
                    raise ValueError('Invalid segment layout')
                checked_slice(data, fo, fs, 'segment file range')
                self.segments.append(dict(name=name, vm=vm, vmsz=vmsz, fo=fo, fs=fs))
                for i in range(nsects):
                    s = c[72 + i * 80:152 + i * 80]
                    sn = s[:16].split(b'\0')[0].decode('ascii')
                    sg = s[16:32].split(b'\0')[0].decode('ascii')
                    addr, sz, off = struct.unpack_from('<QQI', s, 32)
                    if not vm <= addr <= addr + sz <= vm + vmsz:
                        raise ValueError('Section outside segment VM range')
                    if (sg, sn) in self.sections:
                        raise ValueError('Duplicate section')
                    self.sections[sg, sn] = dict(addr=addr, size=sz, offset=off)
            elif cmd == 0x80000034:
                if size != 16 or chain is not None:
                    raise ValueError('Invalid chained fixups command')
                chain = struct.unpack_from('<II', c, 8)
            offset += size
        if offset != sizecmd:
            raise ValueError('Load command count/size mismatch')
        text = [s for s in self.segments if s['name'] == '__TEXT']
        if len(text) != 1 or chain is None:
            raise ValueError('Missing text segment or chained fixups')
        self.base = text[0]['vm']
        self.pointer_formats = set()
        self._fixups(*chain)

    def vm_offset(self, address, size=1):
        matches = [s for s in self.segments if s['vm'] <= address and address + size <= s['vm'] + s['fs']]
        if len(matches) != 1:
            raise ValueError('VM address outside unique file-backed segment')
        s = matches[0]
        return s['fo'] + address - s['vm']

    def _fixups(self, off, size):
        d = checked_slice(self.data, off, size, 'chained fixups')
        version, starts, imports_offset, symbols_offset, self.import_count, imports_format, symbols_format = struct.unpack('<7I', checked_slice(d, 0, 28, 'fixups header'))
        if imports_format not in (1, 2, 3) or symbols_format != 0:
            raise ValueError('Unsupported chained import format')
        checked_slice(d, imports_offset, self.import_count * {1: 4, 2: 8, 3: 16}[imports_format], 'chained imports')
        checked_slice(d, symbols_offset, 1, 'chained import symbols')
        if version != 0:
            raise ValueError('Unsupported fixups version')
        count, = struct.unpack('<I', checked_slice(d, starts, 4, 'fixup segment count'))
        if count != len(self.segments):
            raise ValueError('Fixup segment count mismatch')
        offsets = struct.unpack('<' + 'I' * count, checked_slice(d, starts + 4, count * 4, 'fixup segment offsets'))
        for seg, rel in zip(self.segments, offsets):
            if not rel:
                continue
            si = starts + rel
            segsize, pagesz, fmt, segoff, _, npages = struct.unpack('<IHHQIH', checked_slice(d, si, 22, 'fixup segment'))
            raw = checked_slice(d, si, segsize, 'fixup page starts')
            if fmt != 6 or pagesz not in (4096, 16384) or segoff != seg['vm'] - self.base or segsize < 22 + 2 * npages:
                raise ValueError('Unsupported chained pointer layout')
            self.pointer_formats.add(fmt)
            for page in range(npages):
                start, = struct.unpack_from('<H', raw, 22 + page * 2)
                if start == 0xffff:
                    continue
                if start & 0x8000:
                    raise ValueError('Multi-start fixup pages not supported by this audit')
                local, seen = start, set()
                while True:
                    if local + 8 > pagesz or local in seen:
                        raise ValueError('Fixup chain leaves page or cycles')
                    seen.add(local)
                    address = self.base + segoff + page * pagesz + local
                    fileoff = self.vm_offset(address, 8)
                    self.fixups.add(fileoff)
                    word, = struct.unpack_from('<Q', self.data, fileoff)
                    nxt = (word >> 51) & 0xfff
                    if not nxt:
                        break
                    local += nxt * 4

    def pointer(self, slot):
        if slot not in self.fixups:
            raise ValueError('Registry pointer missing chained fixup')
        word, = struct.unpack_from('<Q', self.data, slot)
        if word >> 63 or ((word >> 36) & 0xff):
            raise ValueError('Bound/tagged registry pointer is unsupported')
        return self.base + (word & ((1 << 36) - 1))

    def cstring(self, address):
        start = self.vm_offset(address)
        segment = next(s for s in self.segments if s['fo'] <= start < s['fo'] + s['fs'])
        end = self.data.find(b'\0', start, min(start + 8192, segment['fo'] + segment['fs']))
        if end < 0:
            raise ValueError('Unterminated registry string')
        return self.data[start:end].decode('utf-8')

    def registry(self, name, stride):
        s = self.sections['__DATA', name]
        if s['size'] % stride:
            raise ValueError('Misaligned registry section')
        checked_slice(self.data, s['offset'], s['size'], 'registry')
        if self.vm_offset(s['addr'], s['size']) != s['offset']:
            raise ValueError('Registry file/VM mismatch')
        result = []
        for slot in range(s['offset'], s['offset'] + s['size'], stride):
            name = self.cstring(self.pointer(slot))
            fnslot = slot + 8
            if fnslot not in self.fixups:
                raise ValueError('Registry function pointer missing fixup')
            fnword, = struct.unpack_from('<Q', self.data, fnslot)
            if fnword >> 63:
                if (fnword & 0xffffff) >= self.import_count:
                    raise ValueError('Registry function bind ordinal outside import table')
            else:
                self.vm_offset(self.pointer(fnslot), 4)
            row = {'name': name}
            if stride == 24:
                row['policy'] = self.cstring(self.pointer(slot + 16))
            result.append(row)
        if len({r['name'] for r in result}) != len(result):
            raise ValueError('Duplicate registry name')
        return result


def validate_archive(a, length):
    """Validate table-derived member boundaries without reading member payloads."""
    h = a.header
    if len(a.entries) != h.file_count:
        raise ValueError('CPK names/SFI count mismatch')
    if not 0 <= a._first_sec <= length or not a._cs2do:
        raise ValueError('CPK sector range missing/outside file')
    if any(x < 0 or x > h.decomp_fs for x in a._cs2do) or any(x > y for x, y in zip(a._cs2do, a._cs2do[1:])):
        raise ValueError('CPK decompressed sector boundaries invalid')
    names = set()
    for e in a.entries:
        name = e.name.lower()
        p = PureWindowsPath(e.name)
        if not name or p.is_absolute() or p.root or p.drive or '..' in p.parts or name in names:
            raise ValueError('Unsafe or duplicate CPK member name')
        names.add(name)
        if e.loc_count < 0 or e.loc_idx < 0 or e.loc_idx + e.loc_count > h.loc_count:
            raise ValueError('CPK location range outside table')
        if e.loc_count and (e.offset < 0 or e.size < 0 or e.offset + e.size > h.decomp_fs):
            raise ValueError('CPK member extent outside decompressed stream')


def archive_inventory(root, out):
    from cpk_shaders import StrictReader
    rom = root / 'work/game/RomFS'
    paths = sorted((rom / 'CPKs').glob('*.cpk'))
    paths += sorted((rom / 'Update/CPKs').glob('*.cpk'), key=lambda p: tuple(map(int, re.findall(r'\d+', p.name))))
    paths += sorted((root / 'work/aoc/11').glob('*.cpk'))
    all_rows, members, merged = [], [], {}
    for path in paths:
        reader = StrictReader(path)
        try:
            a = reader.archive
            validate_archive(a, path.stat().st_size)
            label = str(path.relative_to(root))
            counts = Counter(e.ext for e in a.entries)
            all_rows.append(dict(archive=label, bytes=path.stat().st_size, files=len(a.entries),
                                 version=a.header.version, format=a.header.fmt_const,
                                 decomp_bytes=a.header.decomp_fs, sector_count=len(a._cs2do),
                                 extensions=dict(counts), locations=dict(Counter(e.loc_count for e in a.entries))))
            for e in a.entries:
                row = dict(archive=label, name=e.name, size=e.size, offset=e.offset, locations=e.loc_count, extension=e.ext)
                members.append(row)
                merged[e.name.lower()] = row
            print(f'Indexed {path.name}: {len(a.entries)} entries', flush=True)
        finally:
            reader.close()
    (out / 'archive-members.json').write_text(json.dumps(members, ensure_ascii=False))
    (out / 'merged-members.json').write_text(json.dumps(list(merged.values()), ensure_ascii=False))
    return dict(archives=all_rows, archive_count=len(paths), member_records=len(members),
                merged_names=len(merged), merged_extensions=dict(Counter(r['extension'] for r in merged.values())),
                payloads_decoded=0, multi_extent=sum(r['locations'] > 1 for r in members),
                no_location=sum(r['locations'] == 0 for r in members))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--host', type=Path, help='Exact built runtime to inventory')
    parser.add_argument('--log', type=Path, help='Runtime log paired with that build')
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.output or root / 'work/audit' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True, exist_ok=True)
    profile = json.loads((root / 'config/diablo3-2.7.7.json').read_text())
    modules, images = {}, {}
    for name in ('rtld', *profile['runtime_modules']):
        report, image = load_nso(root / 'work/game/ExeFS' / name)
        if name in profile['modules']:
            expected = profile['modules'][name]
            if report['sha256'] != expected['sha256'] or report['build_id'] != expected['build_id']:
                raise ValueError(f'Module identity differs: {name}')
        modules[name], images[name] = report, image
    host = args.host.resolve() if args.host else root / 'work/macapp-candidate/DR3 Mobile.app/Contents/MacOS/dmhost'
    hostdata = host.read_bytes()
    macho = MachO(hostdata)
    regs = {name: macho.registry(name, stride) for name, stride in [('swhle', 16), ('swforce', 24), ('swnvn', 16)]}
    (out / 'host-registries.json').write_text(json.dumps(regs, ensure_ascii=False, indent=2))
    hle, force = ({r['name'] for r in regs[n]} for n in ('swhle', 'swforce'))
    referenced = set().union(*(set(modules[n]['imports']) | set(modules[n]['exports']) for n in profile['runtime_modules']))
    forced_relevant = [r for r in regs['swforce'] if r['name'] in referenced]
    (out / 'forced-policies-symbol-present.json').write_text(json.dumps(forced_relevant, ensure_ascii=False, indent=2))
    exports = set().union(*(set(modules[n]['exports']) for n in profile['runtime_modules']))
    resolution = {}
    for name in profile['runtime_modules']:
        m = modules[name]
        groups = {'forced': [], 'guest_definition': [], 'host_hle': [], 'weak_unresolved': [], 'strong_unresolved': []}
        for sym in m['imports']:
            category = ('forced' if sym in force else 'guest_definition' if sym in exports else 'host_hle' if sym in hle else
                        'weak_unresolved' if sym in m['weak_imports'] else 'strong_unresolved')
            groups[category].append(sym)
        resolution[name] = groups
    nvn_dir = root / 'third_party/nxnative/dm/gfx/nvn'
    names = set((nvn_dir / 'names.txt').read_text().splitlines())
    nvnsource = (nvn_dir / 'hle_nvn.c').read_text()
    nopblock = re.search(r'g_nops\[\]\s*=\s*\{(.*?)\};', nvnsource, re.S).group(1)
    nops = set(re.findall(r'"(nvn\w+)"', nopblock))
    semantic = {r['name'] for r in regs['swnvn']}
    unknown = names - semantic - nops
    mainstrings = set(re.findall(rb'nvn[A-Za-z0-9_]+(?=\0)', bytes(images['main'])))
    sdkstrings = set(re.findall(rb'nvn[A-Za-z0-9_]+(?=\0)', bytes(images['sdk'])))
    log_path = args.log.resolve() if args.log else root / 'work/run/app.log'
    log = log_path.read_text(errors='replace')
    # Instrumented aggregate lines report calls; names absent from this capture are unobserved, not unused.
    observed = set('nvn' + s for s in re.findall(r'\b([A-Z][A-Za-z0-9]+)=\d+', log) if 'nvn' + s in names)
    nvnaudit = dict(total=len(names), semantic=len(semantic), noops=sorted(nops), unregistered=sorted(unknown),
                    rom_name_strings=sorted(s.decode() for s in mainstrings if s.decode() in names),
                    sdk_name_strings=sorted(s.decode() for s in sdkstrings if s.decode() in names),
                    runtime_observed=sorted(observed), runtime_observed_noops=sorted(observed & nops),
                    runtime_observed_unregistered=sorted(observed & unknown))
    (out / 'nvn-coverage.json').write_text(json.dumps(nvnaudit, indent=2))
    (out / 'module-symbols.json').write_text(json.dumps(dict(modules=modules, resolution=resolution), indent=2))
    svc_cases = set()
    for filename in ('hle_svc.c', 'hle_thread.c'):
        source = (root / 'third_party/nxnative/dm/host' / filename).read_text()
        svc_cases.update(int(x, 16) for x in re.findall(r'case (0x[0-9a-fA-F]+)\s*:', source))
    svc = {}
    for name in profile['runtime_modules']:
        text_segment = modules[name]['segments'][0]
        text = images[name][text_segment['offset']:text_segment['offset'] + text_segment['bytes']]
        sites = [dict(offset=hex(i * 4), number=hex((word >> 5) & 0xffff))
                 for i, (word,) in enumerate(struct.iter_unpack('<I', text)) if word & 0xffe0001f == 0xd4000001]
        numbers = {int(row['number'], 16) for row in sites}
        svc[name] = dict(instruction_sites=len(sites), numbers=sorted(hex(x) for x in numbers),
                         no_dispatch_case=sorted(hex(x) for x in numbers - svc_cases), sites=sites,
                         evidence='Static text SVC instructions/wrappers only; not a runtime reachability claim.')
    (out / 'svc-wrapper-coverage.json').write_text(json.dumps(svc, indent=2))
    warnings = sorted(set(line for line in log.splitlines() if any(t in line for t in ('【红】', 'CRASH', '未实现', '不支持'))))
    (out / 'runtime-warnings.txt').write_text('\n'.join(warnings) + '\n')
    archive = archive_inventory(root, out)
    shader = json.loads((root / 'work/shaders/package-receipt.json').read_text())
    receipt = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                   runtime_log=dict(path=str(log_path),sha256=hashlib.sha256(log_path.read_bytes()).hexdigest()),
                   host=dict(path=str(host), sha256=hashlib.sha256(hostdata).hexdigest(), pointer_formats=sorted(macho.pointer_formats),
                             registries={k: len(v) for k,v in regs.items()}, forced_symbol_present_names=len(forced_relevant)),
                   modules={n: dict(sha256=m['sha256'], build_id=m['build_id'], imports=len(m['imports']), exports=len(m['exports'])) for n,m in modules.items()},
                   resolution_counts={n:{k:len(v) for k,v in groups.items()} for n,groups in resolution.items()},
                   nvn=dict(total=len(names), semantic=len(semantic), noops=len(nops), unregistered=len(unknown),
                            rom_name_strings=len(nvnaudit['rom_name_strings']), runtime_observed=len(observed),
                            runtime_observed_noops=nvnaudit['runtime_observed_noops'], runtime_observed_unregistered=nvnaudit['runtime_observed_unregistered']),
                   svc_wrapper_counts={n:{k:v for k,v in row.items() if k != 'sites'} for n,row in svc.items()},
                   archives=archive, shader_receipt=shader, runtime_warning_lines=len(warnings),
                   limitations=['Archive member tables/extents only; no payload CRC/hash/decode verification.',
                                'Merged names apply base then numeric update then AOC; actual engine mount precedence needs runtime proof.',
                                'Import resolution is namespace coverage, not an execution trace or ABI proof.',
                                'NVN names in ROM are strings, not evidence every API executes.',
                                'Static shader compile coverage does not prove pipeline interfaces or image equivalence.',
                                'SDK SVC wrapper presence is not proof the game executes the wrapper.',
                                'No new process launch, input, focus change, GPU switch, or payload extraction performed.'])
    (out / 'summary.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(output=str(out), resolution=receipt['resolution_counts'], nvn=receipt['nvn'], archives=archive['archive_count'], records=archive['member_records'], merged=archive['merged_names']), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
