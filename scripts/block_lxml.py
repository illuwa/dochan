"""lxml import를 차단한 채 모듈을 실행한다.

사용 예: python -m scripts.block_lxml pytest tests/ -q
선택 import가 예외를 삼켜도 시도 횟수를 보고하고 실패로 판정한다.
"""
import importlib.abc
import runpy
import sys


class BlockLxml(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.attempts = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'lxml' or fullname.startswith('lxml.'):
            self.attempts.append(fullname)
            raise ModuleNotFoundError('lxml is blocked for dependency verification')
        return None


def main():
    if len(sys.argv) < 2:
        raise SystemExit('실행할 모듈을 지정하십시오.')
    blocker = BlockLxml()
    sys.meta_path.insert(0, blocker)
    for name in list(sys.modules):
        if name == 'lxml' or name.startswith('lxml.'):
            del sys.modules[name]
    module = sys.argv[1]
    sys.argv = sys.argv[1:]
    try:
        runpy.run_module(module, run_name='__main__')
    finally:
        print('Blocked lxml import attempts: %d' % len(blocker.attempts))
        if blocker.attempts:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
