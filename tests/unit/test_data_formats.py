"""docs/data_formats.md lists every schema in common/schemas/ with a version that matches the file."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / 'docs' / 'data_formats.md'
SCHEMAS = ROOT / 'common' / 'schemas'
ROW = re.compile(r'^\|\s*`(?P<file>[^`]+\.schema\.json)`\s*\|\s*(?P<id>[^|]+?)\s*\|\s*(?P<version>[^|]+?)\s*\|')


def listed():
    rows = {}
    for line in DOC.read_text(encoding='utf-8').splitlines():
        match = ROW.match(line)
        if match:
            assert match['file'] not in rows, f"{match['file']} is listed twice"
            rows[match['file']] = match
    return rows


def test_every_schema_file_is_listed_and_nothing_else():
    on_disk = {p.name for p in SCHEMAS.glob('*.schema.json')}
    assert on_disk == set(listed())


def test_id_and_version_match_the_schema():
    for name, row in listed().items():
        props = json.loads((SCHEMAS / name).read_text(encoding='utf-8')).get('properties', {})
        document_id = props.get('schema', {}).get('const')
        version = props.get('schema_version', {}).get('const')
        expected_id = f'`{document_id}`' if document_id else 'none'
        expected_version = str(version) if version is not None else 'none'
        assert row['id'] == expected_id, f"{name}: id {row['id']} != {expected_id}"
        assert row['version'] == expected_version, f"{name}: version {row['version']} != {expected_version}"


def test_every_row_names_an_owner_and_a_reader():
    for line in DOC.read_text(encoding='utf-8').splitlines():
        if ROW.match(line):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            assert len(cells) == 5 and all(cells), line


def test_links_to_the_existing_format_docs_resolve():
    text = DOC.read_text(encoding='utf-8')
    for name in ('annotation-format.md', 'transfer-artifact.md'):
        assert f']({name})' in text
    for target in re.findall(r'\]\(([^)#]+\.md)\)', text):
        assert (DOC.parent / target).is_file(), target
