#!/usr/bin/env python3
"""Build/run isolated production NVN command/sync Metal integration tests."""
from pathlib import Path
import json
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
up = ROOT / 'third_party/nxnative/dm'
out = ROOT / 'work/audit/nvn-command-sync'
out.mkdir(parents=True, exist_ok=True)
gfx = sorted([*up.glob('gfx/nvn/*.c'), *up.glob('gfx/nvn/*.m'), *up.glob('gfx/nvn/*.S'),
              *up.glob('gfx/tex/*.c'), *up.glob('gfx/tex/*.m')])
command = ['clang', '-O1', '-g', '-Wall', '-Wno-unused-function', '-Wno-unused-variable',
           '-Wno-deprecated-declarations', '-fobjc-arc',
           '-I' + str(up / 'gfx/nvn/include'), '-I' + str(up / 'host/gen/01001B300B9BE000'),
           '-I' + str(up / 'games/01001B300B9BE000'), str(ROOT / 'tests/test_nvn_commands.m'),
           str(up / 'host/crash.c'), str(up / 'host/hle_bigstack.c'), *[str(p) for p in gfx if p.name not in {'hle_nvn.c', 'nvn_mtl.m'}]]
for framework in ['Metal', 'MetalFX', 'Foundation', 'QuartzCore', 'ImageIO', 'CoreGraphics', 'UniformTypeIdentifiers']:
    command += ['-framework', framework]
binary = ROOT / 'work/test-nvn-commands'
command += ['-o', str(binary)]
(out / 'build-command.json').write_text(json.dumps(command, indent=2) + '\n')
with (out / 'build.log').open('w') as log:
    compiled = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
if compiled.returncode:
    print((out / 'build.log').read_text()[-8000:]);sys.exit(compiled.returncode)
with (out / 'run.log').open('w') as log:
    result = subprocess.run([str(binary)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=60)
print((out / 'run.log').read_text()[-14000:])
sys.exit(result.returncode)
