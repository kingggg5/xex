"""Read-only rAthena research index. No scripts run; no game data is imported.

Counts are declared source records, NOT a merged effective runtime database.
Uses the already pinned PyYAML dependency in requirements-rathena-items.txt.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'references/rathena'
OUTPUT = ROOT / 'exports/ragnarok-research'
LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
SCRIPT_FIELDS = {'Script', 'EquipScript', 'UnEquipScript'}
ID_KEYS = ('Id', 'ID', 'Group', 'Job', 'Name', 'Level', 'Type', 'Map', 'Item', 'Skill')


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def mode_for(path):
    parts = path.parts
    if 'pre-re' in parts:
        return 'pre-re'
    if 're' in parts:
        return 're'
    if 'import-tmpl' in parts:
        return 'import-template'
    return 'common'


def strip_comments(text):
    # Preserve newlines and quoted literals; avoid matching declarations in comments.
    return re.sub(r'"(?:\\.|[^"\\])*"|/\*[\s\S]*?\*/|//[^\n]*',
                  lambda m: m[0] if m[0].startswith('"') else '\n' * m[0].count('\n'), text)


def field_paths(value, prefix='', depth=0):
    if depth > 12:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            name = f'{prefix}.{key}' if prefix else str(key)
            yield name
            if key not in SCRIPT_FIELDS:
                yield from field_paths(child, name, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from field_paths(child, prefix + '[]', depth + 1)


def main():
    assert (SOURCE / 'LICENSE').is_file(), 'missing pinned source checkout'
    OUTPUT.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, check=True).stdout.strip()
    schemas = defaultdict(set)
    files, imports, errors = [], [], []
    counts = Counter()
    script_counts = Counter()
    relations = Counter()
    key_counts = Counter()
    duplicates = []
    seen_keys = set()
    item_totals = Counter()
    records_written = 0
    sample = None
    yaml_paths = sorted((SOURCE / 'db').rglob('*.yml')) + sorted((SOURCE / 'npc').rglob('*.yml'))
    with (OUTPUT / 'records.jsonl').open('w', encoding='utf-8') as records:
        for path in yaml_paths:
            rel = path.relative_to(SOURCE).as_posix()
            raw = path.read_bytes()
            receipt = {'path': rel, 'mode': mode_for(path.relative_to(SOURCE)),
                       'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                       'type': '', 'version': '', 'body_records': 0, 'status': 'parsed'}
            try:
                doc = yaml.load(raw.decode('utf-8-sig'), Loader=LOADER)
                if not isinstance(doc, dict):
                    raise ValueError('not a top-level mapping')
                header = doc.get('Header') or {}
                receipt['type'] = header.get('Type', 'NO_HEADER')
                receipt['version'] = header.get('Version', '')
                body = doc.get('Body') or []
                if not isinstance(body, list):
                    raise ValueError('Body is not a sequence')
                receipt['body_records'] = len(body)
                for imp in (doc.get('Footer') or {}).get('Imports', []) or []:
                    imports.append({'source': rel, 'path': imp.get('Path', ''),
                                    'mode': imp.get('Mode', ''),
                                    'exists': (SOURCE / imp.get('Path', '')).is_file()})
                for index, row in enumerate(body):
                    if not isinstance(row, dict):
                        raise ValueError(f'Body[{index}] is not a mapping')
                    kind, mode = receipt['type'], receipt['mode']
                    counts[(mode, kind)] += 1
                    schemas[kind].update(field_paths(row))
                    id_key = next((k for k in ID_KEYS if k in row), '')
                    identity = row.get(id_key) if id_key else index
                    key = (mode, kind, id_key, str(identity))
                    key_counts[(mode, kind)] += 1
                    if key in seen_keys:
                        duplicates.append({'mode': mode, 'type': kind, 'key': str(identity), 'path': rel})
                    seen_keys.add(key)
                    scripts = {k: {'sha256': hashlib.sha256(str(row[k]).encode()).hexdigest(),
                                   'characters': len(str(row[k]))}
                               for k in SCRIPT_FIELDS if row.get(k)}
                    script_counts[(mode, kind)] += bool(scripts)
                    if kind == 'ITEM_DB':
                        item_totals[(mode, str(row.get('Type', 'missing')))] += 1
                    if kind == 'MOB_DB':
                        for name in ('Drops', 'MvpDrops'):
                            relations[(mode, name)] += len(row.get(name) or [])
                    if kind == 'ITEM_GROUP_DB':
                        for group in row.get('SubGroups', []) or []:
                            relations[(mode, 'box_subgroups')] += 1
                            relations[(mode, 'box_entries')] += len(group.get('List') or [])
                            relations[(mode, 'box_algorithm_' + str(group.get('Algorithm', 'SharedPool(default)')))] += 1
                    if kind == 'SKILL_TREE_DB':
                        relations[(mode, 'skill_tree_entries')] += len(row.get('Tree') or [])
                    record = {'source_commit': commit, 'source_file': rel,
                              'source_pointer': f'/Body/{index}', 'mode': mode, 'database_type': kind,
                              'key_field': id_key, 'key': identity,
                              'name': row.get('Name', row.get('AegisName', row.get('Title', ''))),
                              'fields': sorted(map(str, row.keys())), 'script_evidence': scripts,
                              'status': 'indexed_not_effective_runtime_or_reimplemented'}
                    records.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
                    records_written += 1
                    if kind == 'ITEM_DB' and mode == 're' and row.get('Id') == 18180:
                        sample = {k: row.get(k) for k in ('Id','AegisName','Type','SubType','Attack','MagicAttack','Weight','Slots','WeaponLevel','EquipLevelMin','Buy','Sell')}
                        sample['script_matk_bonus_135_present'] = bool(re.search(r'bonus\s+bMatk\s*,\s*135\s*;', row.get('Script','')))
                        sample['source_file'] = rel
                        sample['source_pointer'] = f'/Body/{index}'
            except (yaml.YAMLError, UnicodeError, ValueError, TypeError, AttributeError) as exc:
                receipt['status'] = 'error'
                errors.append({'path': rel, 'error': str(exc)[:250]})
            files.append(receipt)

    # Lexical source index. Not a VM, preprocessor, or effective load graph.
    declarations, npc_files, conf_refs = [], [], []
    declaration_counts = Counter()
    pattern = re.compile(r'^([^\t\n]+)\t+(script|shop|cashshop|itemshop|pointshop|marketshop|warp|monster|boss_monster|mapflag|duplicate\([^\n\t]*\))\t+([^\t\n]*)(?:\t|$)', re.M)
    for path in sorted((SOURCE / 'npc').rglob('*')):
        if not path.is_file() or path.suffix not in ('.txt', '.conf'):
            continue
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig', errors='replace')
        clean = strip_comments(text)
        rel = path.relative_to(SOURCE).as_posix()
        npc_files.append({'path': rel, 'mode': mode_for(path.relative_to(SOURCE)),
                          'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                          'decode_replacements': text.count('\ufffd')})
        for match in pattern.finditer(clean):
            location, kind, name = match.groups()
            family = 'duplicate' if kind.startswith('duplicate(') else kind
            declaration_counts[family] += 1
            declarations.append({'source_file': rel, 'line': clean.count('\n',0,match.start())+1,
                                 'kind': family, 'location': location.strip(), 'name_or_value': name.strip(),
                                 'loaded_status': 'unknown_static_declaration_only'})
        if path.suffix == '.conf':
            for line, text_line in enumerate(clean.splitlines(), 1):
                m = re.match(r'^\s*(npc|import)\s*:\s*([^\s]+)', text_line)
                if m:
                    conf_refs.append({'source_file': rel, 'line': line, 'directive': m[1],
                                      'target': m[2], 'exists': (SOURCE/m[2]).is_file(),
                                      'activation': 'configuration_and_mode_not_resolved'})

    maps, last_id = [], 0
    for line, entry in enumerate((SOURCE/'db/map_index.txt').read_text().splitlines(),1):
        entry = entry.split('//',1)[0].strip()
        if not entry:
            continue
        parts = entry.split()
        last_id = int(parts[1]) if len(parts)>1 else last_id+1
        maps.append({'map_name':parts[0], 'index':last_id, 'source_line':line, 'visual_asset_verified':False})
    source_cpp = [{'path':p.relative_to(SOURCE).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in sorted((SOURCE/'src/map').rglob('*')) if p.is_file() and p.suffix in ('.cpp','.hpp')]
    text_tables = []
    for path in sorted((SOURCE/'db').rglob('*.txt')):
        raw = path.read_bytes()
        clean = strip_comments(raw.decode('utf-8-sig', errors='replace'))
        text_tables.append({'path':path.relative_to(SOURCE).as_posix(),
                            'mode':mode_for(path.relative_to(SOURCE)),
                            'sha256':hashlib.sha256(raw).hexdigest(),
                            'nonempty_uncommented_lines':sum(bool(line.strip()) for line in clean.splitlines()),
                            'semantics':'line index only; format-specific interpretation pending'})
    config_files = [{'path':p.relative_to(SOURCE).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                    for p in sorted((SOURCE/'conf').rglob('*.conf'))]
    write_csv(OUTPUT/'database-files.csv',files,['path','mode','sha256','bytes','type','version','body_records','status'])
    write_csv(OUTPUT/'npc-declarations.csv',declarations,['source_file','line','kind','location','name_or_value','loaded_status'])
    write_csv(OUTPUT/'map-index.csv',maps,['map_name','index','source_line','visual_asset_verified'])
    write_csv(OUTPUT/'npc-load-references.csv',conf_refs,['source_file','line','directive','target','exists','activation'])
    (OUTPUT/'imports.json').write_text(json.dumps(imports,indent=2),encoding='utf-8')
    (OUTPUT/'field-catalog.json').write_text(json.dumps({k:sorted(v) for k,v in sorted(schemas.items())},indent=2),encoding='utf-8')
    (OUTPUT/'npc-files.json').write_text(json.dumps(npc_files,indent=2),encoding='utf-8')
    (OUTPUT/'mechanics-files.json').write_text(json.dumps(source_cpp,indent=2),encoding='utf-8')
    (OUTPUT/'text-database-files.json').write_text(json.dumps(text_tables,indent=2),encoding='utf-8')
    (OUTPUT/'config-files.json').write_text(json.dumps(config_files,indent=2),encoding='utf-8')
    summary={'generated_at':datetime.now(timezone.utc).isoformat(),'source_commit':commit,
             'source_license':'GPL-3.0-or-later; see references/rathena/LICENSE and per-file headers',
             'scope':'All YAML beneath db/ and npc/; NPC text/conf declaration scan; src/map C++ file manifest',
             'count_semantics':'Declared records; modes isolated; imports/overrides are NOT merged; no runtime activation claim',
             'database_files':len(files),'database_types':len(schemas),'records_indexed':records_written,
             'records_by_mode_and_type':[{'mode':m,'type':t,'records':v,'records_with_scripts':script_counts[m,t]}
                                         for (m,t),v in sorted(counts.items())],
             'items_by_mode_and_type':[{'mode':m,'type':t,'records':v} for (m,t),v in sorted(item_totals.items())],
             'relationships':[{'mode':m,'kind':k,'count':v} for (m,k),v in sorted(relations.items())],
             'map_entries':len(maps),'npc_text_conf_files':len(npc_files),'npc_declarations':dict(declaration_counts),
             'cpp_mechanics_files':len(source_cpp),'parse_errors':errors,'duplicate_source_keys':duplicates,
             'text_database_files':len(text_tables),'configuration_files':len(config_files),
             'weapon_sample_18180':sample,
             'limitations':['NPC scan is lexical, not runtime execution; dynamically created actors/shops not resolved',
                            'Missing import paths may be optional customization; not automatically an error',
                            'Counts cannot be added across Renewal and Pre-Renewal as unique live content',
                            'Script behavior, formula parity, client visuals and every web record remain unverified']}
    (OUTPUT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('source_commit','database_files','database_types','records_indexed','map_entries','npc_text_conf_files','npc_declarations','cpp_mechanics_files','parse_errors')},indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
