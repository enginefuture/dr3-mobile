#!/usr/bin/env python3
"""Build/run upstream NVN GPU regression fixture with production big-stack entry."""
from pathlib import Path
import json
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
up = ROOT / 'third_party/nxnative/dm'
out = ROOT / 'work/audit/nvn-command-sync'
out.mkdir(parents=True, exist_ok=True)
fixture = out / 't_nvn-fixture.c'
fixture.write_text('#include "' + str(up / 'gfx/tests/t_nvn.c') + '"\n'
                   'int dm_guest_as_contains(uintptr_t pointer){(void)pointer;return 0;}\n')
gfx = sorted([*up.glob('gfx/nvn/*.c'), *up.glob('gfx/nvn/*.m'), *up.glob('gfx/nvn/*.S'),
              *up.glob('gfx/tex/*.c'), *up.glob('gfx/tex/*.m')])
command = ['clang', '-O1', '-g', '-Wall', '-Wno-unused-function', '-Wno-unused-variable',
           '-Wno-deprecated-declarations', '-fobjc-arc',
           '-I' + str(up / 'gfx/nvn/include'), '-I' + str(up / 'host/gen/01001B300B9BE000'),
           '-I' + str(up / 'games/01001B300B9BE000'), str(fixture), str(up / 'host/crash.c'),
           str(up / 'host/hle_bigstack.c'), *[str(p) for p in gfx if p.name != 'hle_nvn.c']]
for framework in ['Metal', 'MetalFX', 'Foundation', 'QuartzCore', 'ImageIO', 'CoreGraphics', 'UniformTypeIdentifiers']:
    command += ['-framework', framework]
binary = out / 't_nvn'
command += ['-o', str(binary)]
(out / 'upstream-build-command.json').write_text(json.dumps(command, indent=2) + '\n')
with (out / 'upstream-build.log').open('w') as log:
    compiled = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
if compiled.returncode:
    print((out / 'upstream-build.log').read_text()[-8000:]);sys.exit(compiled.returncode)
with (out / 'upstream-run.log').open('w') as log:
    result = subprocess.run([str(binary)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=60)
print((out / 'upstream-run.log').read_text()[-14000:])
sys.exit(result.returncode)
