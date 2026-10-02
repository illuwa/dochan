"""Synthetic packages for PresentationML character-property inheritance."""
import zipfile

import pytest

from dochan.ooxml.pptx import A_NS, P_NS, R_NS, REL_NS, PPTXReader


def shape(text="sample", ph='type="body" idx="1"', props="", style="", runs=None):
    placeholder = '<p:ph %s/>' % ph if ph is not None else ''
    return ('<p:sp><p:nvSpPr><p:cNvPr id="2" name="test"/><p:cNvSpPr/>'
            '<p:nvPr>%s</p:nvPr></p:nvSpPr><p:txBody><a:bodyPr/>'
            '<a:lstStyle>%s</a:lstStyle><a:p>%s%s</a:p></p:txBody></p:sp>') % (
                placeholder, style, props,
                runs if runs is not None else '<a:r><a:t>%s</a:t></a:r>' % text)


def level(attrs, lvl=0):
    return '<a:lvl%dpPr><a:defRPr %s/></a:lvl%dpPr>' % (lvl + 1, attrs, lvl + 1)


def package(tmp_path, slide=None, layout="", master="", tx="", default="", extra=None):
    ns = 'xmlns:p="%s" xmlns:a="%s" xmlns:r="%s"' % (P_NS, A_NS, R_NS)

    def rel(kind, target):
        return ('<Relationships xmlns="%s"><Relationship Id="r1" Type="%s/%s" '
                'Target="%s"/></Relationships>') % (REL_NS, R_NS, kind, target)

    parts = {
        'ppt/presentation.xml': '<p:presentation %s><p:sldIdLst><p:sldId id="256" '
        'r:id="r1"/></p:sldIdLst><p:defaultTextStyle>%s</p:defaultTextStyle></p:presentation>' % (ns, default),
        'ppt/_rels/presentation.xml.rels': rel('slide', 'slides/slide1.xml'),
        'ppt/slides/slide1.xml': '<p:sld %s><p:cSld><p:spTree>%s</p:spTree></p:cSld></p:sld>' % (
            ns, slide if slide is not None else shape()),
        'ppt/slides/_rels/slide1.xml.rels': rel('slideLayout', '../slideLayouts/slideLayout1.xml'),
        'ppt/slideLayouts/slideLayout1.xml': '<p:sldLayout %s><p:cSld><p:spTree>%s</p:spTree>'
        '</p:cSld></p:sldLayout>' % (ns, layout),
        'ppt/slideLayouts/_rels/slideLayout1.xml.rels': rel('slideMaster', '../slideMasters/slideMaster1.xml'),
        'ppt/slideMasters/slideMaster1.xml': '<p:sldMaster %s><p:cSld><p:spTree>%s</p:spTree>'
        '</p:cSld><p:txStyles>%s</p:txStyles></p:sldMaster>' % (ns, master, tx),
    }
    parts.update(extra or {})
    path = tmp_path / 'master.pptx'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, contents in parts.items():
            archive.writestr(name, contents)
    return path


def read_runs(path):
    doc = PPTXReader().read(str(path))
    assert not doc.errors, doc.errors
    return [run for para in doc.find_all('paragraph') for run in para.runs]


@pytest.mark.parametrize('source', ['default', 'txStyles', 'master', 'layout', 'slide', 'paragraph'])
def test_character_defaults_at_each_stage(tmp_path, source):
    attrs = 'b="1" i="1" u="dbl" sz="2450" baseline="30000"'
    kwargs = {}
    if source == 'default':
        kwargs['default'] = level(attrs)
    elif source == 'txStyles':
        kwargs['tx'] = '<p:bodyStyle>%s</p:bodyStyle>' % level(attrs)
    elif source in {'master', 'layout', 'slide'}:
        kwargs[source] = shape(style=level(attrs))
    else:
        kwargs['slide'] = shape(props='<a:pPr><a:defRPr %s/></a:pPr>' % attrs)
    run = read_runs(package(tmp_path, **kwargs))[0]
    assert (run.bold, run.italic, run.underline, run.font_size_pt, run.superscript) == (
        True, True, True, 24.5, True)
    assert not run.subscript


def test_attribute_wise_precedence_and_explicit_off(tmp_path):
    path = package(
        tmp_path,
        default=level('b="1" i="1" u="sng" sz="1000" baseline="30000"'),
        tx='<p:bodyStyle>%s</p:bodyStyle>' % level('sz="2000"'),
        master=shape(style=level('sz="3000"')),
        layout=shape(style=level('sz="4000" i="0"')),
        slide=shape(style=level('sz="5000"'), props='<a:pPr><a:defRPr sz="6000"/></a:pPr>',
                    runs='<a:r><a:rPr b="0" u="none" baseline="0"/><a:t>off</a:t></a:r>'
                    '<a:r><a:rPr sz="7000" baseline="-25000"/><a:t>on</a:t></a:r>'),
    )
    off, on = read_runs(path)
    assert (off.bold, off.italic, off.underline, off.superscript, off.subscript) == (False,) * 5
    assert off.font_size_pt == 60
    assert (on.bold, on.italic, on.underline, on.font_size_pt, on.subscript) == (True, False, True, 70, True)


@pytest.mark.parametrize('lvl', range(9))
def test_all_nine_paragraph_levels(tmp_path, lvl):
    path = package(tmp_path, slide=shape(props='<a:pPr lvl="%d"/>' % lvl),
                   layout=shape(style=level('sz="%d"' % (1100 + lvl * 100), lvl)),
                   default='<a:defPPr><a:defRPr i="1"/></a:defPPr>')
    run = read_runs(path)[0]
    assert run.font_size_pt == 11 + lvl
    assert run.italic


@pytest.mark.parametrize('slide_type,layout_type,master_type,style_name', [
    ('ctrTitle', 'title', 'title', 'titleStyle'),
    ('title', 'ctrTitle', 'title', 'titleStyle'),
    ('subTitle', 'body', 'body', 'bodyStyle'),
    ('obj', 'obj', 'body', 'bodyStyle'),
    ('body', 'subTitle', 'body', 'bodyStyle'),
])
def test_placeholder_type_families_and_master_index(tmp_path, slide_type, layout_type, master_type, style_name):
    path = package(tmp_path, slide=shape(ph='type="%s" idx="7"' % slide_type),
                   layout=shape(ph='type="%s" idx="7"' % layout_type, style=level('b="1"')),
                   master=shape(ph='type="%s" idx="1"' % master_type, style=level('i="1"')),
                   tx='<p:%s>%s</p:%s>' % (style_name, level('u="sng"'), style_name))
    run = read_runs(path)[0]
    assert run.bold and run.italic and run.underline


def test_placeholder_index_selects_layout_and_missing_type_inherits(tmp_path):
    path = package(tmp_path, slide=shape(ph='idx="7"'),
                   layout=shape(ph='type="title" idx="8"', style=level('b="0"')) +
                   shape(ph='type="title" idx="7"', style=level('b="1"')),
                   tx='<p:titleStyle>%s</p:titleStyle>' % level('i="1"'))
    run = read_runs(path)[0]
    assert run.bold and run.italic


def test_wrong_layout_index_does_not_match_and_other_style_is_isolated(tmp_path):
    path = package(tmp_path, slide=shape() + shape(text='free', ph=None),
                   layout=shape(ph='type="body" idx="8"', style=level('b="1"')),
                   tx='<p:bodyStyle>%s</p:bodyStyle><p:otherStyle>%s</p:otherStyle>' % (
                       level('i="1"'), level('u="sng"')))
    body, free = read_runs(path)
    assert not body.bold and body.italic and not body.underline
    # PowerPoint deck1 S3/S10: free shapes do not inherit otherStyle.
    assert not free.bold and not free.italic and not free.underline


def test_ancestor_paragraph_defaults_not_sample_run_properties(tmp_path):
    ancestor = shape(props='<a:pPr lvl="2"><a:defRPr b="1"/></a:pPr>',
                     style=level('i="1"', 2),
                     runs='<a:r><a:rPr u="sng"/><a:t>sample</a:t></a:r><a:endParaRPr baseline="30000"/>')
    path = package(tmp_path, slide=shape(props='<a:pPr lvl="2"/>'), layout=ancestor)
    run = read_runs(path)[0]
    # PowerPoint deck1 S2: ancestor sample pPr/defRPr is not inherited.
    assert not run.bold and run.italic
    assert not run.underline and not run.superscript


def test_fields_breaks_and_equation_chunks_keep_defaults(tmp_path):
    runs = ('<a:r><a:t>before</a:t></a:r><a:br/><a:fld id="1"><a:rPr b="0"/>'
            '<a:t>field</a:t></a:fld><m:oMath xmlns:m="http://schemas.openxmlformats.org/'
            'officeDocument/2006/math"><m:r><m:t>x</m:t></m:r></m:oMath>'
            '<a:r><a:t>after</a:t></a:r>')
    path = package(tmp_path, slide=shape(props='<a:pPr><a:defRPr b="1" sz="2000"/></a:pPr>', runs=runs))
    before, br, fld, after = read_runs(path)
    assert before.bold and br.bold and after.bold and not fld.bold
    assert [r.font_size_pt for r in (before, br, fld, after)] == [20] * 4


def test_malformed_master_warns_without_losing_slide(tmp_path):
    path = package(tmp_path, default=level('b="1"'),
                   extra={'ppt/slideMasters/slideMaster1.xml': '<broken'})
    doc = PPTXReader().read(str(path))
    assert doc.sections[0].elements[0].text == 'sample'
    assert doc.sections[0].elements[0].runs[0].bold
    assert any('WARN:' in error and 'style' in error.lower() for error in doc.errors)


def test_invalid_values_warn_and_keep_inherited_values(tmp_path):
    path = package(tmp_path, default=level('sz="2300" baseline="-20000" b="1"'),
                   slide=shape(props='<a:pPr lvl="999999999999999999999999999"/>',
                               runs='<a:r><a:rPr sz="NaN" baseline="NaN" b="broken"/>'
                               '<a:t>sample</a:t></a:r>'))
    doc = PPTXReader().read(str(path))
    run = doc.sections[0].elements[0].runs[0]
    assert run.font_size_pt == 23 and run.subscript and run.bold
    assert doc.errors and all(error.startswith('WARN:') for error in doc.errors)


def test_table_cells_keep_existing_formatting_scope(tmp_path):
    table = ('<p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody>'
             '<a:p><a:r><a:rPr i="1" sz="4000"/><a:t>cell</a:t></a:r></a:p>'
             '</a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>')
    path = package(tmp_path, slide=shape() + table, default=level('b="1" sz="3000"'))
    doc = PPTXReader().read(str(path))
    cell = list(doc.find_all('table'))[0].rows[0][0]
    assert cell.paragraphs[0].runs[0].italic
    assert not cell.paragraphs[0].runs[0].bold
    assert cell.paragraphs[0].runs[0].font_size_pt == 10


@pytest.mark.parametrize('budget', ['MAX_STYLE_BYTES', 'MAX_STYLE_PARTS', 'MAX_STYLE_NODES'])
def test_style_resource_limits_preserve_text(tmp_path, monkeypatch, budget):
    import dochan.ooxml.pptx_styles as styles
    monkeypatch.setattr(styles, budget, 0)
    path = package(tmp_path, layout=shape(style=level('b="1"')))
    doc = PPTXReader().read(str(path))
    assert doc.sections[0].elements[0].text == 'sample'
    assert any('limit exceeded' in error for error in doc.errors)


def test_external_style_relationship_is_never_loaded(tmp_path):
    rel = ('<Relationships xmlns="%s"><Relationship Id="ext" Type="%s/slideLayout" '
           'TargetMode="External" Target="https://example.test/style.xml"/></Relationships>') % (REL_NS, R_NS)
    path = package(tmp_path, default=level('b="1"'),
                   extra={'ppt/slides/_rels/slide1.xml.rels': rel})
    assert read_runs(path)[0].bold


def test_missing_type_and_index_use_title_chain(tmp_path):
    path = package(tmp_path, slide=shape(ph=''), layout=shape(ph='', style=level('i="1"')),
                   tx='<p:bodyStyle>%s</p:bodyStyle>' % level('b="1"'))
    run = read_runs(path)[0]
    # PowerPoint deck2 S14: <p:ph/> uses titleStyle, not bodyStyle.
    assert not run.bold and run.italic


def test_reader_reuse_does_not_retain_master_styles(tmp_path):
    reader = PPTXReader()
    path = package(tmp_path, master=shape(style=level('b="1"')))
    assert reader.read(str(path)).sections[0].elements[0].runs[0].bold
    path = package(tmp_path)
    assert not reader.read(str(path)).sections[0].elements[0].runs[0].bold


def test_comments_and_processing_instructions_in_style_tree(tmp_path):
    path = package(tmp_path, layout='<!-- preserved comment --><?test marker?>' + shape(style=level('b="1"')))
    assert read_runs(path)[0].bold


def test_grouped_shapes_and_static_layout_text_receive_defaults(tmp_path):
    path = package(tmp_path, slide='<p:grpSp>' + shape() + '</p:grpSp>',
                   layout=shape(text='static', ph=None, style=level('i="1"')),
                   default=level('sz="2400"'))
    static, slide = read_runs(path)
    assert static.text == 'static' and static.italic
    assert slide.text == 'sample' and not slide.italic
    assert static.font_size_pt == slide.font_size_pt == 24


def test_notes_keep_existing_formatting_scope(tmp_path):
    slide_rels = ('<Relationships xmlns="%s"><Relationship Id="notes" Type="%s/notesSlide" '
                  'Target="../notesSlides/notesSlide1.xml"/></Relationships>') % (REL_NS, R_NS)
    notes = '<p:notes xmlns:p="%s" xmlns:a="%s"><p:cSld><p:spTree>%s</p:spTree></p:cSld></p:notes>' % (
        P_NS, A_NS, shape(text='note'))
    path = package(tmp_path, default=level('b="1" sz="3000"'), extra={
        'ppt/slides/_rels/slide1.xml.rels': slide_rels,
        'ppt/notesSlides/notesSlide1.xml': notes,
    })
    slide, note = read_runs(path)
    assert slide.bold and slide.font_size_pt == 30
    assert not note.bold and note.font_size_pt == 10


def test_body_family_uses_master_body_before_exact_type(tmp_path):
    path = package(tmp_path, slide=shape(ph='type="obj" idx="7"'),
                   master=shape(ph='type="body" idx="7"', style=level('b="1"')) +
                   shape(ph='type="obj" idx="1"', style=level('i="1"')) +
                   shape(ph='type="obj" idx="7"', style=level('u="sng"')))
    run = read_runs(path)[0]
    # PowerPoint deck2 S4/S5: body master supplies every body-family placeholder.
    assert run.bold and not run.underline and not run.italic


@pytest.mark.parametrize('budget', ['MAX_STYLE_BYTES', 'MAX_STYLE_PARTS', 'MAX_STYLE_NODES'])
def test_layout_content_survives_zero_style_budget(tmp_path, monkeypatch, budget):
    import dochan.ooxml.pptx_styles as styles
    monkeypatch.setattr(styles, budget, 0)
    doc = PPTXReader().read(str(package(tmp_path, layout=shape('static', ph=None))))
    assert [p.text for p in doc.find_all('paragraph')] == ['static', 'sample']
    assert any('limit exceeded' in e for e in doc.errors)


def test_shared_layout_content_survives_1100_slides(tmp_path):
    path = package(tmp_path, layout=shape('static', ph=None))
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    ns = 'xmlns:p="%s" xmlns:r="%s"' % (P_NS, R_NS)
    parts['ppt/presentation.xml'] = ('<p:presentation %s><p:sldIdLst>%s</p:sldIdLst>'
                                    '</p:presentation>') % (ns, ''.join(
        '<p:sldId id="%d" r:id="r%d"/>' % (255 + i, i) for i in range(1, 1101)))
    parts['ppt/_rels/presentation.xml.rels'] = '<Relationships xmlns="%s">%s</Relationships>' % (
        REL_NS, ''.join('<Relationship Id="r%d" Type="%s/slide" Target="slides/slide%d.xml"/>' %
                       (i, R_NS, i) for i in range(1, 1101)))
    for i in range(2, 1101):
        parts['ppt/slides/slide%d.xml' % i] = parts['ppt/slides/slide1.xml']
        parts['ppt/slides/_rels/slide%d.xml.rels' % i] = parts['ppt/slides/_rels/slide1.xml.rels']
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    doc = PPTXReader().read(str(path))
    assert len(doc.sections) == 1100
    assert sum(p.text == 'static' for p in doc.find_all('paragraph')) == 1100
    assert sum(p.text == 'sample' for p in doc.find_all('paragraph')) == 1100


@pytest.mark.parametrize('value,expected', [('0%', (False, False)), ('-25%', (False, True)),
                                           ('30%', (True, False)), ('+0.125%', (True, False))])
def test_percentage_baseline_overrides_inherited_value(tmp_path, value, expected):
    path = package(tmp_path, default=level('baseline="30000"'),
                   slide=shape(runs='<a:r><a:rPr baseline="%s"/><a:t>x</a:t></a:r>' % value))
    run = read_runs(path)[0]
    assert (run.superscript, run.subscript) == expected


@pytest.mark.parametrize('value', ['', 'typo'])
def test_invalid_underline_does_not_enable_underline(tmp_path, value):
    path = package(tmp_path, slide=shape(runs='<a:r><a:rPr u="%s"/><a:t>x</a:t></a:r>' % value))
    doc = PPTXReader().read(str(path))
    assert not doc.find_all('paragraph')[0].runs[0].underline
    assert any('invalid character attribute u' in e for e in doc.errors)


@pytest.mark.parametrize('slide_idx,layout_idx', [('01', '1'), ('+1', '1'), ('1', '01'),
                                                ('4294967295', '+4294967295')])
def test_placeholder_idx_is_unsigned_integer(tmp_path, slide_idx, layout_idx):
    path = package(tmp_path, slide=shape(ph='type="body" idx="%s"' % slide_idx),
                   layout=shape(ph='type="body" idx="%s"' % layout_idx, style=level('b="1" sz="3200"')))
    run = read_runs(path)[0]
    assert run.bold and run.font_size_pt == 32


@pytest.mark.parametrize('value', ['-1', '4294967296', '1_0', 'NaN', ''])
def test_invalid_placeholder_idx_never_matches(tmp_path, value):
    path = package(tmp_path, slide=shape(ph='type="body" idx="%s"' % value),
                   layout=shape(ph='type="body" idx="%s"' % value, style=level('b="1"')))
    doc = PPTXReader().read(str(path))
    assert not doc.find_all('paragraph')[0].runs[0].bold
    assert any('invalid placeholder index' in e for e in doc.errors)


def test_layout_style_wins_over_master_style(tmp_path):
    run = read_runs(package(tmp_path, layout=shape(style=level('sz="4000" b="0"')),
                            master=shape(style=level('sz="3000" b="1"'))))[0]
    assert run.font_size_pt == 40 and not run.bold


def test_txstyle_wins_over_presentation_default(tmp_path):
    run = read_runs(package(tmp_path, default=level('sz="1000" b="1"'),
                            tx='<p:bodyStyle>%s</p:bodyStyle>' % level('sz="2800" b="0"')))[0]
    assert run.font_size_pt == 28 and not run.bold


def test_layout_textbox_ignores_master_other_style(tmp_path):
    # PowerPoint deck1 S3/S10 and deck2 S11/S16: otherStyle is not inherited.
    runs = read_runs(package(tmp_path, layout=shape('static', ph=None), default=level('sz="1100"'),
                             tx='<p:otherStyle>%s</p:otherStyle>' % level('sz="3200" b="1"')))
    assert runs[0].text == 'static' and runs[0].font_size_pt == 11 and not runs[0].bold


def resolver_for_test():
    from lxml import etree
    from dochan.ooxml.pptx_styles import TextStyleResolver
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    root = etree.fromstring(('<p:presentation xmlns:p="%s"/>' % P_NS).encode(), parser)
    return TextStyleResolver(None, root, [], lambda node: None), parser


def test_malformed_list_style_scan_is_cached():
    from lxml import etree
    resolver, parser = resolver_for_test()
    node = etree.fromstring(('<a:lstStyle xmlns:a="%s">%s</a:lstStyle>' %
                            (A_NS, '<a:lvl9pPr/>' * 1000)).encode(), parser)

    class CountedStyle:
        def __init__(self):
            self.visits = 0

        def find(self, path, ns):
            self.visits += len(node)
            return node.find(path, ns)

        def __iter__(self):
            for child in node:
                self.visits += 1
                yield child

        def getroottree(self):
            return node.getroottree()

    style = CountedStyle()
    for _ in range(1000):
        assert resolver._list_properties(style, 0) == {}
    assert style.visits <= 3000


def test_first_list_style_scan_has_node_budget(monkeypatch):
    from lxml import etree
    import dochan.ooxml.pptx_styles as styles
    monkeypatch.setattr(styles, 'MAX_STYLE_NODES', 20)
    resolver, parser = resolver_for_test()
    node = etree.fromstring(('<a:lstStyle xmlns:a="%s">%s</a:lstStyle>' %
                            (A_NS, '<a:lvl9pPr/>' * 100 + level('b="1"'))).encode(), parser)
    assert resolver._list_properties(node, 0) == {}
    assert any('limit exceeded' in e for e in resolver.errors)


def test_node_budget_is_per_part(monkeypatch):
    from lxml import etree
    import dochan.ooxml.pptx_styles as styles
    monkeypatch.setattr(styles, 'MAX_STYLE_NODES', 5)
    resolver, parser = resolver_for_test()
    for _ in range(3):
        root = etree.fromstring(('<p:sldLayout xmlns:p="%s" xmlns:a="%s"><p:cSld>'
                                 '<p:spTree>%s</p:spTree></p:cSld></p:sldLayout>' %
                                 (P_NS, A_NS, shape())).encode(), parser)
        assert resolver._index(root)[0]
    assert not resolver.errors


def test_unsafe_layout_target_warns_and_keeps_slide(tmp_path):
    rel = '<Relationships xmlns="%s"><Relationship Id="r1" Type="%s/slideLayout" Target="../../../etc/passwd"/></Relationships>' % (REL_NS, R_NS)
    doc = PPTXReader().read(str(package(tmp_path, extra={'ppt/slides/_rels/slide1.xml.rels': rel})))
    assert [p.text for p in doc.find_all('paragraph')] == ['sample']
    assert doc.errors and all(e.startswith('WARN:') for e in doc.errors)


# Reproduced from the orchestrator's PowerPoint(Mac) measurements, 2026-10-03.
# Expected tuples are measured values, not resolver-generated values.
def measured_shape(name, ph=None, paras=None, lst='', txbox=False, y=0):
    return ('<p:sp><p:nvSpPr><p:cNvPr id="2" name="%s"/><p:cNvSpPr txBox="%s"/>'
            '<p:nvPr>%s</p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="0" y="%d"/>'
            '<a:ext cx="100" cy="100"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/>'
            '<a:lstStyle>%s</a:lstStyle>%s</p:txBody></p:sp>') % (
                name, '1' if txbox else '0', ph or '', y * 1000, lst, ''.join(paras or []))


def measured_paragraph(text, ppr=''):
    return '<a:p>%s<a:r><a:rPr lang="en-US"/><a:t>%s</a:t></a:r></a:p>' % (ppr, text)


def test_powerpoint_measured_deck1(tmp_path):
    def lvl(n, attrs):
        return level(attrs, n - 1)

    TX = ('<p:titleStyle>' + lvl(1, 'sz="4400" b="1"') + '</p:titleStyle>'
          '<p:bodyStyle>' + lvl(1, 'sz="2800" i="1"') + lvl(2, 'sz="2400"') + lvl(3, 'sz="1500" u="sng"') + '</p:bodyStyle>'
          '<p:otherStyle>' + lvl(1, 'sz="3200" b="1"') + '</p:otherStyle>')
    DTS = '<a:defPPr><a:defRPr lang="en-US"/></a:defPPr>' + lvl(1, 'sz="1100"') + lvl(3, 'sz="1000"')

    MASTER = [
        measured_shape('MTitle', '<p:ph type="title"/>', [measured_paragraph('Master title')]),
        # master body sample paragraph carries pPr/defRPr baseline only
        measured_shape('MBody', '<p:ph type="body" idx="1"/>', [measured_paragraph('Master body', '<a:pPr><a:defRPr baseline="30000"/></a:pPr>')]),
        measured_shape('MDate', '<p:ph type="dt" sz="half" idx="2"/>', [measured_paragraph('date')]),
    ]
    L1 = [
        measured_shape('LTitle', '<p:ph type="title"/>', [measured_paragraph('Layout title')]),
        # layout body: sample paragraph pPr/defRPr (not lstStyle)
        measured_shape('LBody', '<p:ph idx="1"/>', [measured_paragraph('Layout body sample', '<a:pPr><a:defRPr i="0" sz="4000" u="sng"/></a:pPr>')]),
        measured_shape('LPic', '<p:ph type="pic" idx="13"/>', [measured_paragraph('pic prompt')]),
        measured_shape('LDate', '<p:ph type="dt" sz="half" idx="10"/>', [measured_paragraph('date')]),
        measured_shape('LDefPPr', '<p:ph type="body" idx="14"/>', [measured_paragraph('defppr')], lst='<a:defPPr><a:defRPr sz="4400"/></a:defPPr>'),
        measured_shape('LSub', '<p:ph type="subTitle" idx="15"/>', [measured_paragraph('sub')]),
        measured_shape('LByType', '<p:ph type="body" idx="16"/>', [measured_paragraph('bytype')], lst=lvl(1, 'sz="2000"')),
        measured_shape('LText', None, [measured_paragraph('LAYOUT TEXTBOX')], txbox=True, y=10),
    ]
    SLIDE = [
        measured_shape('S1_title', '<p:ph type="title"/>', [measured_paragraph('S1 title')], y=0),
        measured_shape('S2_body', '<p:ph idx="1"/>', [measured_paragraph('S2 body lvl0'), measured_paragraph('S2 body lvl2', '<a:pPr lvl="2"/>')], y=1),
        measured_shape('S3_textbox', None, [measured_paragraph('S3 textbox plain')], txbox=True, y=2),
        measured_shape('S4_textbox_pdef', None, [measured_paragraph('S4 textbox pPr defRPr', '<a:pPr><a:defRPr b="0" sz="2400" i="1"/></a:pPr>')], txbox=True, y=3),
        measured_shape('S5_pic', '<p:ph type="pic" idx="13"/>', [measured_paragraph('S5 pic text')], y=4),
        measured_shape('S6_dt', '<p:ph type="dt" sz="half" idx="10"/>', [measured_paragraph('S6 date')], y=5),
        measured_shape('S7_defppr', '<p:ph type="body" idx="14"/>', [measured_paragraph('S7 defPPr')], y=6),
        measured_shape('S8_sub', '<p:ph type="subTitle" idx="15"/>', [measured_paragraph('S8 subtitle')], y=7),
        measured_shape('S9_orphan', '<p:ph type="body" idx="99"/>', [measured_paragraph('S9 orphan idx')], y=8),
        measured_shape('S10_shape_nontx', None, [measured_paragraph('S10 rect shape no txBox')], y=9),
    ]
    path = package(tmp_path, slide="".join(SLIDE), layout="".join(L1),
                   master="".join(MASTER), tx=TX, default=DTS)
    actual = [(r.text, r.font_size_pt, r.bold, r.italic, r.underline, r.superscript, r.subscript)
              for r in read_runs(path) if r.text != "LAYOUT TEXTBOX"]
    assert actual == [
        ('S1 title', 44.0, True, False, False, False, False),
        ('S2 body lvl0', 28.0, False, True, False, False, False),
        ('S2 body lvl2', 15.0, False, False, True, False, False),
        ('S3 textbox plain', 11.0, False, False, False, False, False),
        ('S4 textbox pPr defRPr', 24.0, False, True, False, False, False),
        ('S5 pic text', 28.0, False, True, False, False, False),
        ('S6 date', 11.0, False, False, False, False, False),
        ('S7 defPPr', 28.0, False, True, False, False, False),
        ('S8 subtitle', 28.0, False, True, False, False, False),
        ('S9 orphan idx', 28.0, False, True, False, False, False),
        ('S10 rect shape no txBox', 11.0, False, False, False, False, False),
    ]


def test_powerpoint_measured_deck2(tmp_path):
    def lvl(n, attrs):
        return level(attrs, n - 1)

    TX = ('<p:titleStyle>' + lvl(1, 'sz="4400" b="1"') + '</p:titleStyle>'
          '<p:bodyStyle>' + lvl(1, 'sz="2800" i="1"') + lvl(2, 'sz="2400"') + '</p:bodyStyle>'
          '<p:otherStyle>' + lvl(1, 'sz="3200" b="1" u="sng"') + '</p:otherStyle>')
    DTS = '<a:defPPr><a:defRPr sz="1300"/></a:defPPr>' + lvl(1, 'sz="1100"') + lvl(2, 'sz="1050"')

    MASTER = [
        measured_shape('MTitle', '<p:ph type="title"/>', [measured_paragraph('Master title')]),
        measured_shape('MBody', '<p:ph type="body" idx="1"/>', [measured_paragraph('Master body')], lst=lvl(1, 'sz="3000"')),
        measured_shape('MDate', '<p:ph type="dt" sz="half" idx="2"/>', [measured_paragraph('date')], lst=lvl(1, 'sz="900"')),
        measured_shape('MFtr', '<p:ph type="ftr" sz="quarter" idx="3"/>', [measured_paragraph('ftr')]),
        measured_shape('MNum', '<p:ph type="sldNum" sz="quarter" idx="4"/>', [measured_paragraph('num')]),
    ]
    L1 = [
        measured_shape('LTitle', '<p:ph type="title"/>', [measured_paragraph('Layout title')], lst=lvl(1, 'sz="4000"')),
        measured_shape('LBody', '<p:ph idx="1"/>', [measured_paragraph('Layout body')]),
        measured_shape('LBody20', '<p:ph type="body" idx="20"/>', [measured_paragraph('b20')], lst=lvl(1, 'sz="2600"')),
        measured_shape('LObj', '<p:ph type="obj" idx="21"/>', [measured_paragraph('obj')]),
        measured_shape('LTbl', '<p:ph type="tbl" idx="22"/>', [measured_paragraph('tbl')]),
        measured_shape('LChart', '<p:ph type="chart" idx="23"/>', [measured_paragraph('chart')]),
        measured_shape('LMedia', '<p:ph type="media" idx="24"/>', [measured_paragraph('media')]),
        measured_shape('LDate', '<p:ph type="dt" sz="half" idx="10"/>', [measured_paragraph('date')]),
        measured_shape('LFtr', '<p:ph type="ftr" sz="quarter" idx="11"/>', [measured_paragraph('ftr')]),
        measured_shape('LNum', '<p:ph type="sldNum" sz="quarter" idx="12"/>', [measured_paragraph('num')]),
        measured_shape('LPic', '<p:ph type="pic" idx="13"/>', [measured_paragraph('pic')]),
    ]
    SLIDE = [
        measured_shape('S1_title_layoutlst', '<p:ph type="title"/>', [measured_paragraph('S1')], y=0),
        measured_shape('S2_body_masterlst', '<p:ph idx="1"/>', [measured_paragraph('S2'), measured_paragraph('S2 lvl2', '<a:pPr lvl="1"/>')], y=1),
        measured_shape('S3_body_layoutlst', '<p:ph type="body" idx="20"/>', [measured_paragraph('S3')], y=2),
        measured_shape('S4_obj', '<p:ph type="obj" idx="21"/>', [measured_paragraph('S4')], y=3),
        measured_shape('S5_tbl', '<p:ph type="tbl" idx="22"/>', [measured_paragraph('S5')], y=4),
        measured_shape('S6_chart', '<p:ph type="chart" idx="23"/>', [measured_paragraph('S6')], y=5),
        measured_shape('S7_media', '<p:ph type="media" idx="24"/>', [measured_paragraph('S7')], y=6),
        measured_shape('S8_dt', '<p:ph type="dt" sz="half" idx="10"/>', [measured_paragraph('S8')], y=7),
        measured_shape('S9_ftr', '<p:ph type="ftr" sz="quarter" idx="11"/>', [measured_paragraph('S9')], y=8),
        measured_shape('S10_sldNum', '<p:ph type="sldNum" sz="quarter" idx="12"/>', [measured_paragraph('S10')], y=9),
        measured_shape('S11_textbox_lst', None, [measured_paragraph('S11')], lst=lvl(1, 'sz="1700"'), txbox=True, y=10),
        measured_shape('S12_textbox_lvl2', None, [measured_paragraph('S12', '<a:pPr lvl="1"/>')], txbox=True, y=11),
        measured_shape('S13_body_slidelst_bold', '<p:ph idx="1"/>', [measured_paragraph('S13')], lst=lvl(1, 'b="1"'), y=12),
        measured_shape('S14_ph_noattr', '<p:ph/>', [measured_paragraph('S14')], y=13),
        measured_shape('S15_pic', '<p:ph type="pic" idx="13"/>', [measured_paragraph('S15')], y=14),
        measured_shape('S16_shape_lst', None, [measured_paragraph('S16')], lst=lvl(1, 'sz="1900"'), y=15),
    ]
    path = package(tmp_path, slide="".join(SLIDE), layout="".join(L1),
                   master="".join(MASTER), tx=TX, default=DTS)
    actual = [(r.text, r.font_size_pt, r.bold, r.italic, r.underline, r.superscript, r.subscript)
              for r in read_runs(path) if r.text != "LAYOUT TEXTBOX"]
    assert actual == [
        ('S1', 40.0, True, False, False, False, False),
        ('S2', 30.0, False, True, False, False, False),
        ('S2 lvl2', 24.0, False, False, False, False, False),
        ('S3', 26.0, False, True, False, False, False),
        ('S4', 30.0, False, True, False, False, False),
        ('S5', 30.0, False, True, False, False, False),
        ('S6', 30.0, False, True, False, False, False),
        ('S7', 30.0, False, True, False, False, False),
        ('S8', 9.0, False, False, False, False, False),
        ('S9', 11.0, False, False, False, False, False),
        ('S10', 11.0, False, False, False, False, False),
        ('S11', 17.0, False, False, False, False, False),
        ('S12', 10.5, False, False, False, False, False),
        ('S13', 30.0, True, True, False, False, False),
        ('S14', 40.0, True, False, False, False, False),
        ('S15', 30.0, False, True, False, False, False),
        ('S16', 19.0, False, False, False, False, False),
    ]



def test_layout_context_keeps_master_relationship(tmp_path):
    from dochan.ooxml.package import OOXMLPackage
    from dochan.ooxml.pptx_styles import TextStyleResolver
    path = package(tmp_path)
    with OOXMLPackage(str(path)) as archive:
        presentation = archive.read_xml_part('ppt/presentation.xml')
        resolver = TextStyleResolver(archive, presentation, [], lambda node: None)
        layout_path = 'ppt/slideLayouts/slideLayout1.xml'
        layout = archive.read_xml_part(layout_path)
        ancestor_layout, master = resolver.context(layout, layout_path)
        assert ancestor_layout is None
        assert master.tag == '{%s}sldMaster' % P_NS


@pytest.mark.parametrize('kind', ['dgm', 'clipArt', 'pic', 'tbl', 'chart', 'media', 'obj', 'subTitle'])
def test_body_family_placeholders_inherit_master_body(tmp_path, kind):
    # PowerPoint RULES 2, deck2 S4/S5/S6/S7/S15.
    path = package(tmp_path, slide=shape(ph='type="%s" idx="7"' % kind),
                   master=shape(style=level('sz="3000"')),
                   tx='<p:bodyStyle>%s</p:bodyStyle>' % level('sz="2800" i="1"'))
    run = read_runs(path)[0]
    assert run.font_size_pt == 30 and run.italic


def test_all_level_styles_outrank_nearer_default_paragraph_style(tmp_path):
    # PowerPoint RULES 6, deck1 S7 and deck2 S11/S16.
    default_paragraph = '<a:defPPr><a:defRPr b="1" sz="4400"/></a:defPPr>'
    path = package(tmp_path, slide=shape(style=default_paragraph),
                   layout=shape(style=default_paragraph), master=shape(style=default_paragraph),
                   default=level('sz="1100" b="0"'))
    run = read_runs(path)[0]
    assert run.font_size_pt == 11 and not run.bold


def test_exhausted_part_does_not_disable_another_part(monkeypatch):
    from lxml import etree
    import dochan.ooxml.pptx_styles as styles
    monkeypatch.setattr(styles, 'MAX_STYLE_NODES', 20)
    resolver, parser = resolver_for_test()
    bad = etree.fromstring(('<a:lstStyle xmlns:a="%s">%s</a:lstStyle>' %
                           (A_NS, '<a:lvl9pPr/>' * 100)).encode(), parser)
    good = etree.fromstring(('<a:lstStyle xmlns:a="%s">%s</a:lstStyle>' %
                            (A_NS, level('b="1"'))).encode(), parser)
    assert resolver._list_properties(bad, 0) == {}
    assert resolver._list_properties(good, 0) == {'b': '1'}


def test_style_budget_is_shared_by_trees_of_same_part(monkeypatch):
    from lxml import etree
    import dochan.ooxml.pptx_styles as styles
    monkeypatch.setattr(styles, 'MAX_STYLE_NODES', 2)
    resolver, parser = resolver_for_test()
    # R2: identical XML reparses must reuse the first result. The old second
    # expectation ({}) pinned the repeated-budget bug (888 lost styled runs).
    for _ in range(2):
        node = etree.fromstring(('<a:lstStyle xmlns:a="%s">%s</a:lstStyle>' %
                                (A_NS, level('b="1"'))).encode(), parser)
        resolver.root_paths[node] = 'ppt/slides/slide1.xml'
        assert resolver._list_properties(node, 0) == {'b': '1'}
    assert resolver.nodes['ppt/slides/slide1.xml'] == 2
    assert not resolver.errors


def alternating_layout_package(tmp_path, slides, shapes=1, padding=0):
    styles = ''.join(level('sz="3200" b="1"', n) for n in range(9))
    path = package(tmp_path, slide='', default=level('sz="1000"'),
                   layout='<!--%s-->%s' % ('x' * padding, ''.join(
                       shape('static%d' % n, ph=None, style=styles) for n in range(shapes))))
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    parts['ppt/slideLayouts/slideLayout2.xml'] = parts['ppt/slideLayouts/slideLayout1.xml']
    parts['ppt/slideLayouts/_rels/slideLayout2.xml.rels'] = parts['ppt/slideLayouts/_rels/slideLayout1.xml.rels']
    ns = 'xmlns:p="%s" xmlns:a="%s" xmlns:r="%s"' % (P_NS, A_NS, R_NS)
    parts['ppt/presentation.xml'] = (
        '<p:presentation %s><p:sldIdLst>%s</p:sldIdLst><p:defaultTextStyle>%s'
        '</p:defaultTextStyle></p:presentation>' % (ns, ''.join(
            '<p:sldId id="%d" r:id="r%d"/>' % (255 + i, i) for i in range(1, slides + 1)),
            level('sz="1000"')))
    parts['ppt/_rels/presentation.xml.rels'] = '<Relationships xmlns="%s">%s</Relationships>' % (
        REL_NS, ''.join('<Relationship Id="r%d" Type="%s/slide" Target="slides/slide%d.xml"/>' %
                       (i, R_NS, i) for i in range(1, slides + 1)))
    for i in range(1, slides + 1):
        parts['ppt/slides/slide%d.xml' % i] = parts['ppt/slides/slide1.xml']
        parts['ppt/slides/_rels/slide%d.xml.rels' % i] = (
            '<Relationships xmlns="%s"><Relationship Id="r1" Type="%s/slideLayout" '
            'Target="../slideLayouts/slideLayout%d.xml"/></Relationships>' %
            (REL_NS, R_NS, 1 + (i - 1) % 2))
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return path


@pytest.mark.parametrize('slides', [100, 200])
def test_alternating_layouts_do_not_retain_content_trees(tmp_path, slides):
    from lxml import etree

    def roots_in(value):
        if isinstance(value, etree._Element):
            return {value.getroottree().getroot()}
        if isinstance(value, dict):
            return roots_in(list(value.keys()) + list(value.values()))
        if isinstance(value, (tuple, list)):
            return {root for item in value for root in roots_in(item)}
        return set()

    reader = PPTXReader()
    doc = reader.read(str(alternating_layout_package(tmp_path, slides, padding=100000)))
    assert not doc.errors, doc.errors
    assert len(doc.find_all('paragraph')) == slides
    roots = roots_in(vars(reader._text_styles))
    assert sum(root.tag == '{%s}sldLayout' % P_NS for root in roots) <= 2
    assert not any(root.tag == '{%s}sld' % P_NS for root in roots)


def test_alternating_layouts_preserve_styles_after_reparsing(tmp_path):
    reader = PPTXReader()
    doc = reader.read(str(alternating_layout_package(tmp_path, 60, shapes=200)))
    runs = [r for p in doc.find_all('paragraph') for r in p.runs]
    assert len(runs) == 12000
    assert sum(r.font_size_pt == 32 and r.bold for r in runs) == 12000
    assert not doc.errors, doc.errors


def test_reparsed_style_cache_distinguishes_parts_shapes_and_levels(tmp_path):
    path = alternating_layout_package(tmp_path, 4)
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for part, size in [(1, 3200), (2, 4200)]:
        styles = level('sz="%d" b="1"' % size) + level('sz="2100" i="1"', 1)
        # Both shapes deliberately have cNvPr id=2. A paragraph override must
        # not leak into the next paragraph or a later reparse of this layout.
        first = shape(ph=None, style=styles, props='<a:pPr><a:defRPr b="0"/></a:pPr>')
        first = first.replace('</a:p></p:txBody>', '</a:p>' +
                              measured_paragraph('level1', '<a:pPr lvl="1"/>') +
                              measured_paragraph('level0') + '</p:txBody>')
        second = shape('other', ph=None, style=level('sz="1700"'))
        parts['ppt/slideLayouts/slideLayout%d.xml' % part] = (
            '<p:sldLayout xmlns:p="%s" xmlns:a="%s"><p:cSld><p:spTree>%s%s'
            '</p:spTree></p:cSld></p:sldLayout>' % (P_NS, A_NS, first, second))
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    doc = PPTXReader().read(str(path))
    assert not doc.errors, doc.errors
    for section, size in zip(doc.sections, [32, 42, 32, 42]):
        assert [(r.font_size_pt, r.bold, r.italic) for p in section.elements for r in p.runs] == [
            (size, False, False), (21, False, True), (size, True, False), (17, False, False)]


def test_content_tree_released_on_parse_failure(tmp_path, monkeypatch):
    reader = PPTXReader()

    def fail(*args, **kwargs):
        raise ValueError('synthetic content failure')

    monkeypatch.setattr(reader, '_collect_positioned_elements', fail)
    doc = reader.read(str(alternating_layout_package(tmp_path, 2)))
    assert any('synthetic content failure' in e for e in doc.errors)
    assert reader._last_layout_content == ('', None)
    assert not any(root.tag == '{%s}sldLayout' % P_NS for root in reader._text_styles.root_paths)
