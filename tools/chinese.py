#!/usr/bin/env python3
"""Install the local Simplified Chinese DLC and update only locale preferences."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import time
from dr3 import ROOT, WORK, run, save, sha, check_modules

TITLE = '01001b300b9bf00b'
INDEX = 11
LOCALE = 19  # main+0xa4bb10: locale table entry 19 is ztCN (enUS is entry 2).

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keys', type=Path)
    parser.add_argument('--nsp', type=Path)
    parser.add_argument('--preferences', action='store_true')
    args = parser.parse_args()
    final = WORK / 'aoc' / str(INDEX)
    if args.nsp:
        if not args.keys:
            parser.error('--keys is required when importing --nsp')
        stage = WORK / 'aoc.partial' / str(INDEX)
        if not final.exists():
            # A completed prior local extraction may be resumed after validating the inventory.
            if not stage.exists():
                run([WORK / 'tools/nx_extract/nx_extract', args.keys.resolve(strict=True), '--aoc',
                     args.nsp.resolve(strict=True), stage], WORK / 'logs/extract-zhCN.log')
            log = (WORK / 'logs/extract-zhCN.log').read_text()
            if TITLE not in log.lower():
                raise ValueError('Unexpected DLC identity')
            paths = sorted(stage.glob('*.cpk'))
            required = {'ztCN_' + n + '.cpk' for n in ['CoreCommon', 'ClientCommon', 'Common',
                        'CommonCutscene', *['Act' + str(i) for i in range(1,6)],
                        *['Act' + str(i) + 'Cutscene' for i in range(1,6)]]}
            if {p.name for p in paths} != required:
                raise ValueError('Incomplete Chinese archive inventory')
            receipt = {'title_id': TITLE, 'aoc_index': INDEX, 'locale': 'ztCN',
                       'source_sha256': sha(args.nsp), 'files': [
                       {'name':p.name, 'bytes':p.stat().st_size, 'sha256':sha(p)} for p in paths]}
            final.parent.mkdir(exist_ok=True)
            stage.rename(final)
            save(final.parent / 'chinese-receipt.json', receipt)
        print('Chinese DLC installed:', final)
    if args.preferences:
        check_modules()
        processes = subprocess.check_output(['ps', '-axo', 'command'], text=True).splitlines()
        if any(str(WORK / 'macapp/DR3 Mobile.app/Contents/MacOS/dmhost') in s or
               (str(ROOT / 'third_party/nxnative/dm/host/dmhost') in s) for s in processes):
            raise ValueError('Close the native game before updating preferences')
        if not final.is_dir():
            raise ValueError('Install the Chinese DLC first')
        folder = WORK / 'run/save'
        path = folder / 'prefs.dat'
        raw = path.read_bytes()
        changed = raw
        for field in (b'SelectedTextLocale', b'SelectedAudioLocale'):
            changed, count = re.subn(rb'(?m)^' + field + rb' "[0-9]+"', field + b' "19"', changed)
            if count != 1:
                raise ValueError('Expected exactly one locale preference: ' + field.decode())
        backup = WORK / 'run/backups' / time.strftime('%Y%m%d-%H%M%S-before-chinese')
        backup.parent.mkdir(exist_ok=True)
        shutil.copytree(folder, backup)
        temp = path.with_suffix('.language.tmp')
        temp.write_bytes(changed); temp.replace(path)
        save(WORK / 'run/chinese-settings.json', {'locale':LOCALE, 'backup':str(backup),
             'prefs_before_sha256': hashlib.sha256(raw).hexdigest(), 'prefs_after_sha256':sha(path)})
        print('Text/audio locale set to ztCN; save backup:', backup)

if __name__ == '__main__':
    main()
