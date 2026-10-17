"""Package the player's extracted game icon; generated artwork stays in work/Gen."""
import json
from pathlib import Path
import subprocess


def png(source, destination, pixels):
    source=Path(source).resolve(strict=True);destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['sips','-s','format','png','-z',str(pixels),str(pixels),
                    str(source),'--out',str(destination)],check=True,stdout=subprocess.DEVNULL)


def ios_catalog(source, destination):
    catalog=Path(destination);icons=catalog/'AppIcon.appiconset';icons.mkdir(parents=True,exist_ok=True)
    metadata={'info':{'author':'xcode','version':1}}
    (catalog/'Contents.json').write_text(json.dumps(metadata,indent=2)+'\n')
    png(source,icons/'icon-1024.png',1024)
    metadata['images']=[{'filename':'icon-1024.png','idiom':'universal','platform':'ios','size':'1024x1024'}]
    (icons/'Contents.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return icons/'icon-1024.png'


def mac_icns(source, destination, staging):
    staging=Path(staging);staging.mkdir(parents=True,exist_ok=True)
    iconset=staging/'AppIcon.iconset';iconset.mkdir(exist_ok=True)
    for points in (16,32,128,256,512):
        for scale in (1,2):
            suffix='@2x' if scale==2 else ''
            png(source,iconset/f'icon_{points}x{points}{suffix}.png',points*scale)
    subprocess.run(['iconutil','-c','icns',str(iconset),'-o',str(destination)],check=True)
