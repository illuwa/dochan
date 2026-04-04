"""Equation model — 수식"""
import re
from dataclasses import dataclass


@dataclass
class Equation:
    """한글 수식 (EQEDIT)"""
    script: str = ""

    @property
    def latex(self) -> str:
        """HWP 수식 스크립트 → LaTeX 변환"""
        if not self.script:
            return ""
        return _hwp_to_latex(self.script)


def _hwp_to_latex(script: str) -> str:
    """Basic HWP equation → LaTeX conversion"""
    text = script.strip()

    # Greek letters
    greeks = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta',
              'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'rho', 'sigma',
              'tau', 'upsilon', 'phi', 'chi', 'psi', 'omega',
              'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta', 'Theta',
              'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi', 'Pi', 'Rho', 'Sigma',
              'Tau', 'Upsilon', 'Phi', 'Chi', 'Psi', 'Omega']
    for g in greeks:
        text = re.sub(r'\b' + g + r'\b', lambda m, g=g: '\\' + g, text)

    # Operators
    replacements = {
        ' times ': r' \times ',
        ' pm ': r' \pm ',
        ' inf ': r' \infty ',
        '<=': r'\leq ',
        '>=': r'\geq ',
        '!=': r'\neq ',
        ' cdot ': r' \cdot ',
        ' approx ': r' \approx ',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Functions
    for fn in ['sum', 'int', 'prod', 'lim', 'sin', 'cos', 'tan', 'log', 'ln', 'exp']:
        text = re.sub(r'\b' + fn + r'\b', lambda m, fn=fn: '\\' + fn, text)

    # sqrt
    text = re.sub(r'sqrt\s*\{([^}]*)\}', r'\\sqrt{\1}', text)
    text = re.sub(r'sqrt\s+(\w+)', r'\\sqrt{\1}', text)

    # over -> frac (simple cases: a over b -> \frac{a}{b})
    text = re.sub(r'(\{[^}]+\}|\w+)\s+over\s+(\{[^}]+\}|\w+)', r'\\frac{\1}{\2}', text)

    return text
