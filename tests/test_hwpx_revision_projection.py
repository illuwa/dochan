"""Projection of complete HWPX revision ranges in synthetic packages."""

import collections
import hashlib
from pathlib import Path

import pytest
from lxml import etree

from dochan.hwpx.revisions import RevisionProjector
from dochan.hwpx import revisions
from dochan.hwpx.parser import HWPXParser


HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
NS = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"'
HEADER = '<hh:head %s><hh:trackChange id="1" type="Insert"/><hh:trackChange id="2" type="Delete"/></hh:head>' % NS


def project(body, mode, header=HEADER):
    root = etree.fromstring(('<hp:section %s>%s</hp:section>' % (NS, body)).encode())
    errors = []
    projector = RevisionProjector(errors, mode)
    projector.read_header(etree.fromstring(header.encode()))
    projector.project_section(root)
    return root, errors


def para_texts(root):
    return [''.join(p.itertext()) for p in root.iter(HP + 'p')]


@pytest.mark.parametrize('mode, expected', [
    ('preserve', ['AB', 'CD']),
    ('final', ['AB', 'CD']),
    ('original', ['ABCD']),
])
def test_inserted_paragraph_end_merges_in_original(mode, expected):
    body = ('<hp:p styleIDRef="7"><hp:run><hp:t>AB<hp:insertBegin Id="a" TcId="1"/>'
            '<hp:insertEnd Id="a" TcId="1" paraend="1"/></hp:t></hp:run></hp:p>'
            '<hp:p styleIDRef="8"><hp:run><hp:t>CD</hp:t></hp:run></hp:p>')
    root, errors = project(body, mode)
    assert para_texts(root) == expected
    assert not errors
    if mode == 'original':
        assert next(root.iter(HP + 'p')).get('styleIDRef') == '7'


@pytest.mark.parametrize('mode, expected', [
    ('preserve', ['AB', 'CD']),
    ('final', ['ABCD']),
    ('original', ['AB', 'CD']),
])
def test_deleted_paragraph_end_merges_in_final(mode, expected):
    body = ('<hp:p><hp:run><hp:t>AB<hp:deleteBegin Id="a" TcId="2"/>'
            '<hp:deleteEnd Id="a" TcId="2" paraend="1"/></hp:t></hp:run></hp:p>'
            '<hp:p><hp:run><hp:t>CD</hp:t></hp:run></hp:p>')
    root, errors = project(body, mode)
    assert para_texts(root) == expected
    assert not errors


def test_wholly_inserted_paragraph_keeps_following_style_in_original():
    body = ('<hp:p styleIDRef="7"><hp:run><hp:t>'
            '<hp:insertBegin Id="a" TcId="1"/>NEW'
            '<hp:insertEnd Id="a" TcId="1" paraend="1"/>'
            '</hp:t></hp:run></hp:p>'
            '<hp:p styleIDRef="8"><hp:run><hp:t>FOLLOW</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'original')
    assert para_texts(root) == ['FOLLOW']
    assert next(root.iter(HP + 'p')).get('styleIDRef') == '8'
    assert not errors


def test_deleted_object_only_paragraph_keeps_following_style():
    body = ('<hp:p styleIDRef="7"><hp:run><hp:t>'
            '<hp:deleteBegin Id="d" TcId="2"/></hp:t><hp:pic/>'
            '<hp:t><hp:deleteEnd Id="d" TcId="2" paraend="1"/></hp:t>'
            '</hp:run></hp:p>'
            '<hp:p styleIDRef="8"><hp:run><hp:t>FOLLOW</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert para_texts(root) == ['FOLLOW']
    assert next(root.iter(HP + 'p')).get('styleIDRef') == '8'
    assert not errors


@pytest.mark.parametrize('mode, expected', [
    ('preserve', ['ABCDE']), ('final', ['ADE']), ('original', ['ABE']),
])
def test_crossed_ranges_use_excluded_union(mode, expected):
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:insertBegin Id="i" TcId="1"/>C'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>D'
            '<hp:insertEnd Id="i" TcId="1" paraend="0"/>E</hp:t></hp:run></hp:p>')
    root, errors = project(body, mode)
    assert para_texts(root) == expected
    assert not errors


@pytest.mark.parametrize('outer, inner, mode, expected', [
    ('delete', 'insert', 'preserve', 'ABCDE'),
    ('delete', 'insert', 'final', 'AE'),
    ('delete', 'insert', 'original', 'ABDE'),
    ('insert', 'delete', 'preserve', 'ABCDE'),
    ('insert', 'delete', 'final', 'ABDE'),
    ('insert', 'delete', 'original', 'AE'),
])
def test_nested_ranges_project_each_kind(outer, inner, mode, expected):
    ids = {'insert': '1', 'delete': '2'}
    body = ('<hp:p><hp:run><hp:t>A<hp:%sBegin Id="o" TcId="%s"/>B'
            '<hp:%sBegin Id="i" TcId="%s"/>C'
            '<hp:%sEnd Id="i" TcId="%s" paraend="0"/>D'
            '<hp:%sEnd Id="o" TcId="%s" paraend="0"/>E</hp:t></hp:run></hp:p>') % (
                outer, ids[outer], inner, ids[inner], inner, ids[inner],
                outer, ids[outer])
    root, errors = project(body, mode)
    assert para_texts(root) == [expected]
    assert not errors


@pytest.mark.parametrize('mode, count', [('preserve', 1), ('final', 1), ('original', 0)])
def test_inserted_picture_is_atomic(mode, count):
    body = ('<hp:p><hp:run><hp:t>A<hp:insertBegin Id="i" TcId="1"/>'
            '</hp:t><hp:pic/><hp:t><hp:insertEnd Id="i" TcId="1" '
            'paraend="0"/>B</hp:t></hp:run></hp:p>')
    root, errors = project(body, mode)
    assert len(list(root.iter(HP + 'pic'))) == count
    assert not errors


@pytest.mark.parametrize('mode', ['preserve', 'final', 'original'])
def test_title_mark_does_not_break_text_range(mode):
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>'
            'B</hp:t><hp:titleMark/><hp:t>C<hp:deleteEnd Id="d" TcId="2" '
            'paraend="0"/>D</hp:t></hp:run></hp:p>')
    root, errors = project(body, mode)
    assert para_texts(root) == (['AD'] if mode == 'final' else ['ABCD'])
    assert not errors


@pytest.mark.parametrize('mode, count', [('preserve', 1), ('final', 0), ('original', 1)])
def test_object_inside_deleted_range_is_atomic(mode, count):
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/></hp:t>'
            '<hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run><hp:t>CELL</hp:t>'
            '</hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl>'
            '<hp:t><hp:deleteEnd Id="d" TcId="2" paraend="0"/>B</hp:t>'
            '</hp:run></hp:p>')
    root, errors = project(body, mode)
    assert len(list(root.iter(HP + 'tbl'))) == count
    assert not errors


@pytest.mark.parametrize('mode', ['preserve', 'final', 'original'])
def test_formatting_is_information_only(mode):
    header = HEADER.replace('</hh:head>', '<hh:trackChange id="3" type="ParaShape"/></hh:head>')
    root, errors = project('<hp:p paraTcId="3"><hp:run><hp:t>A</hp:t></hp:run></hp:p>', mode, header)
    assert para_texts(root) == ['A']
    assert len(errors) == 1
    assert errors[0].startswith('WARN:')
    assert 'formatting' in errors[0]


def test_multiset_subset_for_all_modes():
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:insertBegin Id="i" TcId="1"/>C'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>D'
            '<hp:insertEnd Id="i" TcId="1" paraend="0"/>E</hp:t></hp:run></hp:p>')
    baseline = collections.Counter(''.join(para_texts(project(body, 'preserve')[0])))
    for mode in ('final', 'original'):
        output = collections.Counter(''.join(para_texts(project(body, mode)[0])))
        assert not output - baseline


def test_object_tail_outside_range_survives():
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>'
            '<hp:pic/>TAIL<hp:deleteEnd Id="d" TcId="2" paraend="0"/>B'
            '</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert para_texts(root) == ['AB']
    assert not list(root.iter(HP + 'pic'))
    assert not errors


def test_ten_thousand_paragraph_end_merges_are_linear():
    paragraphs = []
    for index in range(10000):
        paragraphs.append('<hp:p><hp:run><hp:t>x<hp:deleteBegin Id="%d" TcId="2"/>'
                          '<hp:deleteEnd Id="%d" TcId="2" paraend="1"/>'
                          '</hp:t></hp:run></hp:p>' % (index, index))
    paragraphs.append('<hp:p><hp:run><hp:t>z</hp:t></hp:run></hp:p>')
    root, errors = project(''.join(paragraphs), 'final')
    assert para_texts(root) == ['x' * 10000 + 'z']
    assert not errors


def test_hundred_thousand_ranges_are_bounded():
    marker = ('<hp:deleteBegin Id="%d" TcId="2"/>'
              'x<hp:deleteEnd Id="%d" TcId="2" paraend="0"/>')
    body = '<hp:p><hp:run><hp:t>' + ''.join(marker % (n, n) for n in range(100000)) + '</hp:t></hp:run></hp:p>'
    root, errors = project(body, 'final')
    assert len(para_texts(root)[0]) == 100000
    assert any('range-limit' in error for error in errors)


def test_deeply_nested_markers_are_bounded():
    begins = ''.join('<hp:deleteBegin Id="%d" TcId="2"/>' % n for n in range(500))
    ends = ''.join('<hp:deleteEnd Id="%d" TcId="2" paraend="0"/>' % n
                   for n in reversed(range(500)))
    root, errors = project('<hp:p><hp:run><hp:t>' + begins + 'x' + ends + '</hp:t></hp:run></hp:p>', 'final')
    assert para_texts(root) == ['x']
    assert any('range-limit' in error for error in errors)


def test_public_revision_documents_when_corpus_is_supplied():
    root = Path(__file__).resolve().parents[1] / 'corpus/hwp-public/hwpx'
    if not root.is_dir():
        pytest.skip('Optional real corpus fixture is not installed')
    r1 = root / 'hwpxlib-ChangeTrack.hwpx'
    r2 = root / 'admrul-관세조사-운영-훈령.hwpx'
    assert r1.exists() and r2.exists()
    expected = {
        'preserve': '변경 추적 \t인간은',
        'final': '변경 \t인간은',
        'original': '변경 추적 \t',
    }
    parser = HWPXParser()
    for mode, gold in expected.items():
        doc = parser.parse(r1, include_assets=False, revision_mode=mode)
        assert [p.text for p in doc.find_all('paragraph')] == [gold]
        assert not doc.errors
    output = {}
    for mode in expected:
        doc = parser.parse(r2, include_assets=False, revision_mode=mode)
        output[mode] = [p.text for p in doc.find_all('paragraph')]
        assert all('[duplicate-end]' in e or '[formatting]' in e for e in doc.errors)
    preserve_hash = hashlib.sha256('\n'.join(output['preserve']).encode()).hexdigest()
    assert preserve_hash == 'ec5863b402309f855b9307f06c606c1a7f969bc94d7e5855453a22d3bf7deff8'
    baseline = collections.Counter(''.join(output['preserve']))
    for mode in ('final', 'original'):
        assert not collections.Counter(''.join(output[mode])) - baseline


@pytest.mark.parametrize('kind, mode', [('delete', 'final'), ('insert', 'original')])
def test_suppressed_object_has_no_children(kind, mode):
    tc = '2' if kind == 'delete' else '1'
    body = ('<hp:p><hp:run><hp:t>A<hp:%sBegin Id="x" TcId="%s"/>'
            '</hp:t><hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run>'
            '<hp:t>SECRET</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl>'
            '<hp:t><hp:%sEnd Id="x" TcId="%s" paraend="0"/>B</hp:t>'
            '</hp:run></hp:p>') % (kind, tc, kind, tc)
    root, errors = project(body, mode)
    assert para_texts(root) == ['AB']
    assert 'SECRET' not in ''.join(root.itertext())
    assert not errors


def test_adjacent_duplicate_end_is_informational():
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>C</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert para_texts(root) == ['AC']
    assert len(errors) == 1 and errors[0].startswith('WARN:')
    assert '[duplicate-end]' in errors[0]


def test_duplicate_end_across_empty_run_boundary_is_adjacent():
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/></hp:t></hp:run>'
            '<hp:run charPrIDRef="8"><hp:t>'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>C</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert para_texts(root) == ['AC']
    assert len(errors) == 1 and '[duplicate-end]' in errors[0]
    assert errors[0].startswith('WARN:')


def test_nonadjacent_end_invalidates_other_open_range():
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>'
            '<hp:insertBegin Id="i" TcId="1"/>'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>C'
            '<hp:insertEnd Id="i" TcId="1" paraend="0"/>D</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'original')
    # The intervening insertBegin makes the second deleteEnd nonadjacent.
    # An unmatched end invalidates the still-open insert range, so its text
    # must be preserved instead of silently projected.
    assert para_texts(root) == ['ABCD']
    assert any('[missing-begin]' in error and error.startswith('ERR:')
               for error in errors)


def test_nonadjacent_or_mismatched_end_stays_partial():
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>C'
            '<hp:deleteEnd Id="d" TcId="2" paraend="1"/>D</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert para_texts(root) == ['ACD']
    assert any('[missing-begin]' in error and error.startswith('ERR:')
               for error in errors)


def test_whitespace_prefix_survives_paragraph_end_merge():
    body = ('<hp:p><hp:run><hp:t>   <hp:insertBegin Id="i" TcId="1"/>'
            '<hp:insertEnd Id="i" TcId="1" paraend="1"/></hp:t></hp:run></hp:p>'
            '<hp:p><hp:run><hp:t>X</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'original')
    assert para_texts(root) == ['   X']
    assert not errors


def test_structural_ctrl_does_not_keep_deleted_heading():
    body = ('<hp:p styleIDRef="7"><hp:run><hp:ctrl><hp:colPr/></hp:ctrl>'
            '<hp:t><hp:deleteBegin Id="d" TcId="2"/>TITLE'
            '<hp:deleteEnd Id="d" TcId="2" paraend="1"/></hp:t></hp:run></hp:p>'
            '<hp:p styleIDRef="8"><hp:run><hp:t>body</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert para_texts(root) == ['body']
    assert next(root.iter(HP + 'p')).get('styleIDRef') == '8'
    assert not errors


def test_formatting_occurrences_count_actual_references():
    header = HEADER.replace('</hh:head>', '<hh:trackChange id="3" type="CharShape"/></hh:head>')
    body = '<hp:p><hp:run charTcId="3"><hp:t>A</hp:t></hp:run><hp:run charTcId="3"><hp:t>B</hp:t></hp:run></hp:p>'
    _, errors = project(body, 'final', header)
    assert len(errors) == 1
    assert 'occurrences=3' in errors[0]


def test_markpen_and_hyphen_do_not_break_range():
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:markpenBegin/>C<hp:markpenEnd/><hp:hyphen/>D'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>E</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert para_texts(root) == ['AE']
    assert not errors


def test_parashape_heading_change_remains_partial():
    header = HEADER.replace('</hh:head>', (
        '<hh:paraPr id="7"><hh:heading type="OUTLINE" level="0"/></hh:paraPr>'
        '<hh:paraPr id="8"><hh:heading type="NONE" level="0"/></hh:paraPr>'
        '<hh:trackChange id="3" type="ParaShape" parashapeID="7"/>'
        '</hh:head>'))
    body = '<hp:p paraPrIDRef="8" paraTcId="3"><hp:run><hp:t>body</hp:t></hp:run></hp:p>'
    _, errors = project(body, 'final', header)
    assert any('[formatting-heading]' in error and error.startswith('ERR:')
               for error in errors)


@pytest.mark.parametrize('between, suffix', [
    ('XYZ', 'text'),
    ('</hp:t></hp:run></hp:p><hp:p><hp:run><hp:t>XYZ', 'paragraph'),
    ('</hp:t><hp:pic/><hp:t>', 'object'),
])
def test_nonadjacent_duplicate_end_is_partial(between, suffix):
    body = ('<hp:p><hp:run><hp:t>A<hp:deleteBegin Id="d" TcId="2"/>B'
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>' + between +
            '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>C'
            '</hp:t></hp:run></hp:p>')
    root, errors = project(body, 'final')
    assert any('[missing-begin]' in error and error.startswith('ERR:')
               for error in errors), (suffix, errors)
    assert not any('[duplicate-end]' in error for error in errors)
    assert 'B' not in ''.join(para_texts(root))


def test_wholly_deleted_paragraph_retains_outside_bookmark_and_following_style():
    body = ('<hp:p styleIDRef="7"><hp:run>'
            '<hp:ctrl><hp:bookmark name="anchor1"/></hp:ctrl>'
            '<hp:ctrl><hp:colPr/></hp:ctrl><hp:ctrl><hp:secPr/></hp:ctrl>'
            '<hp:t><hp:deleteBegin Id="d" TcId="2"/>GONE'
            '<hp:deleteEnd Id="d" TcId="2" paraend="1"/></hp:t>'
            '</hp:run></hp:p>'
            '<hp:p styleIDRef="8" paraPrIDRef="9"><hp:run><hp:t>NEXT</hp:t>'
            '</hp:run></hp:p>')
    root, errors = project(body, 'final')
    paragraphs = list(root.iter(HP + 'p'))
    assert len(paragraphs) == 1
    assert paragraphs[0].get('styleIDRef') == '8'
    assert paragraphs[0].get('paraPrIDRef') == '9'
    assert [b.get('name') for b in paragraphs[0].iter(HP + 'bookmark')] == ['anchor1']
    assert len(list(paragraphs[0].iter(HP + 'colPr'))) == 1
    assert len(list(paragraphs[0].iter(HP + 'secPr'))) == 1
    assert 'GONE' not in ''.join(paragraphs[0].itertext())
    assert not errors


def test_diagnostic_counts_skipped_paragraphs_and_runs():
    plain = '<hp:p><hp:run><hp:t>plain</hp:t></hp:run></hp:p>'
    body = plain * 17 + ('<hp:p><hp:run charTcId="99"><hp:t>tracked'
                         '</hp:t></hp:run></hp:p>')
    header = HEADER.replace('</hh:head>',
                            '<hh:trackChange id="3" type="CharShape"/></hh:head>')
    _, errors = project(body, 'final', header)
    assert any('[header-reference]' in error and
               'paragraph#18/run#18' in error for error in errors), errors


def test_none_heading_levels_do_not_trigger_heading_partial():
    header = HEADER.replace('</hh:head>', (
        '<hh:paraPr id="7"><hh:heading type="NONE" level="0"/></hh:paraPr>'
        '<hh:paraPr id="8"><hh:heading type="NONE" level="4"/></hh:paraPr>'
        '<hh:trackChange id="3" type="ParaShape" parashapeID="7"/>'
        '</hh:head>'))
    body = '<hp:p paraPrIDRef="8" paraTcId="3"><hp:run><hp:t>body</hp:t></hp:run></hp:p>'
    _, errors = project(body, 'final', header)
    assert any('[formatting]' in error for error in errors)
    assert not any('[formatting-heading]' in error for error in errors)


def test_relevant_scan_reuses_known_ancestors():
    class Node:
        ancestor_visits = 0

        def __init__(self, parent=None, marked=False):
            self.tag = HP + 'run'
            self.attrib = {'charTcId': '3'} if marked else {}
            self.parent = parent
            self.children = []
            if parent is not None:
                parent.children.append(self)

        def iter(self):
            yield self
            for child in self.children:
                yield from child.iter()

        def iterancestors(self):
            parent = self.parent
            while parent is not None:
                Node.ancestor_visits += 1
                yield parent
                parent = parent.parent

    root = Node()
    parent = root
    for _ in range(80):
        parent = Node(parent)
    for _ in range(100):
        Node(parent, marked=True)
    relevant = revisions._collect_relevant(root)
    assert len(relevant) == 181
    assert Node.ancestor_visits <= 180
