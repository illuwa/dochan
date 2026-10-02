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
    assert not free.bold and not free.italic and free.underline


def test_ancestor_paragraph_defaults_not_sample_run_properties(tmp_path):
    ancestor = shape(props='<a:pPr lvl="2"><a:defRPr b="1"/></a:pPr>',
                     style=level('i="1"', 2),
                     runs='<a:r><a:rPr u="sng"/><a:t>sample</a:t></a:r><a:endParaRPr baseline="30000"/>')
    path = package(tmp_path, slide=shape(props='<a:pPr lvl="2"/>'), layout=ancestor)
    run = read_runs(path)[0]
    assert run.bold and run.italic
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


def test_missing_type_uses_body_and_missing_index_uses_zero(tmp_path):
    path = package(tmp_path, slide=shape(ph=''), layout=shape(ph='', style=level('i="1"')),
                   tx='<p:bodyStyle>%s</p:bodyStyle>' % level('b="1"'))
    run = read_runs(path)[0]
    assert run.bold and run.italic


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


def test_master_exact_type_and_index_win_before_family(tmp_path):
    path = package(tmp_path, slide=shape(ph='type="obj" idx="7"'),
                   master=shape(ph='type="body" idx="7"', style=level('b="1"')) +
                   shape(ph='type="obj" idx="1"', style=level('i="1"')) +
                   shape(ph='type="obj" idx="7"', style=level('u="sng"')))
    run = read_runs(path)[0]
    assert run.underline and not run.bold and not run.italic
