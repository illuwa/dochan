"""Untrusted attribute callbacks must keep Python's evaluation semantics."""
import pytest

from dochan.pdf import content

clines = pytest.importorskip("dochan.pdf._clines")


def test_custom_order_callback_delegates_before_running_it():
    called = []
    fragments = []

    class MutatingOrder(int):
        def __lt__(self, other):
            called.append(True)
            fragments[-1].x = -100.0
            return super().__lt__(other)

    fragments.extend([
        content.Fragment(0.0, 0.0, 1.0, 10.0, "a", 2.0, order=1),
        content.Fragment(1.0, 0.0, 1.0, 10.0, "b", 2.0, order=MutatingOrder(0)),
        content.Fragment(0.0, 50.0, 1.0, 10.0, "c", 2.0),
        content.Fragment(10.0, 50.0, 1.0, 10.0, "d", 2.0),
    ])
    result = clines.assemble_lines(fragments, content._Line, content._Segment,
                                   content.Fragment, content._LINE_Y_TOLERANCE)
    assert result is None
    assert called == []


def test_nonstandard_list_delegates_without_iteration():
    class Fragments(list):
        def __iter__(self):
            raise RuntimeError("custom iteration")

    assert clines.assemble_lines(Fragments(), content._Line, content._Segment,
                                content.Fragment, content._LINE_Y_TOLERANCE) is None


@pytest.mark.parametrize("field,value", [
    ("text", type("CustomText", (str,), {})("x")),
    ("note_ref", type("CustomNote", (int,), {})(0)),
    ("invisible", type("CustomFlag", (int,), {})(0)),
    ("link_spans", type("CustomSpans", (list,), {})([])),
    ("comment_markers", [(0, type("CustomMarker", (int,), {})(1))]),
    ("link_spans", [(0, 1, type("CustomTarget", (str,), {})("target"))]),
])
def test_callback_capable_attributes_delegate_entire_call(field, value):
    fragment = content.Fragment(0.0, 0.0, 1.0, 10.0, "x", 2.0)
    setattr(fragment, field, value)
    assert clines.assemble_lines([fragment], content._Line, content._Segment,
                                content.Fragment, content._LINE_Y_TOLERANCE) is None
