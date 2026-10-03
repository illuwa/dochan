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
            sections = self._format_sections(selected)
            position = 1 if number < 0 and len(sections) > 1 else 2 if number == 0 and len(sections) > 2 else 0
            section = sections[position]
            shown = abs(number) if number < 0 and position == 1 else number
            if not section or section == '""':
                return ""
            code = self._format_code_tokens(section)
            if re.search(r"general", code, re.I):
                return self._render_general_section(section, value, number, position)
            if not re.search(r"[0#?@hmsyd]", self._format_code_tokens(section), re.I):
                literal = "".join(token for token, is_format in self._format_literal_tokens(section)
                                  if not is_format)
                # Color/condition annotations alone cannot hide a numeric value.
                residue = re.sub(r"\[[^\]]*\]", "", code)
                if not literal or re.search(r"[^ +\-()/.:!&$£€¥=<>^'`~{}]", residue):
                    return value
                return literal
            metadata = self._format_metadata(section)
            clean = code.lower()
            if metadata.kind != "scientific" and re.search(r"[Ee][+-][0#?]", code):
                return value
            auto_minus = (number < 0 and position == 1
                          and self._is_color_only_negative_section(sections[0], section))
            if number == 0 and position == 2 and "0" not in clean and any(
                    char in clean for char in "#?"):
                return "".join(" " if token == "?" else "" if is_format else token
                               for token, is_format in self._format_literal_tokens(section))
            if (metadata.kind == "decimal" and re.search(r"[0#?].*/.*[0#?]", clean)
                    and "_?" in re.findall(r'"[^"]*"|[\\_*].', section)):
                # Unsupported fraction patterns must not become rounded whole
                # numbers when a padding placeholder (_?) is discarded.
                return value
            if metadata.kind == "duration":
                # An explicit negative section is applied to the absolute value
                # without an automatic minus sign (Excel section rules).
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
                formatted = self._zero_filled_number(shown, metadata.pattern)
                return "-" + formatted if auto_minus else formatted
            if metadata.kind == "fraction":
                formatted = self._fraction_number(shown, metadata.denominator_limit,
                                                  metadata.fixed_denominator)
                formatted = self._apply_literal_affixes(formatted, metadata)
                return "-" + formatted if auto_minus else formatted
            if metadata.kind == "scientific":
                formatted = self._scientific_number(shown, section, metadata.decimals)
                formatted = self._apply_literal_affixes(formatted, metadata)
                return "-" + formatted if auto_minus else formatted
            if metadata.kind == "percent":
                # Excel stores double values and rounds ties away from zero.
                # Excel's display precision is 15 significant decimal digits.
                # Round there first, then avoid binary multiplication artifacts.
                with localcontext() as context:
                    context.prec = max(32, len(value) + metadata.decimals + 4)
                    scaled = Decimal(format(shown, ".15g")) * 100
                    scaled = scaled.quantize(Decimal(1).scaleb(-metadata.decimals), rounding=ROUND_HALF_UP)
                    formatted = f"{scaled:.{metadata.decimals}f}%"
                formatted = self._apply_literal_affixes(formatted, metadata)
                return "-" + formatted if auto_minus else formatted
            if metadata.kind == "decimal":
                if re.search(r"[0#?]\s*/[1-9]\d*", clean) and "?" not in clean:
                    return value
                scale = sum(len(match[0]) for match in re.finditer(
                    r"(?<=[0#?]),+(?=\.|$|[^0#?,])", clean))
                separator = "," if metadata.thousands and (not scale or clean.count(",") > scale) else ""
                display_number = shown / (1000 ** scale)
                rounded = self._round_decimal(display_number, metadata.decimals)
                formatted = f"{rounded:{separator}.{metadata.decimals}f}"
                integer, dot, fraction = formatted.partition(".")
                sign = "-" if integer.startswith("-") else ""
                integer = integer.lstrip("-")
                int_code = clean.split(".", 1)[0]
                numeric_run = re.search(r"[0#?,]+", int_code)
                required = numeric_run[0].count("0") if numeric_run else 0
                if required:
                    integer = integer.replace(",", "").zfill(required)
                    if separator:
                        integer = re.sub(r"(?<=\d)(?=(?:\d{3})+$)", ",", integer)
                formatted = sign + integer + (dot + fraction if dot else "")
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
                    if metadata.currency_symbol:
                        code = self._format_code_tokens(section)
                        symbol_after = code.find("$") > max(code.find("0"), code.find("#"), code.find("?"))
                        if symbol_after:
                            formatted += metadata.currency_symbol
                        elif formatted.startswith("-"):
                            formatted = "-" + metadata.currency_symbol + formatted[1:]
                        else:
                            formatted = metadata.currency_symbol + formatted
                    formatted = self._apply_literal_affixes(
                        formatted, metadata)
                return "-" + formatted if auto_minus else formatted
        except (OverflowError, ValueError, InvalidOperation):
            source = getattr(self, "_format_warning_source", "spreadsheet")
            warning = f"WARN: {source} formatted numeric value is out of range: {value[:80]}"
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
            fixed_denominator = self._fraction_fixed_denominator(fmt)
            affix_pattern = re.sub(r"/[1-9]\d*", "/?", fmt) if fixed_denominator else fmt
            literal_prefix, literal_suffix = self._literal_affixes(affix_pattern)
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
            bracketed = [unit for unit in units if unit.startswith("[")]
            if len(bracketed) != 1 or any(len(unit) > 2 for unit in units if not unit.startswith("[")):
                return None
            kinds = [unit[1] if unit.startswith("[") else unit[0] for unit in units]
            order = "hms"
            if len(set(kinds)) != len(kinds):
                return None
            indexes = sorted(order.index(kind) for kind in kinds)
            if indexes != list(range(indexes[0], indexes[-1] + 1)):
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
            if before != "h" and after != "s" and not (elapsed and any(unit.startswith("[h") for unit in units)):
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
        first_slot = next((index for index, token in enumerate(tokens)
                           if token == ("0", True)), 0)
        result.insert(first_slot, prefix)
        return sign + "".join(result)

    @staticmethod
    def _round_decimal(number: float, decimals: int) -> Decimal:
        with localcontext() as context:
            context.prec = 340
            decimal = Decimal(format(number, ".15g"))
            return decimal.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)

    def _scientific_number(self, number: float, section: str, decimals: int) -> str:
        code = self._format_code_tokens(section)
        exponent_digits = re.search(r"([Ee])[+-](0+)", code)
        width = len(exponent_digits[2]) if exponent_digits else 2
        mantissa_code = re.split(r"[Ee][+-]", code, maxsplit=1)[0]
        integer_slots = max(1, sum(char in "0#?" for char in mantissa_code.split(".", 1)[0]))
        if not number:
            exponent, mantissa = 0, Decimal(0)
        else:
            decimal = Decimal(format(abs(number), ".15g"))
            exponent = decimal.adjusted() // integer_slots * integer_slots
            mantissa = self._round_decimal(float(decimal.scaleb(-exponent)), decimals)
            if mantissa >= 10 ** integer_slots:
                mantissa /= 10 ** integer_slots
                exponent += integer_slots
        sign = "-" if number < 0 else ""
        letter = exponent_digits[1] if exponent_digits else "E"
        return f"{sign}{mantissa:.{decimals}f}{letter}{'+' if exponent >= 0 else '-'}{abs(exponent):0{width}d}"

    def _fraction_number(self, number: float, denominator_limit: int,
                         fixed_denominator: int = 0) -> str:
        sign = "-" if number < 0 else ""
        value = abs(number)
        whole = int(value)
        if fixed_denominator:
            # Round the binary fraction after removing the whole part. This
            # agrees with all fixed-denominator cells in the public Excel table.
            numerator = math.floor((value - whole) * fixed_denominator + 0.5)
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
        match = re.search(r"[0#?],*\.([0#?]+)", self._format_code_tokens(fmt))
        if match:
            return len(match.group(1))
        return None

    def _optional_decimal_places(self, fmt: str) -> int:
        match = re.search(r"[0#?],*\.([0#?]+)", self._format_code_tokens(fmt))
        return len(match[1]) - len(match[1].rstrip("#?")) if match else 0

    _BRACKET = re.compile(r"\[[^\]]*\]")
    # 조건([<0]), 지역·통화([$-412], [$€-2]), 경과 시간([h], [mm], [ss])이 아닌 대괄호는 색 표기다(지역화된 색 이름 포함).
    _COLOR = re.compile(r"\[(?![$<>=])(?![hHmMsS]+\])[^\]]+\]")

    def _is_color_only_negative_section(self, positive: str, negative: str) -> bool:
        """Markdown 에는 색이 없으므로, 색만 다른 음수 구역은 부호를 잃지 않게 - 를 붙인다(계약).

        대괄호 토큰을 지운 뒤 음수 구역의 리터럴이 모두 양수 구역에도 있으면 색만 다른 구역이다.
        음수 구역에만 있는 리터럴(▲·△·U+2212·괄호·" CR")은 작성자의 부호 표기이므로 붙이지 않는다.
        """
        if not self._COLOR.search(negative):
            return False

        def literals(section: str) -> List[str]:
            return [token for token, is_format in self._format_literal_tokens(self._BRACKET.sub("", section))
                    if not is_format and token.strip()]

        positive_literals = literals(positive)
        return all(token in positive_literals for token in literals(negative))

    def _render_general_section(self, section: str, value: str,
                                number: float, position: int) -> str:
        masked = re.sub(r'"[^"]*"|[\\_*].|\[[^\]]*\]',
                        lambda match: " " * len(match[0]), section)
        match = re.search(r"general", masked, re.I)
        if match is None:
            return str(number)
        prefix = "".join(token for token, is_format in
                         self._format_literal_tokens(section[:match.start()]) if not is_format)
        suffix = "".join(token for token, is_format in
                         self._format_literal_tokens(section[match.end():]) if not is_format)
        formatted = value.lstrip("-") if number < 0 and position == 1 and prefix.strip() else value
        if number < 0 and position == 0 and prefix.strip():
            # 한 구역 서식의 음수는 리터럴 앞에 부호가 온다(NumberFormatTests A22 Excel 저장값).
            return "-" + prefix + value.lstrip("-") + suffix
        return prefix + formatted + suffix

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
