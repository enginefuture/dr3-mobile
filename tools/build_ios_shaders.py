#!/usr/bin/env python3
"""Compile the complete verified D3 MSL corpus with the iPhoneOS compiler."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from dr3 import WORK, UPSTREAM, check_modules, check_shaders, shader_chain, sha, save

sys.path[:0] = [str(UPSTREAM/'dm/ios/tools'), str(UPSTREAM/'dm/gfx/tools')]
import ios_metal
import dmsh_fetch
from vertex_fetch_variants import adapt_source, export_sources, observed_signatures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs',type=int,default=6)
    args=parser.parse_args()
    check_modules();source=check_shaders();chain=shader_chain()
    target=WORK/'shaders/ios'/source.name;target.mkdir(parents=True,exist_ok=True)
    compiler=subprocess.check_output(['xcrun','-sdk','iphoneos','metal','--version'],text=True).strip()
    sdk=subprocess.check_output(['xcrun','-sdk','iphoneos','--show-sdk-version'],text=True).strip()
    identity=hashlib.sha256((compiler+sdk+ios_metal.RECORD).encode()).hexdigest()
    jobs=[];metas={};inputs={}
    for src in sorted(source.glob('*_b.metal')):
        meta=json.loads(src.with_suffix('.json').read_text())
        if meta['chain']!=chain or meta['key']!=src.stem:raise ValueError('Shader identity mismatch: '+src.name)
        inputs[src.name]=sha(src);inputs[src.with_suffix('.json').name]=sha(src.with_suffix('.json'))
        text=src.read_text();jobs.append((src.stem,text));metas[src.stem]=dict(meta,chain_metal=ios_metal.RECORD)
        if src.with_name(src.stem+'f.metallib').exists():
            variant,info=dmsh_fetch.variant(text,meta['bindings'],om_only_ok=True)
            if not variant or info!=meta.get('fetch'):raise ValueError('Fetch variant differs: '+src.name)
            jobs.append((src.stem+'f',variant))
    expected=len(json.loads((source/'_b_build.json').read_text()))
    if len(metas)!=expected or not metas:raise ValueError('Incomplete MSL corpus')
    def build(job):
        name,text=job;src=target/(name+'.metal');lib=target/(name+'.metallib');record=target/(name+'.build.json')
        digest=hashlib.sha256(text.encode()).hexdigest()
        old=json.loads(record.read_text()) if record.exists() else {}
        if old.get('source_sha256')!=digest or old.get('compiler')!=identity or not lib.exists() or old.get('metallib_sha256')!=sha(lib):
            src.write_text(text);air=src.with_suffix('.air');temp=lib.with_suffix('.metallib.tmp')
            ios_metal.compile(str(src),str(air),str(temp));os.replace(temp,lib);air.unlink()
            save(record,dict(source_sha256=digest,compiler=identity,metallib_sha256=sha(lib)))
        if name in metas:save(target/(name+'.json'),metas[name])
        return name
    names=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        for name in executor.map(build,jobs):
            names.append(name)
            if len(names)%100==0:print(f'iPhoneOS shaders {len(names)}/{len(jobs)}',flush=True)
    for name,digest in inputs.items():
        if sha(source/name)!=digest:raise ValueError('Source changed while compiling: '+name)
    if shader_chain()!=chain:raise ValueError('Host chain changed during compilation')
    files={name+'.metallib':sha(target/(name+'.metallib')) for name in names}
    files.update({name+'.json':sha(target/(name+'.json')) for name in metas})
    # Export this platform's exact source and compile its own fetch shims.
    manifests=export_sources(target)
    requested=observed_signatures(source,WORK/'run/pso_user.tsv')
    requested.update([('18f2aadcec113d49_b',0x10),('88ba806f61d19fae_b',0x4)])
    for key,signature in sorted(requested):
        text=adapt_source((target/(key+'.vsrc')).read_text(),signature)
        name=f'{key}_vf{signature:016x}';build((name,text))
        lib=target/(name+'.metallib');files[lib.name]=sha(lib)
        manifest=manifests[key]
        manifest['variants'][f'{signature:016x}']=dict(file=lib.name,source_sha256=hashlib.sha256(text.encode()).hexdigest(),library_sha256=sha(lib),sdk='iphoneos')
        save(target/(key+'.vsrc.json'),manifest)
    for src in list(target.glob('*.vsrc'))+list(target.glob('*.vsrc.json')):
        files[src.name]=sha(src)
    save(WORK/'shaders/ios-build.json',dict(schema=1,platform='iphoneos',chain=chain,sdk=sdk,compiler=compiler,
         compiler_record=ios_metal.RECORD,source_files=inputs,base_stages=len(metas),fetch_variants=len(names)-len(metas),vertex_variants=len(requested),files=files,
         limitations=['Compilation is not device execution or complete rendering equivalence.']))
    subprocess.run([sys.executable,str(UPSTREAM/'dm/gfx/tools/c1_guard.py'),str(target),str(WORK/'shaders/ios-c1_full.tsv')],check=True)
    print(f'iPhoneOS: {len(names)} libraries compiled; receipt work/shaders/ios-build.json',flush=True)


if __name__=='__main__':main()
