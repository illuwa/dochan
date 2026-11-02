"""Selected XML traversal keeps order/budgets without per-node snapshots."""

import pytest

from dochan.hwpx import parser as hwpx
from dochan.hwpx import revisions
from dochan.utils import safe_xml as xml


HP = hwpx.NS['hp']


def _root(body):
    return xml.fromstring(('<sec xmlns:hp="' + HP + '">' + body + '</sec>').encode())


def test_budget_resolves_each_expanded_tag_once(monkeypatch):
    root = _root('<hp:p><hp:run><hp:t>text</hp:t></hp:run></hp:p>' * 2000)
    original = hwpx._local_tag
    calls = []

    def counted(tag):
        calls.append(tag)
        return original(tag)

    monkeypatch.setattr(hwpx, '_local_tag', counted)
    parser = hwpx.HWPXParser()
    parser._limit_body_nodes(root)
    assert parser._body_nodes_remaining == hwpx.MAX_DOCUMENT_BODY_NODES - 2000
    assert len(calls) <= len({node.tag for node in root.iter()})


def test_repeated_local_tags_do_not_allocate_split_lists():
    class CountedTag(str):
        splits = 0

        def split(self, *args):
            self.splits += 1
            return super().split(*args)

    tag = CountedTag('{urn:speed-test}run')
    for _ in range(2000):
        assert hwpx._local_tag(tag) == 'run'
    assert tag.splits <= 1
    assert hwpx._local_tag([]) == ''
    assert hwpx._local_tag(xml.Comment) == ''


def test_revision_preflight_does_not_split_each_irrelevant_tag():
    class CountedTag(str):
        splits = 0

        def rsplit(self, *args):
            self.splits += 1
            return super().rsplit(*args)

    root = xml.Element('sec')
    tag = CountedTag('{urn:speed-test}layout')
    for _ in range(2000):
        xml.SubElement(root, tag)
    projector = revisions.RevisionProjector([])
    projector.read_header(root)
    assert revisions._collect_relevant(root) == set()
    assert tag.splits == 0


def test_revision_preflight_does_not_materialize_empty_attribute_dicts():
    class LazyAttributes(xml.Element):
        @property
        def attrib(self):
            raise AssertionError('attribute mapping was eagerly requested')

    root = LazyAttributes('sec')
    plain = LazyAttributes('run')
    changed = LazyAttributes('run', {'paraTcId': ''})
    root.extend([plain, changed])
    assert revisions._collect_relevant(root) == {root, changed}


def test_selected_walk_flattens_nested_switches_and_keeps_comments():
    root = _root(
        '<hp:p id="a"/><!--keep--><hp:switch>'
        '<hp:case required-namespace="unknown"><hp:p id="hidden"/></hp:case>'
        '<hp:default><hp:switch><hp:default><hp:p id="b">'
        '<hp:run id="c"/></hp:p></hp:default></hp:switch></hp:default>'
        '</hp:switch><hp:p id="d"/>'
    )
    assert [node.get('id') for node in hwpx._selected_children(root)] == ['a', None, 'b', 'd']
    assert [node.get('id') for node in hwpx._selected_descendants(root)] == ['a', None, 'b', 'c', 'd']


@pytest.mark.parametrize('budget', [0, 1, 2, 3, 4])
def test_budget_prunes_without_skipping_following_selected_siblings(budget):
    root = _root(
        '<hp:p><hp:run><hp:t>A</hp:t></hp:run></hp:p>'
        '<hp:switch><hp:case required-namespace="unknown"><hp:p>'
        '<hp:run><hp:t>hidden</hp:t></hp:run></hp:p></hp:case>'
        '<hp:default><hp:footNote><hp:subList><hp:p>'
        '<hp:run><hp:t>B</hp:t></hp:run></hp:p></hp:subList></hp:footNote>'
        '</hp:default></hp:switch>'
        '<hp:p><hp:run><hp:t>C</hp:t></hp:run></hp:p>'
    )
    parser = hwpx.HWPXParser()
    parser._section_root = root
    parser._body_nodes_remaining = budget
    parser._limit_body_nodes(root)
    assert parser._body_tail.getvalue() == {0: 'ABC', 1: 'BC', 2: 'BC', 3: 'BC', 4: 'C'}[budget]
    assert len(parser.errors) == 1
    assert 'hidden' not in parser._body_tail.getvalue()


def test_chart_in_unselected_branch_does_not_trigger_unsupported_placement():
    parser = hwpx.HWPXParser()
    section = parser._parse_section_xml(
        ('<sec xmlns:hp="' + HP + '"><hp:switch>'
         '<hp:case required-namespace="unknown"><hp:chart/></hp:case>'
         '<hp:default><hp:p><hp:run><hp:t>kept</hp:t></hp:run></hp:p>'
         '</hp:default></hp:switch></sec>').encode()
    )
    assert section.elements[0].text == 'kept'
    assert parser.errors == []


def test_chart_in_unknown_namespace_still_reports_unsupported_placement():
    parser = hwpx.HWPXParser()
    parser._parse_section_xml(b'<sec xmlns:x="urn:unknown"><x:box><x:chart/></x:box></sec>')
    assert len(parser.errors) == 1
    assert '[chart:unsupported_placement]' in parser.errors[0]
