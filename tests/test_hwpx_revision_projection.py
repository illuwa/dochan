"""Projection of complete HWPX revision ranges in synthetic packages."""

import collections
import hashlib
import os
from pathlib import Path

import pytest
from lxml import etree

from dochan.hwpx.revisions import RevisionProjector
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
    corpus = os.environ.get('DOCHAN_PUBLIC_HWPX_CORPUS')
    if not corpus:
        pytest.skip('Set DOCHAN_PUBLIC_HWPX_CORPUS to run public document validation')
    root = Path(corpus)
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
        assert all('[missing-begin]' in e or '[formatting]' in e for e in doc.errors)
    preserve_hash = hashlib.sha256('\n'.join(output['preserve']).encode()).hexdigest()
    assert preserve_hash == 'ec5863b402309f855b9307f06c606c1a7f969bc94d7e5855453a22d3bf7deff8'
    baseline = collections.Counter(''.join(output['preserve']))
    for mode in ('final', 'original'):
        assert not collections.Counter(''.join(output[mode])) - baseline
