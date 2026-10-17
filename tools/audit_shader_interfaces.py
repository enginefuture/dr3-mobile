#!/usr/bin/env python3
"""Read-only audit of extracted D3 shader stages; never compiles or runs a shader.

Container co-occurrence is a conservative candidate, not a draw observation.
The append-only PSO ledger records successful pipeline creation, not image QA.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CHAIN = 'b-87c50a868147'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fields(source, name, attribute='user'):
    match = re.search(r'\bstruct\s+' + re.escape(name) + r'\s*\{(.*?)\};', source, re.S)
    if not match:
        return {}, []
    body = match.group(1)
    pattern = (r'\b(\w+)\s+(\w+)\s*\[\[user\(locn(\d+)\)([^]]*)\]\]'
               if attribute == 'user' else
               r'\b(\w+)\s+(\w+)\s*\[\[attribute\((\d+)\)([^]]*)\]\]')
    result = {}
    for typ, member, loc, qualifiers in re.findall(pattern, body):
        result[int(loc)] = {'type': typ, 'member': member, 'qualifiers': qualifiers.strip(' ,')}
    unknown = []
    if body.count('[[user(' if attribute == 'user' else '[[attribute(') != len(result):
        unknown.append(f'unparsed or duplicate {attribute} in {name}')
    return result, unknown


def compare(vs, ps):
    """Missing declarations are definite; differing declarations need linker proof."""
    missing = sorted(set(ps['inputs']) - set(vs['outputs']))
    different = []
    for loc in sorted(set(ps['inputs']) & set(vs['outputs'])):
        v, p = vs['outputs'][loc], ps['inputs'][loc]
        if v['type'] != p['type'] or v['qualifiers'] != p['qualifiers']:
            different.append({'location': loc, 'vertex': v, 'fragment': p})
    return {'missing_locations': missing, 'potential_type_or_interpolation_mismatches': different,
            'unknowns': vs['unknowns'] + ps['unknowns']}


def read_stage(path):
    metadata = json.loads(path.read_text())
    if not isinstance(metadata, dict) or 'key' not in metadata:
        return None
    msl_path = path.with_suffix('.metal')
    source = msl_path.read_text()
    ins, unknown1 = fields(source, 'main0_in')
    outs, unknown2 = fields(source, 'main0_out')
    attrs, unknown3 = fields(source, 'main0_in', 'attribute')
    if '[[stage_in]]' in source and not re.search(r'\bstruct\s+main0_in\s*\{', source):
        unknown1.append('stage_in has unexpected structure name')
    return {'metadata': metadata, 'inputs': ins, 'outputs': outs, 'attributes': attrs,
            'unknowns': unknown1 + unknown2 + unknown3,
            'source_hash': digest(msl_path), 'metadata_hash': digest(path),
            'metallib_exists': path.with_suffix('.metallib').is_file(),
            'driver_mentions': sorted(set(re.findall(r'\b(?:vp|fp)_c([02])\b', source)))}


def read_success_ledger(path, text=None):
    """Decode identities in pso_skey, not native pointer-dependent pso_key contents.

    Current ABI size 432 was checked with offsetof/sizeof against nvn_pso_skey.h;
    another layout is unknown and rejected. R is appended only after PSO success.
    """
    pairs, unknown, stages = set(), [], set()
    records = 0
    for line in (path.read_text() if text is None else text).splitlines():
        values = line.split('\t')
        if values[0] == 'S' and len(values) >= 3:
            stages.add(values[1])
        if values[0] != 'R' or len(values) != 2:
            continue
        try:
            raw = bytes.fromhex(values[1])
            if len(raw) != 432:
                raise ValueError('unknown pso_skey ABI')
            vertex = raw[:24].split(b'\0', 1)[0].decode('ascii')
            fragment = raw[24:48].split(b'\0', 1)[0].decode('ascii')
            if not re.fullmatch(r'[a-f0-9]{16}_b', vertex):
                raise ValueError('unknown vertex key')
            if fragment and not re.fullmatch(r'[a-f0-9]{16}_b', fragment):
                raise ValueError('unknown fragment key')
        except (ValueError, UnicodeError) as error:
            unknown.append(str(error))
            continue
        records += 1
        pairs.add((vertex, fragment))
    return pairs, records, stages, unknown


def pair_findings(pairs, stages):
    findings, unknown = [], []
    for vertex, fragment in sorted(pairs):
        if not fragment:
            continue
        if vertex not in stages or fragment not in stages:
            unknown.append([vertex, fragment])
            continue
        result = compare(stages[vertex], stages[fragment])
        if result['missing_locations'] or result['potential_type_or_interpolation_mismatches'] or result['unknowns']:
            findings.append({'vertex': vertex, 'fragment': fragment, **result})
    return findings, unknown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    cache = root / 'work/build/cache/metal_shader_cache' / CHAIN
    stages = {}
    for path in sorted(cache.glob('*.json')):
        item = read_stage(path)
        if item:
            stages[item['metadata']['key']] = item
    pair_path = root / 'third_party/nxnative/dm/games/01001B300B9BE000/shader_pairs.tsv'
    candidates = {tuple(x + '_b' for x in line.split()) for line in pair_path.read_text().splitlines()
                  if line.strip() and not line.startswith('#')}
    candidate_findings, candidate_unknown = pair_findings(candidates, stages)
    ledger_path = root / 'work/run/pso_user.tsv'
    ledger_bytes = ledger_path.read_bytes()
    success_pairs, success_records, loaded_stages, ledger_unknown = read_success_ledger(ledger_path, ledger_bytes.decode())
    success_findings, success_unknown = pair_findings(success_pairs, stages)
    log_path = root / 'work/run/app.log'
    log_bytes = log_path.read_bytes()
    log = log_bytes.decode(errors='replace')
    failures = Counter(re.findall(r'建渲染管线失败（顶点 (\S+) 片元 (\S+)）：([^\n]+)', log))
    metadata = [s['metadata'] for s in stages.values()]
    binds = [b for d in metadata for b in d['bindings']]
    notes = [{'key': d['key'], 'notes': [n for n in d['notes'] if n != '无配对 PC 反射，查询按缺省']}
             for d in metadata if any(n != '无配对 PC 反射，查询按缺省' for n in d['notes'])]
    integral = [{'key': key, 'attributes': {loc: attr for loc, attr in s['attributes'].items()
                 if re.match(r'(uint|int|ushort|short|uchar|char)', attr['type'])}}
                for key, s in stages.items() if s['metadata']['stage'] == 'vs'
                and any(re.match(r'(uint|int|ushort|short|uchar|char)', a['type']) for a in s['attributes'].values())]
    source_receipt = root / 'work/shaders/cpk-receipt.json'
    package_receipt = root / 'work/shaders/package-receipt.json'
    receipt_names = {x['output']: x['name'] for x in json.loads(source_receipt.read_text())['extracted']}
    warning_lines = [line for line in log.splitlines() if any(w in line for w in ('顶点属性格式', '贴图类型不符', '未映射', '驱动常量', '读不到着色器'))]
    report = {
        'chain': CHAIN,
        'evidence': {**{str(p.relative_to(root)): digest(p) for p in (pair_path, source_receipt, package_receipt)},
            str(ledger_path.relative_to(root)): hashlib.sha256(ledger_bytes).hexdigest(),
            str(log_path.relative_to(root)): hashlib.sha256(log_bytes).hexdigest()},
        'live_snapshot_bytes': {'pso_user.tsv': len(ledger_bytes), 'app.log': len(log_bytes)},
        'inventory': {'stages': len(stages), 'by_stage': dict(Counter(d['stage'] for d in metadata)),
            'missing_metallibs': [k for k, s in stages.items() if not s['metallib_exists']],
            'bindings': dict(Counter(b['kind'] for b in binds)),
            'texture_types': dict(Counter(b['msl_type'] for b in binds if b['kind'] == 'tex')),
            'default_pc_reflection': sum('无配对 PC 反射，查询按缺省' in d['notes'] for d in metadata),
            'extra_default_notes': notes, 'reported_driver_reads': sum(bool(d['drv_reads']) for d in metadata),
            'reported_unfillable_driver_constants': sum(bool(d['drv_unfillable']) for d in metadata),
            'msl_driver_mentions': [k for k, s in stages.items() if s['driver_mentions']],
            'constant_c1_stages': sum(bool(d['c1']) for d in metadata),
            'padded_vertex_stages': sum(bool(d['vs_pad']) for d in metadata),
            'integral_attribute_vertex_stages': len(integral),
            'integral_attribute_candidates': integral,
            'parse_unknowns': {k: s['unknowns'] for k, s in stages.items() if s['unknowns']}},
        'conservative_container_pairs': {'count': len(candidates), 'findings': candidate_findings,
            'unknown_stage_pairs': candidate_unknown, 'not_runtime_observations': True},
        'successful_pipeline_history': {'records': success_records, 'unique_pairs': len(success_pairs),
            'unique_stage_loads': len(loaded_stages), 'findings': success_findings,
            'unknown_stage_pairs': success_unknown, 'unparsed_records': ledger_unknown,
            'pairs_outside_container_table': [list(pair) for pair in sorted(success_pairs - candidates)],
            'not_per_session_or_visual_validation': True},
        'current_log_actual_pipeline_failures': [dict(vertex=v, fragment=p, message=m, occurrences=n,
             in_container_pair_table=(v, p) in candidates,
             interface=compare(stages[v], stages[p]) if v in stages and p in stages else {'unknown': True})
             for (v, p, m), n in sorted(failures.items())],
        'current_log_warning_lines': warning_lines,
        'limitations': ['Stage compilation and file presence do not establish pipeline linking or visual correctness.',
            'Conservative within-container pairs omit runtime combinations across containers and include combinations never drawn.',
            'PSO user ledger is append-only across runs and records success, not failed or never visited scenes.',
            'Missing varying declarations are definite interface gaps; type/interpolation differences are candidates requiring Metal linker validation.',
            'No driver reads in emitted MSL does not establish correctness of the original translation queries.',
            'Texture target and vertex format compatibility require runtime state; integer inputs are candidates, not failures.',
            'This does not prove all ROM shader formats or dynamically generated stages were inventoried.'],
        'stages': {k: {'stage': s['metadata']['stage'], 'source': s['metadata']['source'],
                      'representative_container': receipt_names.get(s['metadata']['pc_paired'].split('@')[0]),
                      'metadata_sha256': s['metadata_hash'], 'msl_sha256': s['source_hash']}
                   for k, s in stages.items()}}
    output = args.output or root / 'work/audit/shader-interfaces.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    summary = {'stage_count': len(stages), 'candidate_pairs': len(candidates),
        'candidate_pairs_missing_varyings': sum(bool(f['missing_locations']) for f in candidate_findings),
        'candidate_type_or_interpolation_pairs': sum(bool(f['potential_type_or_interpolation_mismatches']) for f in candidate_findings),
        'runtime_success_records': success_records, 'runtime_success_unique_pairs': len(success_pairs),
        'runtime_success_interface_findings': len(success_findings),
        'current_log_failed_pairs': len({(v, p) for v, p, _ in failures}), 'output': str(output)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
