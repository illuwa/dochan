"""Audit must not excuse actual visible words or more copies than evidence."""
from collections import Counter

from scripts.check_doc_word_preservation import classify_losses, words


def test_doc_audit_keeps_unexplained_visible_word_loss():
    losses = classify_losses(words('keep missing'), words('keep'), [])
    assert losses['unclassified'] == {'missing': 1}


def test_doc_audit_evidence_is_occurrence_bounded():
    losses = classify_losses(words('same same same'), words('same'),
                             [('tracked_deletion', Counter(same=1))])
    assert losses['tracked_deletion'] == {'same': 1}
    assert losses['unclassified'] == {'same': 1}


def test_doc_audit_does_not_count_one_loss_twice():
    losses = classify_losses(words('word'), Counter(),
                             [('tracked_deletion', Counter(word=1)),
                              ('hidden_field', Counter(word=1))])
    assert losses['tracked_deletion'] == {'word': 1}
    assert not losses['unclassified']
    assert not losses.get('hidden_field')


def test_doc_audit_detects_joined_words_and_preserves_case():
    assert classify_losses(words('Alpha Beta'), words('AlphaBeta'), [])['unclassified'] == {'Alpha': 1, 'Beta': 1}
    assert classify_losses(words('Name'), words('name'), [])['unclassified'] == {'Name': 1}


def binary(text, deleted=(), blobs=None, story_ranges=None):
    from types import SimpleNamespace
    return SimpleNamespace(text=text,
        stories=story_ranges or {'main': (0, len(text))},
        char_props=lambda cp: {'deleted': True} if cp in deleted else {},
        blob=lambda index: (blobs or {}).get(index, b''))


def test_doc_audit_partial_revision_word_needs_surviving_replacement():
    from dochan.office_binary import doc as baseline
    from scripts.check_doc_word_preservation import cp_evidence
    source = binary('IThe word', range(1, 4))
    evidence, _ = cp_evidence(source, baseline, words('I word'))
    assert classify_losses(words('IThe word'), words('I word'), evidence)['unclassified'] == {}
    evidence, _ = cp_evidence(source, baseline, words('word'))
    assert classify_losses(words('IThe word'), words('word'), evidence)['unclassified'] == {'IThe': 1}


def test_doc_audit_optional_hyphen_requires_complete_output_word():
    from dochan.office_binary import doc as baseline
    from scripts.check_doc_word_preservation import cp_evidence
    source = binary('doc\x1fument')
    evidence, _ = cp_evidence(source, baseline, words('document'))
    assert classify_losses(words('doc ument'), words('document'), evidence)['optional_hyphen'] == {'doc': 1, 'ument': 1}
    evidence, _ = cp_evidence(source, baseline, Counter())
    assert classify_losses(words('doc ument'), Counter(), evidence)['unclassified'] == {'doc': 1, 'ument': 1}


def test_doc_audit_controls_do_not_excuse_discarded_normal_text():
    from dochan.office_binary import doc as baseline
    from scripts.check_doc_word_preservation import cp_evidence
    source = binary('one\x01two keep')
    evidence, _ = cp_evidence(source, baseline, words('onetwo'))
    losses = classify_losses(words('one two keep'), words('onetwo'), evidence)
    assert losses['control_character_normalization'] == {'one': 1, 'two': 1}
    assert losses['unclassified'] == {'keep': 1}


def test_doc_audit_bookmark_annotation_does_not_split_source_word():
    from dochan.conversion import Provenance
    from dochan.model.document import Document, Paragraph, Section, TextRun
    from scripts.check_doc_word_preservation import document_text
    provenance = Provenance(source_format='doc', path='WordDocument#cp0')
    doc = Document(sections=[Section(elements=[Paragraph(runs=[
        TextRun('P', provenance=provenance), TextRun('[bookmark: Label] '),
        TextRun('aragraph', provenance=provenance)])])])
    assert document_text(doc) == 'Paragraph'


def test_doc_audit_malformed_header_plc_is_not_a_loss_exemption():
    from dochan.office_binary import doc as baseline
    from scripts.check_doc_word_preservation import cp_evidence
    source = binary('body\rheader\r', blobs={11: b'bad'},
        story_ranges={'main': (0, 5), 'header': (5, 12)})
    evidence, _ = cp_evidence(source, baseline, words('body'))
    losses = classify_losses(words('body header'), words('body'), evidence)
    assert losses['unclassified'] == {'header': 1}


def test_doc_audit_new_document_error_fails_even_if_both_outputs_empty():
    from scripts.check_doc_word_preservation import has_new_fatal
    assert has_new_fatal([], ['ERR: parser failure'])
    assert not has_new_fatal(['ERR: unsupported'], ['ERR: unsupported'])
    assert not has_new_fatal([], ['WARN: unsupported formatting'])
