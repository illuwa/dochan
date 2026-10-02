"""Read-only inventory and paired raw-text checks for public HWP features.

Usage: /usr/bin/python3 -m scripts.probe_hwp_features /path/to/hwp-public
The corpus is never copied into the repository. Only public corpus names
and aggregate observations are printed; this is not an internal-pair probe.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import zipfile

from lxml import etree
import olefile

from dochan import Dochan
from dochan.hwp.forms import form_text, clickhere_prompt
from dochan.hwp.doc_info import DocInfoParser
from dochan.model.document import Document
from dochan.output.plain_text import to_plain_text
from dochan.hwp.header import FileHeader
from dochan.hwp.records.para_text import parse_para_text
from dochan.hwp.revisions import parse_author, parse_change, project_text_result
from dochan.hwp.section import SectionParser
from dochan.hwpx.revisions import RevisionProjector
from dochan.utils.bounded_io import MAX_OLE_DOCUMENT_SIZE, read_ole_stream, validate_file_size
from dochan.utils.safe_decompress import safe_zlib_decompress


HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
MAX_XML_PART_SIZE = 32 * 1024 * 1024


def _records(ole, path, compressed, issues=None):
    data = read_ole_stream(ole, path)
    if compressed:
        data = safe_zlib_decompress(data)
    parser = SectionParser()
    records = parser._read_all_records(data)
    if parser.errors and issues is not None:
        issues.extend(parser.errors)
    return records


def _xml_part(archive, part):
    info = archive.getinfo(part)
    if info.file_size > MAX_XML_PART_SIZE:
        raise ValueError('XML part exceeds probe size limit')
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    return etree.fromstring(archive.read(part), parser)


def _xml_form_text(element):
    kind = etree.QName(element).localname
    if kind in ('checkBtn', 'radioBtn'):
        marker = '[x]' if element.get('value', '').upper() == 'CHECKED' else '[ ]'
        return marker + element.get('caption', '')
    if kind == 'btn':
        return element.get('caption', '')
    if kind == 'edit':
        if element.get('passwordChar'):
            return ''
        return ''.join(element.findtext(HP + 'text', ''))
    items = element.findall(HP + 'listItem')
    selected = element.get('selectedValue', '')
    for item in items:
        if selected and item.get('value') == selected:
            return item.get('displayText') or item.get('value', '')
    return selected


def _paired_revisions(ole, header, pair, changes, authors):
    view_paths = sorted(path for path in ole.listdir() if len(path) == 2 and path[0] == 'ViewText')
    if not view_paths or not pair.is_file():
        return {'paired': False}
    paragraphs = []
    range_count = 0
    for path in view_paths:
        for record in _records(ole, path, header.is_compressed):
            if record.tag_id == 66:
                paragraphs.append([None, []])
            elif record.tag_id == 67 and paragraphs:
                paragraphs[-1][0] = parse_para_text(record.data)
            elif record.tag_id == 70 and paragraphs:
                paragraphs[-1][1].append(record.data)
                range_count += len(record.data) // 12
    result = {'paired': True, 'paragraphs': len(paragraphs), 'ranges': range_count, 'modes': {}}
    with zipfile.ZipFile(str(pair)) as archive:
        if len(archive.filelist) > 10000:
            raise ValueError('HWPX archive member count exceeds probe limit')
        xml_header = _xml_part(archive, 'Contents/header.xml')
        xml_changes = list(xml_header.iter(HH + 'trackChange'))
        xml_authors = list(xml_header.iter(HH + 'trackChangeAuthor'))
        result['change_types_match'] = [change.kind for change in changes.values()] == [element.get('type') for element in xml_changes]
        result['author_names_match'] = [author.name for author in authors] == [element.get('name') for element in xml_authors]
        result['changes'] = len(changes)
        for mode in ('preserve', 'final', 'original'):
            xml_errors = []
            projector = RevisionProjector(xml_errors, mode)
            projector.read_header(xml_header)
            xml_text = []
            for path in sorted(p for p in archive.namelist() if p.startswith('Contents/section') and p.endswith('.xml')):
                section = _xml_part(archive, path)
                projector.project_section(section)
                xml_text.extend(''.join(''.join(t.itertext()) for run in paragraph.findall(HP + 'run') for t in run.findall(HP + 't')) for paragraph in section.iter(HP + 'p'))
            binary_errors = []
            binary_text = [project_text_result(text, ranges, changes, mode, binary_errors)['text'] if text else '' for text, ranges in paragraphs]
            matches = sum(a == b for a, b in zip(binary_text, xml_text))
            result['modes'][mode] = {'binary_paragraphs': len(binary_text), 'hwpx_paragraphs': len(xml_text), 'matches': matches, 'binary_warnings': len(binary_errors), 'hwpx_warnings': len(xml_errors)}
    return result



def _final_projection_body(ole, header):
    """Compare the projected ViewText model with independently parsed BodyText.

    Limits stay identical to production. A truncated projection is reported as
    incomplete instead of comparing two prefixes and claiming success.
    """
    info = DocInfoParser().parse_stream(read_ole_stream(ole, 'DocInfo'), header.is_compressed)
    observations = {}
    texts = {}
    for storage, mode in (('ViewText', 'final'), ('BodyText', 'preserve')):
        parser = SectionParser(doc_info=info, revision_mode=mode)
        document = Document(source_format='hwp')
        paths = sorted(path for path in ole.listdir() if len(path) == 2 and path[0] == storage)
        for path in paths:
            document.sections.append(parser.parse_stream(read_ole_stream(ole, path), header.is_compressed))
        texts[storage] = to_plain_text(document)
        observations[storage] = {
            'sections': len(paths), 'characters': len(texts[storage]),
            'paragraphs': len(document.find_all('paragraph')),
            'diagnostics': len(info.errors) + len(parser.errors),
            'incomplete': any(error.startswith('ERR:') for error in info.errors + parser.errors),
            'record_limit': any('record count exceeds limit' in error for error in parser.errors),
        }
    observations['exact'] = texts['ViewText'] == texts['BodyText']
    observations['passed'] = observations['exact'] and all(
        observations[storage]['sections'] and not observations[storage]['incomplete']
        for storage in ('ViewText', 'BodyText'))
    return observations


def _model_pair(path, pair, modes=('preserve',)):
    result = {}
    for mode in modes:
        binary = Dochan(str(path), revision_mode=mode)
        xml = Dochan(str(pair), revision_mode=mode)
        binary_text = [paragraph.text for paragraph in binary.find_all('paragraph')]
        xml_text = [paragraph.text for paragraph in xml.find_all('paragraph')]
        result[mode] = {'binary_paragraphs': len(binary_text), 'hwpx_paragraphs': len(xml_text),
                        'matches': sum(a == b for a, b in zip(binary_text, xml_text)),
                        'exact': binary_text == xml_text,
                        'plain_text_exact': binary.to_plain_text() == xml.to_plain_text(),
                        'binary_warnings': len(binary.errors), 'hwpx_warnings': len(xml.errors)}
    return result


def _model_summary(path):
    result = {}
    for mode in ('preserve', 'final', 'original'):
        document = Dochan(str(path), revision_mode=mode)
        result[mode] = {'paragraphs': len(document.find_all('paragraph')), 'diagnostics': len(document.errors)}
    return result


def probe(corpus):
    root = Path(corpus)
    hwp_root = root / 'hwp' if (root / 'hwp').is_dir() else root
    hwpx_root = root / 'hwpx' if (root / 'hwpx').is_dir() else root.parent / 'hwpx'
    counts = Counter()
    forms = []
    revisions = []
    failures = []
    partial_streams = []
    for path in sorted(hwp_root.glob('*.hwp')):
        counts['files'] += 1
        try:
            validate_file_size(str(path), MAX_OLE_DOCUMENT_SIZE)
            if not olefile.isOleFile(str(path)):
                counts['not_ole'] += 1
                continue
            with olefile.OleFileIO(str(path)) as ole:
                if not ole.exists('FileHeader'):
                    counts['no_file_header'] += 1
                    continue
                header = FileHeader.parse(read_ole_stream(ole, 'FileHeader', max_bytes=256))
                counts['hwp'] += 1
                if header.is_encrypted or header.is_distribution:
                    counts['encrypted_or_distribution'] += 1
                    continue
                doc_records = _records(ole, 'DocInfo', header.is_compressed, partial_streams) if ole.exists('DocInfo') else []
                changes = {}
                authors = []
                for record in doc_records:
                    if record.tag_id == 96:
                        changes[len(changes) + 1] = parse_change(record.data)
                    elif record.tag_id == 97:
                        authors.append(parse_author(record.data))
                body_forms = []
                click_count = 0
                click_errors = 0
                for body_path in ole.listdir():
                    if len(body_path) != 2 or body_path[0] != 'BodyText':
                        continue
                    for record in _records(ole, body_path, header.is_compressed, partial_streams):
                        if record.tag_id == 91:
                            body_forms.append(form_text(record.data))
                        elif record.tag_id == 71 and record.data[:4] == b'klc%':
                            click_count += 1
                            try:
                                clickhere_prompt(record.data)
                            except ValueError:
                                click_errors += 1
                counts['clickhere_documents'] += bool(click_count)
                counts['clickhere_controls'] += click_count
                counts['clickhere_command_errors'] += click_errors
                pair = hwpx_root / (path.stem + '.hwpx')
                if body_forms:
                    counts['form_documents'] += 1
                    counts['form_controls'] += len(body_forms)
                    result = {'file': path.name, 'forms': len(body_forms), 'visible': sum(bool(value) for value in body_forms)}
                    if pair.is_file():
                        with zipfile.ZipFile(str(pair)) as archive:
                            if len(archive.filelist) > 10000:
                                raise ValueError('HWPX archive member count exceeds probe limit')
                            xml_values = []
                            unresolved_combos = 0
                            for part in sorted(p for p in archive.namelist() if p.startswith('Contents/section') and p.endswith('.xml')):
                                section = _xml_part(archive, part)
                                xml_values.extend(_xml_form_text(element) for element in section.iter() if isinstance(element.tag, str) and element.tag in {HP + name for name in ('btn', 'checkBtn', 'radioBtn', 'comboBox', 'edit')})
                                unresolved_combos += sum(not element.get('selectedValue') and any(item.get('value') or item.get('displayText') for item in element.findall(HP + 'listItem')) for element in section.iter(HP + 'comboBox'))
                            result.update({'paired_forms': len(xml_values), 'matches': sum(a == b for a, b in zip(body_forms, xml_values)), 'exact': body_forms == xml_values, 'unresolved_combo_selections': unresolved_combos})
                        result['model_comparison'] = _model_pair(path, pair)
                    forms.append(result)
                if header.is_track_change or changes:
                    counts['revision_documents'] += 1
                    result = {'file': path.name, 'changes': len(changes), 'authors': len(authors), 'validation': _paired_revisions(ole, header, pair, changes, authors),
                              'final_projection_vs_body': _final_projection_body(ole, header)}
                    counts['original_gold_pairs'] += pair.is_file()
                    counts['final_projection_body_passed'] += result['final_projection_vs_body']['passed']
                    if pair.is_file():
                        result['model_comparison'] = _model_pair(path, pair, ('preserve', 'final', 'original'))
                    else:
                        result['model_observation_without_gold'] = _model_summary(path)
                    revisions.append(result)
        except Exception as error:
            counts['errors'] += 1
            # Public file names identify incomplete scans without dumping data.
            failures.append({'file': path.name, 'probe_error': type(error).__name__})
    counts['partial_record_diagnostics'] = len(partial_streams)
    return {'counts': dict(counts), 'forms': forms, 'revisions': revisions, 'failed_files': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', help='public hwp-public directory')
    args = parser.parse_args()
    print(json.dumps(probe(args.corpus), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
