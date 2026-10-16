"""Validate a public workflow Skill and optionally refresh its file manifest."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'skill-package-manifest.json'
EXCLUDED = {'node_modules', '__pycache__', '.git', '.cache', 'out', 'output', 'qa'}
ALLOWED = {'.md', '.py', '.json', '.jsonc', '.yaml', '.yml', '.ts', '.tsx', '.mjs', '.mts', '.cjs', '.css', '.html', '.svg', '.txt', '.ps1', '.lock'}
PRIVATE = [r'(?i)[A-Z]:[\\/]Users[\\/][^/\\\s]+[\\/]', r'codex-remote-attachments', r'gh[pousr]_[A-Za-z0-9]{24,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-manifest', action='store_true', help='Refresh only the public file inventory after validation')
    args = parser.parse_args()
    errors, files = [], []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path == MANIFEST or any(p in EXCLUDED for p in path.relative_to(ROOT).parts):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if path.name not in {'.gitignore', '.gitattributes', '.gitkeep'} and path.suffix not in ALLOWED:
            errors.append(f'Unexpected public-file type: {rel}')
        if path.stat().st_size > 2_000_000:
            errors.append(f'Unexpected large file: {rel}')
        data = path.read_bytes()
        try:
            content = data.decode('utf8')
        except UnicodeDecodeError:
            errors.append(f'Not UTF8 text: {rel}')
            continue
        if b'\r\n' in data:
            errors.append(f'Normalize LF before manifest generation: {rel}')
        if path.name != 'validate_package.py':
            for pattern in PRIVATE:
                if re.search(pattern, content):
                    errors.append(f'Private path or credential pattern: {rel}')
        if path.suffix == '.json':
            try:
                json.loads(content)
            except ValueError:
                errors.append(f'Invalid JSON: {rel}')
        if path.suffix == '.md':
            for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
                target = unquote(link.split('#',1)[0].split(' ',1)[0].strip('<>'))
                if target and not re.match(r'[a-z][a-z0-9+.-]*:', target, re.I) and not (path.parent / target).exists():
                    errors.append(f'Broken local link in {rel}: {target}')
        files.append({'path':rel, 'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()})
    skill = (ROOT / 'SKILL.md').read_text(encoding='utf8')
    if not re.match(r'^---\nname: math-explainer-animation\ndescription: .+\n---\n', skill):
        errors.append('Missing or invalid Skill frontmatter')
    for required in ['agents/openai.yaml', 'assets/starter/package.json', 'assets/starter/pnpm-lock.yaml', 'scripts/init_project.py', 'scripts/analyze_audio.py', 'scripts/verify_video.py', 'scripts/browser_check.mjs', 'templates/series.json']:
        if not (ROOT / required).exists():
            errors.append(f'Missing required file: {required}')
    if errors:
        raise SystemExit('\n'.join(errors))
    inventory = {'name':'math-explainer-animation', 'version':'1.1.0', 'package_type':'workflow-skill',
                 'contains_third_party_media':False, 'contains_private_source_conversation':False,
                 'contains_vendor':False, 'contains_complete_video':False, 'files':files}
    if args.write_manifest:
        MANIFEST.write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n', encoding='utf8', newline='\n')
    elif not MANIFEST.exists() or json.loads(MANIFEST.read_text(encoding='utf8')) != inventory:
        raise SystemExit('Manifest missing or stale; review changes then use --write-manifest')
    print(json.dumps({'passed':True, 'fileCount':len(files), 'manifestVerified':True}, indent=2))

if __name__ == '__main__':
    main()
