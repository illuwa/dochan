"""Excel cell number formatting shared by BIFF XLS and OOXML XLSX."""
from datetime import datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from fractions import Fraction
import math
import re
from typing import List, Optional, Tuple

BUILTIN_NUM_FORMATS = {
    0: "General",
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    12: "# ?/?",
    13: "# ??/??",
    14: "m/d/yy",
    15: "d-mmm-yy",
    16: "d-mmm",
    17: "mmm-yy",
    18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM",
    20: "h:mm",
    21: "h:mm:ss",
    22: "m/d/yy h:mm",
    37: "#,##0;(#,##0)",
    38: "#,##0;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)",
    40: "#,##0.00;[Red](#,##0.00)",
    45: "mm:ss",
    46: "[h]:mm:ss",
    47: "mmss.0",
    48: "##0.0E+0",
    49: "@",
}

@dataclass(frozen=True)
class _FormatMetadata:
    kind: str = ""
    decimals: int = 0
    optional_decimals: int = 0
    thousands: bool = False
    currency_symbol: str = ""
    negative_parentheses: bool = False
    pattern: str = ""
    literal_prefix: str = ""
    literal_suffix: str = ""
    denominator_limit: int = 0
    fixed_denominator: int = 0



class SpreadsheetNumberFormatter:
    def _format_cell_value(self, value: str, fmt: str) -> str:
        if not value or not fmt or len(fmt) > 255:
            return value
        try:
            number = float(value)
        except ValueError:
            return value
        try:
            if not math.isfinite(number):
                raise ValueError("nonfinite numeric value")
            selected = self._conditional_format_section(fmt, number)
            conditional_integer = selected != fmt and selected.strip() == "0"
            fmt = selected
            sections = self._format_sections(fmt)
            position = 1 if number < 0 and len(sections) > 1 else 2 if number == 0 and len(sections) > 2 else 0
            # A comma after the last numeric placeholder scales by 1000;
            # emitting its suffix without scaling would change the meaning.
            # Keep the raw value until that display operation is supported.
            if re.search(r"[0#?],+(?![0#?,])", self._format_code_tokens(sections[position])):
                return value
            section = sections[position]
            if not section or section == '""':
                return ""
            temporal_metadata = self._format_metadata(section)
            metadata = self._format_metadata(fmt)
            clean = self._format_code_tokens(section).lower()
            # Select temporal tokens before classification; retain the existing
            # numeric section/parenthesis contract for non-temporal formats.
            if (temporal_metadata.kind in ("date", "time", "duration")
                    or metadata.kind in ("date", "time", "duration")):
                metadata = temporal_metadata
            if (metadata.kind == "decimal" and re.search(r"[0#?].*/.*[0#?]", clean)
                    and "_?" in re.findall(r'"[^"]*"|[\\_*].', fmt)):
                # Unsupported fraction patterns must not become rounded whole
                # numbers when a padding placeholder (_?) is discarded.
                return value
            if metadata.kind == "duration":
                # An explicit negative section is applied to the absolute value
                # without an automatic minus sign (Excel section rules).
                shown = abs(number) if position == 1 else number
                formatted = self._excel_duration(shown, section) if (
                    number >= 0 or getattr(self, "_date_1904", False)) else None
                return formatted if formatted is not None else value
            if metadata.kind in ("date", "time") and number < 0:
                return value
            if conditional_integer:
                return str(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if metadata.kind == "time":
                formatted = self._clock_display(number, section)
                return formatted if formatted is not None else value
            if metadata.kind == "date":
                has_time = "h" in clean or "s" in clean
                precision = self._second_precision(clean)
                if precision is None:
                    return value
                if has_time:
                    ticks = self._temporal_ticks(number, precision)
                    # Use the rounded integral day for the date; float datetime
                    # microseconds can otherwise carry across midnight twice.
                    day = ticks // (86400 * 10 ** precision)
                else:
                    day = number
                if not getattr(self, "_date_1904", False) and 60 <= day < 61:
                    formatted = "1900-02-29"
                else:
                    formatted = self._excel_date(day).strftime("%Y-%m-%d")
                if has_time:
                    clock_fmt = "hh:mm:ss" if "s" in clean else "hh:mm"
                    if precision:
                        clock_fmt += "." + "0" * precision
                    formatted += " " + self._clock_display(number, clock_fmt)
                return formatted
            if metadata.kind == "zero_fill":
                formatted = self._zero_filled_number(number, metadata.pattern)
                return formatted
            if metadata.kind == "fraction":
                formatted = self._fraction_number(number, metadata.denominator_limit,
                                                  metadata.fixed_denominator)
                return self._apply_literal_affixes(formatted, metadata)
            if metadata.kind == "scientific":
                formatted = self._scientific_number(number, section, metadata.decimals)
                return self._apply_literal_affixes(formatted, metadata)
            if metadata.kind == "percent":
                # Excel stores double values and rounds ties away from zero.
                # Excel's display precision is 15 significant decimal digits.
                # Round there first, then avoid binary multiplication artifacts.
                with localcontext() as context:
                    context.prec = max(32, len(value) + metadata.decimals + 4)
                    scaled = Decimal(format(number, ".15g")) * 100
                    if metadata.negative_parentheses and number < 0:
                        scaled = abs(scaled)
                    scaled = scaled.quantize(Decimal(1).scaleb(-metadata.decimals), rounding=ROUND_HALF_UP)
                    formatted = f"{scaled:.{metadata.decimals}f}%"
                formatted = self._apply_literal_affixes(formatted, metadata)
                return f"({formatted.strip()})" if metadata.negative_parentheses and number < 0 else formatted
            if metadata.kind == "decimal":
                separator = "," if metadata.thousands else ""
                display_number = abs(number) if metadata.negative_parentheses and number < 0 else number
                rounded = self._round_decimal(display_number, metadata.decimals)
                formatted = f"{rounded:{separator}.{metadata.decimals}f}"
                if metadata.optional_decimals and "." in formatted:
                    integer, fraction = formatted.split(".", 1)
                    removed = len(fraction) - len(fraction.rstrip("0"))
                    fraction = fraction[:len(fraction) - min(removed, metadata.optional_decimals)]
                    formatted = integer + ("." + fraction if fraction else "")
                if (metadata.currency_symbol and metadata.literal_prefix.isspace()
                        and re.search(r"\[\$[^\]]+\]", section)):
                    formatted = (metadata.currency_symbol + metadata.literal_prefix + formatted
                                 + metadata.literal_suffix)
                else:
                    if metadata.currency_symbol and formatted.startswith("-"):
                        formatted = "-" + metadata.currency_symbol + formatted[1:]
                    else:
                        formatted = metadata.currency_symbol + formatted
                    formatted = self._apply_literal_affixes(
                        formatted, metadata)
                return f"({formatted.strip()})" if metadata.negative_parentheses and number < 0 else formatted
        except (OverflowError, ValueError, InvalidOperation):
            warning = f"WARN: XLSX formatted numeric value is out of range: {value[:80]}"
            errors = getattr(self, "_errors", None)
            if errors is not None and warning not in errors:
                errors.append(warning)
        return value

    def _conditional_format_section(self, fmt: str, number: float) -> str:
        """Select explicit numeric conditions before classifying their tokens."""
        sections = self._format_sections(fmt)
        condition = re.compile(r"\[(<=|>=|<>|=|<|>)\s*(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*\]")
        # Keep offsets while masking literals, so removing an actual condition
        # cannot also remove identical bracket text inside a quoted label.
        masks = [re.sub(r'"[^"]*"|[\\_*].', lambda match: " " * len(match.group()), section)
                 for section in sections]
        if not any(condition.search(mask) for mask in masks[:2]):
            return fmt
        for section, mask in zip(sections[:3], masks[:3]):
            match = condition.search(mask)
            if match is None:
                return section
            operator, threshold = match.groups()
            bound = float(threshold)
            accepted = {"<": number < bound, "<=": number <= bound,
                        ">": number > bound, ">=": number >= bound,
                        "=": number == bound, "<>": number != bound}[operator]
            if accepted:
                return section[:match.start()] + section[match.end():]
        return "General"

    def _format_metadata(self, fmt: str) -> _FormatMetadata:
        cache = getattr(self, "_format_metadata_cache", None)
        if cache is None:
            cache = {}
            self._format_metadata_cache = cache
        cached = cache.get(fmt)
        if cached is not None:
            return cached
        clean_fmt = self._format_code_tokens(fmt)
        lower_fmt = clean_fmt.lower()
        if self._is_duration_format(lower_fmt):
            metadata = _FormatMetadata(kind="duration")
        elif self._is_time_only_format(lower_fmt):
            metadata = _FormatMetadata(kind="time")
        elif self._is_date_format(lower_fmt):
            metadata = _FormatMetadata(kind="date")
        elif self._is_zero_fill_format(fmt):
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            metadata = _FormatMetadata(
                kind="zero_fill",
                pattern=self._format_sections(fmt)[0],
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
            )
        elif self._is_fraction_format(fmt):
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            fixed_denominator = self._fraction_fixed_denominator(fmt)
            if fixed_denominator:
                literal_suffix = re.sub(r"^/\d+", "", literal_suffix)
            metadata = _FormatMetadata(
                kind="fraction",
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
                denominator_limit=self._fraction_denominator_limit(fmt),
                fixed_denominator=fixed_denominator,
            )
        elif self._is_scientific_format(fmt):
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            metadata = _FormatMetadata(
                kind="scientific",
                decimals=self._scientific_decimal_places(fmt),
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
            )
        elif "%" in clean_fmt:
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            metadata = _FormatMetadata(
                kind="percent",
                decimals=self._decimal_places_before_percent(fmt),
                negative_parentheses=self._negative_uses_parentheses(fmt),
                literal_prefix=literal_prefix,
                literal_suffix=literal_suffix,
            )
        else:
            decimals = self._decimal_places(fmt)
            thousands = self._uses_thousands_separator(fmt)
            currency_symbol = self._currency_symbol(fmt)
            literal_prefix, literal_suffix = self._literal_affixes(fmt)
            if decimals is not None or thousands or currency_symbol or literal_prefix or literal_suffix or clean_fmt.strip() == "0":
                metadata = _FormatMetadata(
                    kind="decimal",
                    decimals=decimals if decimals is not None else 0,
                    optional_decimals=self._optional_decimal_places(fmt),
                    thousands=thousands,
                    currency_symbol=currency_symbol,
                    negative_parentheses=self._negative_uses_parentheses(fmt),
                    literal_prefix=literal_prefix,
                    literal_suffix=literal_suffix,
                )
            else:
                metadata = _FormatMetadata()
        cache[fmt] = metadata
        return metadata

    def _is_date_format(self, lower_fmt: str) -> bool:
        lower_fmt = self._format_code_tokens(lower_fmt)
        if "%" in lower_fmt:
            return False
        return any(token in lower_fmt for token in ("yy", "mm", "dd", "mmm", "h:mm"))

    def _is_duration_format(self, lower_fmt: str) -> bool:
        clean_fmt = self._format_without_literals(lower_fmt)
        return bool(re.search(r"\[(?:h+|m+|s+)\]", clean_fmt, re.IGNORECASE))

    def _is_time_only_format(self, lower_fmt: str) -> bool:
        clean_fmt = self._format_sections(self._format_code_tokens(lower_fmt))[0]
        # Separators can be quoted localized text, not only colons.
        if "h" not in clean_fmt and "s" not in clean_fmt:
            return False
        return not any(token in clean_fmt for token in ("y", "d", "mmm"))

    def _excel_date(self, serial: float) -> datetime:
        if getattr(self, "_date_1904", False):
            base = datetime(1904, 1, 1)
        elif serial < 60:
            base = datetime(1899, 12, 31)
        else:
            # Excel's 1900 date system includes the fictitious 1900-02-29 at
            # serial 60.  Dates after that point therefore need one-day offset.
            base = datetime(1899, 12, 30)
        return base + timedelta(days=serial)

    @staticmethod
    def _temporal_ticks(serial: float, precision: int = 0) -> int:
        # Normalize the total seconds to Excel's 15 significant digits, then
        # round once at the displayed precision (including half-second ties).
        seconds = Decimal(format(abs(serial) * 86400, ".15g"))
        with localcontext() as context:
            context.prec = 340
            return int((seconds * 10 ** precision).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    @staticmethod
    def _second_precision(clean: str) -> Optional[int]:
        match = re.search(r"s\]?(\.0+)", clean, re.I)
        precision = len(match[1]) - 1 if match else 0
        return precision if precision <= 3 else None

    def _excel_time(self, serial: float, include_seconds: bool = False) -> str:
        total_seconds = self._temporal_ticks(serial) % 86400
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if include_seconds else f"{hours:02d}:{minutes:02d}"

    def _clock_display(self, serial: float, fmt: str) -> Optional[str]:
        clean = self._format_code_tokens(fmt).lower()
        precision = self._second_precision(clean)
        if precision is None:
            return None
        # Existing normalized wall-clock display remains HH:MM[:SS]. Render
        # explicit seconds-only, single-s and subsecond patterns at their widths.
        explicit = precision or re.search(r"(?<!s)s(?!s)", clean) or ("h" not in clean and "m" not in clean)
        if not explicit:
            result = self._excel_time(serial, include_seconds="s" in clean)
            return result[3:] if "h" not in clean and "s" in clean else result
        return self._render_time_tokens(serial, fmt, elapsed=False)

    def _excel_duration(self, serial: float, fmt: str) -> Optional[str]:
        return self._render_time_tokens(serial, fmt, elapsed=True)

    def _render_time_tokens(self, serial: float, fmt: str, elapsed: bool) -> Optional[str]:
        tokens = re.findall(r'"[^"]*"|[\\_*].|\[[^\]]*\]|h+|m+|s+|\.0+|.', fmt, re.I)
        units = [token.lower() for token in tokens
                 if re.fullmatch(r"\[(?:h+|m+|s+)\]|h+|m+|s+", token, re.I)]
        if not units:
            return None
        if elapsed:
            if not units[0].startswith("[") or any("[" in unit for unit in units[1:]):
                return None
            first = units[0][1:-1]
            tail = [unit[0] for unit in units[1:]]
            allowed = {"h": ([], ["m"], ["m", "s"]), "m": ([], ["s"]), "s": ([],)}
            if tail not in allowed[first[0]] or any(len(unit) > 2 for unit in units[1:]):
                return None
        elif any("[" in unit or len(unit) > 2 for unit in units):
            return None
        precision = self._second_precision(self._format_code_tokens(fmt))
        if precision is None:
            return None
        # A plain m/mm is minutes only next to an hour or second token;
        # otherwise it is a month, which this time renderer does not handle.
        plain = [unit for unit in units if not unit.startswith("[")]
        for index, unit in enumerate(plain):
            if unit[0] != "m":
                continue
            before = plain[index - 1][0] if index else ""
            after = plain[index + 1][0] if index + 1 < len(plain) else ""
            if before != "h" and after != "s" and not (elapsed and units[0].startswith("[h")):
                return None
        ticks = self._temporal_ticks(serial, precision)
        seconds, fraction = divmod(ticks, 10 ** precision)
        result = []
        previous_unit = ""
        for token in tokens:
            lower = token.lower()
            if token.startswith('"'):
                result.append(token[1:-1])
            elif token.startswith("\\"):
                result.append(token[1:])
            elif token.startswith("_"):
                result.append(" ")
            elif token.startswith("*"):
                continue
            elif re.fullmatch(r"\[(h+|m+|s+)\]", lower):
                unit = lower[1:-1]
                result.append(str(seconds // {"h": 3600, "m": 60, "s": 1}[unit[0]]).zfill(len(unit)))
                previous_unit = unit[0]
            elif token.startswith("["):
                continue  # color, condition and locale annotations
            elif re.fullmatch(r"h+|m+|s+", lower):
                component = seconds // {"h": 3600, "m": 60, "s": 1}[lower[0]]
                component %= 24 if lower[0] == "h" else 60
                result.append(str(component).zfill(len(lower)))
                previous_unit = lower[0]
            elif re.fullmatch(r"\.0+", token):
                if previous_unit != "s" or len(token) - 1 != precision:
                    return None
                result.append("." + str(fraction).zfill(precision))
            elif token in (":", " ", "-", "/", ",", ".", "(", ")", "+"):
                result.append(token)
            else:
                return None
        return ("-" if serial < 0 else "") + "".join(result)

    def _zero_filled_number(self, number: float, pattern: str) -> str:
        sign = "-" if number < 0 else ""
        digits = str(int(self._round_decimal(abs(number), 0)))
        tokens = self._format_literal_tokens(pattern)
        width = sum(token == "0" and is_format for token, is_format in tokens)
        overflow = max(len(digits) - width, 0)
        prefix = digits[:overflow]
        digits = digits[overflow:].zfill(width)
        result = []
        digit_index = 0
        for char, is_format in tokens:
            if char == "0" and is_format:
                result.append(digits[digit_index] if digit_index < len(digits) else "0")
                digit_index += 1
            else:
                result.append(char)
        return sign + prefix + "".join(result)

    @staticmethod
    def _round_decimal(number: float, decimals: int) -> Decimal:
        with localcontext() as context:
            context.prec = 340
            decimal = Decimal(format(number, ".15g"))
            return decimal.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)

    def _scientific_number(self, number: float, section: str, decimals: int) -> str:
        exponent_digits = re.search(r"E[+-](0+)", self._format_code_tokens(section), re.I)
        width = len(exponent_digits[1]) if exponent_digits else 2
        if not number:
            exponent, mantissa = 0, Decimal(0)
        else:
            decimal = Decimal(format(abs(number), ".15g"))
            exponent = decimal.adjusted()
            mantissa = self._round_decimal(float(decimal.scaleb(-exponent)), decimals)
            if mantissa >= 10:
                mantissa /= 10
                exponent += 1
        sign = "-" if number < 0 else ""
        return f"{sign}{mantissa:.{decimals}f}E{'+' if exponent >= 0 else '-'}{abs(exponent):0{width}d}"

    def _fraction_number(self, number: float, denominator_limit: int,
                         fixed_denominator: int = 0) -> str:
        sign = "-" if number < 0 else ""
        value = abs(number)
        whole = int(value)
        if fixed_denominator:
            # Excel's mixed fraction first subtracts the whole part in binary.
            # This makes 1.15 land just below the 1.5/10 tie in the fixture;
            # fractions below one use the usual 15-digit display precision.
            with localcontext() as context:
                context.prec = 340
                fractional = (Decimal.from_float(value - whole) if whole
                              else Decimal(format(value, ".15g")))
                numerator = int((fractional * fixed_denominator)
                                .quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if numerator >= fixed_denominator:
                whole += 1
                numerator = 0
            fraction = Fraction(numerator, fixed_denominator)
        else:
            fraction = Fraction(value - whole).limit_denominator(max(denominator_limit, 1))
        if fraction.numerator == fraction.denominator:
            whole += 1
            fraction = Fraction(0, 1)
        if fraction.numerator == 0:
            return f"{sign}{whole}"
        denominator = fixed_denominator or fraction.denominator
        shown_numerator = numerator if fixed_denominator else fraction.numerator
        if whole:
            return f"{sign}{whole} {shown_numerator}/{denominator}"
        return f"{sign}{shown_numerator}/{denominator}"

    def _apply_literal_affixes(self, text: str, metadata: _FormatMetadata) -> str:
        if not metadata.literal_prefix and not metadata.literal_suffix:
            return text
        sign = ""
        if text.startswith("-"):
            sign = "-"
            text = text[1:]
        return f"{sign}{metadata.literal_prefix}{text}{metadata.literal_suffix}"

    def _decimal_places_before_percent(self, fmt: str) -> int:
        before_percent = self._format_code_tokens(fmt).split("%", 1)[0]
        decimals = self._decimal_places(before_percent)
        return decimals if decimals is not None else 0

    def _decimal_places(self, fmt: str):
        match = re.search(r"[0#?]\.([0#?]+)", self._format_code_tokens(fmt))
        if match:
            return len(match.group(1))
        return None

    def _optional_decimal_places(self, fmt: str) -> int:
        match = re.search(r"[0#?]\.([0#?]+)", self._format_code_tokens(fmt))
        return len(match[1]) - len(match[1].rstrip("#?")) if match else 0

    def _uses_thousands_separator(self, fmt: str) -> bool:
        return "," in self._format_without_literals(fmt)

    def _is_zero_fill_format(self, fmt: str) -> bool:
        tokens = self._format_literal_tokens(self._format_sections(fmt)[0])
        clean_fmt = "".join(token for token, is_format in tokens if is_format)
        if "." in clean_fmt or "#" in clean_fmt or "%" in clean_fmt or "," in clean_fmt:
            return False
        if not re.fullmatch(r"0+", clean_fmt):
            return False
        return clean_fmt.count("0") > 1

    def _is_fraction_format(self, fmt: str) -> bool:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        return "/" in first_section and "?" in first_section

    def _fraction_denominator_limit(self, fmt: str) -> int:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        denominator = first_section.rsplit("/", 1)[-1]
        digit_slots = sum(1 for char in denominator if char in {"?", "0", "#"})
        return (10 ** max(digit_slots, 1)) - 1

    def _fraction_fixed_denominator(self, fmt: str) -> int:
        section = self._format_sections(self._format_without_literals(fmt))[0]
        match = re.search(r"/[1-9]\d*", section)
        return int(match.group()[1:]) if match else 0

    def _is_scientific_format(self, fmt: str) -> bool:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        return bool(re.search(r"[0#?](?:\.[0#?]+)?E[+-]0+", first_section, flags=re.IGNORECASE))

    def _scientific_decimal_places(self, fmt: str) -> int:
        clean_fmt = self._format_without_literals(fmt)
        first_section = self._format_sections(clean_fmt)[0]
        mantissa = re.split(r"E[+-]", first_section, maxsplit=1, flags=re.IGNORECASE)[0]
        match = re.search(r"\.([0#?]+)", mantissa)
        return len(match.group(1)) if match else 0

    def _currency_symbol(self, fmt: str) -> str:
        clean_fmt = self._format_without_literals(fmt)
        bracketed = re.search(r"\[\$([^-\]]+)", clean_fmt)
        if bracketed:
            return bracketed.group(1)
        return "$" if "$" in re.sub(r"\[[^\]]*\]", "", clean_fmt) else ""

    def _format_code_tokens(self, fmt: str) -> str:
        """Ignore literal text, colors, conditions and locale annotations."""
        clean = self._format_without_literals(fmt)
        return re.sub(r"\[(?![hmsHMS]+\])[^\]]*\]", "", clean)

    def _format_without_literals(self, fmt: str) -> str:
        # Consume lexical pairs together: _" and \" do not open a quote.
        return re.sub(r'"[^"]*"|[\\_*].', "", fmt)

    def _literal_affixes(self, fmt: str) -> Tuple[str, str]:
        section = self._format_sections(fmt)[0]
        tokens = self._format_literal_tokens(section)
        numeric_indexes = [
            index
            for index, token in enumerate(tokens)
            if token[1] and token[0] in {"0", "#", "?", ".", ",", "%", "$"}
        ]
        if not numeric_indexes:
            return ("", "")
        first_numeric = numeric_indexes[0]
        last_numeric = numeric_indexes[-1]
        prefix = "".join(token for token, is_format in tokens[:first_numeric] if not is_format)
        suffix = "".join(token for token, is_format in tokens[last_numeric + 1:] if not is_format)
        return (prefix, suffix)

    def _format_literal_tokens(self, fmt: str) -> List[Tuple[str, bool]]:
        tokens: List[Tuple[str, bool]] = []
        index = 0
        while index < len(fmt):
            char = fmt[index]
            if char in "_*":
                if char == "_" and index + 1 < len(fmt):
                    tokens.append((" ", False))
                index += 2
                continue
            if char == '"':
                end = fmt.find('"', index + 1)
                if end == -1:
                    tokens.append((fmt[index + 1:], False))
                    break
                tokens.append((fmt[index + 1:end], False))
                index = end + 1
                continue
            if char == "\\":
                if index + 1 < len(fmt):
                    tokens.append((fmt[index + 1], False))
                    index += 2
                else:
                    index += 1
                continue
            if char == "[":
                end = fmt.find("]", index + 1)
                if end != -1:
                    tokens.append((fmt[index:end + 1], True))
                    index = end + 1
                    continue
            tokens.append((char, char in "0#?.,%$"))
            index += 1
        return tokens

    def _negative_uses_parentheses(self, fmt: str) -> bool:
        sections = self._format_sections(fmt)
        if len(sections) < 2:
            return False
        literals = [token for token, is_format in self._format_literal_tokens(sections[1])
                    if not is_format]
        return "(" in literals and ")" in literals

    def _format_sections(self, fmt: str) -> List[str]:
        sections = []
        current = []
        in_quote = False
        escaped = False
        for char in fmt:
            if escaped:
                current.append(char)
                escaped = False
                continue
            if char in "\\_*" and not in_quote:
                current.append(char)
                escaped = True
                continue
            if char == '"':
                current.append(char)
                in_quote = not in_quote
                continue
            if char == ";" and not in_quote:
                sections.append("".join(current))
                current = []
                continue
            current.append(char)
        sections.append("".join(current))
        return sections
