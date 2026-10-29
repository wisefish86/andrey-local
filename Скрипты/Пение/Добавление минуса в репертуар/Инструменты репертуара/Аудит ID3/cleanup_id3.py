from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path
from collections import Counter
from mutagen.id3 import ID3, ID3NoHeaderError

ROOT = Path(r'D:\YandexDisk\Проекты\Пение\Минусы\1. Основной репертуар')
DROP = {'WOAF','WOAR','WXXX','WCOP','TCOP','TOPE','TSSE','GEOB','TIT3','TKEY','TCMP','TDEN','TENC'}

def unwanted(f):
    return f.FrameID in DROP or (f.FrameID == 'PRIV' and f.owner == 'XMP')

def main():
    p = argparse.ArgumentParser(description='ID3 cleanup: preview by default; no automatic backup')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--root', type=Path, default=ROOT)
    args = p.parse_args()
    if not args.root.is_dir():
        p.error(f'Folder not found: {args.root}')
    rows, errors, totals = [], [], Counter()
    for path in sorted(args.root.rglob('*.mp3')):
        if '֎' not in path.name:
            continue
        try:
            tags = ID3(path)
            frames = [f for f in tags.values() if unwanted(f)]
            if not frames:
                continue
            ids = ['PRIV:XMP' if f.FrameID == 'PRIV' else f.FrameID for f in frames]
            if args.apply:
                for f in frames:
                    del tags[f.HashKey]
                tags.save(path, v2_version=tags.version[1])
                if any(unwanted(f) for f in ID3(path).values()):
                    raise RuntimeError('Post-save verification failed')
            totals.update(ids)
            rows.append({'file': str(path.relative_to(args.root)), 'frames': sorted(ids)})
        except ID3NoHeaderError:
            continue
        except Exception as e:
            errors.append({'file': str(path), 'error': repr(e)})
            if args.apply:
                break
    output_dir = Path(__file__).resolve().parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / ('cleanup_apply_' if args.apply else 'cleanup_preview_')
    output = Path(str(output)+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
    output.write_text(json.dumps({'mode': 'apply' if args.apply else 'preview', 'files': rows, 'counts': totals, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Files:',len(rows), 'Errors:',len(errors), 'Report:',output)
    for k,v in totals.most_common():
        print(k, v)
    if errors:
        print('First error:',errors[0])
    return int(bool(errors))
if __name__ == '__main__':
    raise SystemExit(main())
