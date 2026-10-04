
# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[5]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import zipfile,json,hashlib
from pathlib import Path
root=Path(str(_XEXORIA_ASSET_SOURCE / 'sources/cc0/quaternius-farm-animal-2018-author-mirror'))
archive=root/'Farm Animals by @Quaternius.zip';out=root/'original-extracted'
sha=lambda b:hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(archive) as z:
    bad=z.testzip()
    if bad:raise RuntimeError('Archive CRC failed '+bad)
    files=[];licences=[]
    for item in z.infolist():
        if item.is_dir():continue
        dest=(out/item.filename).resolve()
        if not dest.is_relative_to(out.resolve()):raise RuntimeError('Archive unsafe path '+item.filename)
        data=z.read(item);files.append({'file':item.filename,'bytes':len(data),'sha256':sha(data)})
        if any(x in item.filename.lower() for x in ['licen','readme','copying']):licences.append({'file':item.filename,'text':data.decode('utf8',errors='replace')})
        if dest.exists():
            if sha(dest.read_bytes())!=sha(data):raise RuntimeError('Immutable extractedsource mismatch '+str(dest))
        else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
receipt={'schema':'xexoria.cc0-author-mirror-intake/1','start_ict':'2026-10-03 17:12:53','author':'quaternius','published':'2018-06-08','source_url':'https://opengameart.org/content/lowpoly-animated-farm-animal-pack','archive_url':'https://opengameart.org/sites/default/files/Farm%20Animals%20by%20%40Quaternius.zip','archive':str(archive),'archive_sha256':sha(archive.read_bytes()),'archive_bytes':archive.stat().st_size,'crc':'PASS','files':files,'licence_documents':licences,'source_immutable':True,'autoexec':'Never enabled; Blender will use --disable-autoexec.'}
e=Path('planning/evidence/blueprint-p0-20261003/cc0/sheep-v1');e.mkdir(parents=True,exist_ok=True)
(e/'archive-intake.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print(json.dumps({'sha256':receipt['archive_sha256'],'files':len(files),'sheep':[f for f in files if 'sheep' in f['file'].lower()],'licences':licences},ensure_ascii=False))
