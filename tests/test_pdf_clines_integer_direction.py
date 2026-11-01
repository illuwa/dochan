"""Direction integer tags never escape line assembly's direction classifier."""
import struct

import pytest

from dochan.pdf import content

clines = pytest.importorskip('dochan.pdf._clines')


def signature(value):
    if isinstance(value, float):
        return type(value), struct.pack('!d', value)
    if isinstance(value, (list, tuple)):
        return type(value), tuple(map(signature, value))
    if isinstance(value, (content._Line, content._Segment)):
        return type(value), signature(tuple(vars(value).items()))
    return type(value), value


@pytest.mark.parametrize('direction', [(1, 0), (-1, 0), (0, -1), (0, 1),
                                       (1, 1), (-1, -1), (0, 0)])
def test_integer_directions_construct_lines_without_python_init(monkeypatch, direction):
    dx, dy = direction
    fragments = [content.Fragment(float(i), -float(i), 1.0, 10.0,
                                  chr(0xac00 + i), 4.0, order=i,
                                  dir_x=dx, dir_y=dy) for i in range(10)]
    with monkeypatch.context() as pure:
        pure.setattr(content, '_c_assemble_lines', None)
        expected = content.assemble_lines(fragments)

    def unexpected_python_line(self, fragments):
        raise AssertionError('ordinary integer direction delegated to Python')

    monkeypatch.setattr(content._Line, '__init__', unexpected_python_line)
    actual = clines.assemble_lines(fragments, content._Line, content._Segment,
                                  content.Fragment, content._LINE_Y_TOLERANCE)
    assert actual is not None
    assert signature(actual) == signature(expected)
