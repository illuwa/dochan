"""Generated facts from [MS-XLS] 2.5.198.17 Ftab; do not edit by hand.

Source: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-xls/00b5dd7d-51ca-4938-b7b7-483fe0e5933b
Regenerate: python -m scripts.generate_xls_ftab INPUT_JSON OUTPUT_PY
Input JSON SHA-256: f30365f746837d0ce65b6ebc4ffb7210d223e8fa62b5b76a373c29ca4db2813d
"""

# Includes the UDF sentinel as an official label, not a callable name.
FUNCTION_NAMES = {
    0x0000: 'COUNT',
    0x0001: 'IF',
    0x0002: 'ISNA',
    0x0003: 'ISERROR',
    0x0004: 'SUM',
    0x0005: 'AVERAGE',
    0x0006: 'MIN',
    0x0007: 'MAX',
    0x0008: 'ROW',
    0x0009: 'COLUMN',
    0x000A: 'NA',
    0x000B: 'NPV',
    0x000C: 'STDEV',
    0x000D: 'DOLLAR',
    0x000E: 'FIXED',
    0x000F: 'SIN',
    0x0010: 'COS',
    0x0011: 'TAN',
    0x0012: 'ATAN',
    0x0013: 'PI',
    0x0014: 'SQRT',
    0x0015: 'EXP',
    0x0016: 'LN',
    0x0017: 'LOG10',
    0x0018: 'ABS',
    0x0019: 'INT',
    0x001A: 'SIGN',
    0x001B: 'ROUND',
    0x001C: 'LOOKUP',
    0x001D: 'INDEX',
    0x001E: 'REPT',
    0x001F: 'MID',
    0x0020: 'LEN',
    0x0021: 'VALUE',
    0x0022: 'TRUE',
    0x0023: 'FALSE',
    0x0024: 'AND',
    0x0025: 'OR',
    0x0026: 'NOT',
    0x0027: 'MOD',
    0x0028: 'DCOUNT',
    0x0029: 'DSUM',
    0x002A: 'DAVERAGE',
    0x002B: 'DMIN',
    0x002C: 'DMAX',
    0x002D: 'DSTDEV',
    0x002E: 'VAR',
    0x002F: 'DVAR',
    0x0030: 'TEXT',
    0x0031: 'LINEST',
    0x0032: 'TREND',
    0x0033: 'LOGEST',
    0x0034: 'GROWTH',
    0x0035: 'GOTO',
    0x0036: 'HALT',
    0x0037: 'RETURN',
    0x0038: 'PV',
    0x0039: 'FV',
    0x003A: 'NPER',
    0x003B: 'PMT',
    0x003C: 'RATE',
    0x003D: 'MIRR',
    0x003E: 'IRR',
    0x003F: 'RAND',
    0x0040: 'MATCH',
    0x0041: 'DATE',
    0x0042: 'TIME',
    0x0043: 'DAY',
    0x0044: 'MONTH',
    0x0045: 'YEAR',
    0x0046: 'WEEKDAY',
    0x0047: 'HOUR',
    0x0048: 'MINUTE',
    0x0049: 'SECOND',
    0x004A: 'NOW',
    0x004B: 'AREAS',
    0x004C: 'ROWS',
    0x004D: 'COLUMNS',
    0x004E: 'OFFSET',
    0x004F: 'ABSREF',
    0x0050: 'RELREF',
    0x0051: 'ARGUMENT',
    0x0052: 'SEARCH',
    0x0053: 'TRANSPOSE',
    0x0054: 'ERROR',
    0x0055: 'STEP',
    0x0056: 'TYPE',
    0x0057: 'ECHO',
    0x0058: 'SET.NAME',
    0x0059: 'CALLER',
    0x005A: 'DEREF',
    0x005B: 'WINDOWS',
    0x005C: 'SERIES',
    0x005D: 'DOCUMENTS',
    0x005E: 'ACTIVE.CELL',
    0x005F: 'SELECTION',
    0x0060: 'RESULT',
    0x0061: 'ATAN2',
    0x0062: 'ASIN',
    0x0063: 'ACOS',
    0x0064: 'CHOOSE',
    0x0065: 'HLOOKUP',
    0x0066: 'VLOOKUP',
    0x0067: 'LINKS',
    0x0068: 'INPUT',
    0x0069: 'ISREF',
    0x006A: 'GET.FORMULA',
    0x006B: 'GET.NAME',
    0x006C: 'SET.VALUE',
    0x006D: 'LOG',
    0x006E: 'EXEC',
    0x006F: 'CHAR',
    0x0070: 'LOWER',
    0x0071: 'UPPER',
    0x0072: 'PROPER',
    0x0073: 'LEFT',
    0x0074: 'RIGHT',
    0x0075: 'EXACT',
    0x0076: 'TRIM',
    0x0077: 'REPLACE',
    0x0078: 'SUBSTITUTE',
    0x0079: 'CODE',
    0x007A: 'NAMES',
    0x007B: 'DIRECTORY',
    0x007C: 'FIND',
    0x007D: 'CELL',
    0x007E: 'ISERR',
    0x007F: 'ISTEXT',
    0x0080: 'ISNUMBER',
    0x0081: 'ISBLANK',
    0x0082: 'T',
    0x0083: 'N',
    0x0084: 'FOPEN',
    0x0085: 'FCLOSE',
    0x0086: 'FSIZE',
    0x0087: 'FREADLN',
    0x0088: 'FREAD',
    0x0089: 'FWRITELN',
    0x008A: 'FWRITE',
    0x008B: 'FPOS',
    0x008C: 'DATEVALUE',
    0x008D: 'TIMEVALUE',
    0x008E: 'SLN',
    0x008F: 'SYD',
    0x0090: 'DDB',
    0x0091: 'GET.DEF',
    0x0092: 'REFTEXT',
    0x0093: 'TEXTREF',
    0x0094: 'INDIRECT',
    0x0095: 'REGISTER',
    0x0096: 'CALL',
    0x0097: 'ADD.BAR',
    0x0098: 'ADD.MENU',
    0x0099: 'ADD.COMMAND',
    0x009A: 'ENABLE.COMMAND',
    0x009B: 'CHECK.COMMAND',
    0x009C: 'RENAME.COMMAND',
    0x009D: 'SHOW.BAR',
    0x009E: 'DELETE.MENU',
    0x009F: 'DELETE.COMMAND',
    0x00A0: 'GET.CHART.ITEM',
    0x00A1: 'DIALOG.BOX',
    0x00A2: 'CLEAN',
    0x00A3: 'MDETERM',
    0x00A4: 'MINVERSE',
    0x00A5: 'MMULT',
    0x00A6: 'FILES',
    0x00A7: 'IPMT',
    0x00A8: 'PPMT',
    0x00A9: 'COUNTA',
    0x00AA: 'CANCEL.KEY',
    0x00AB: 'FOR',
    0x00AC: 'WHILE',
    0x00AD: 'BREAK',
    0x00AE: 'NEXT',
    0x00AF: 'INITIATE',
    0x00B0: 'REQUEST',
    0x00B1: 'POKE',
    0x00B2: 'EXECUTE',
    0x00B3: 'TERMINATE',
    0x00B4: 'RESTART',
    0x00B5: 'HELP',
    0x00B6: 'GET.BAR',
    0x00B7: 'PRODUCT',
    0x00B8: 'FACT',
    0x00B9: 'GET.CELL',
    0x00BA: 'GET.WORKSPACE',
    0x00BB: 'GET.WINDOW',
    0x00BC: 'GET.DOCUMENT',
    0x00BD: 'DPRODUCT',
    0x00BE: 'ISNONTEXT',
    0x00BF: 'GET.NOTE',
    0x00C0: 'NOTE',
    0x00C1: 'STDEVP',
    0x00C2: 'VARP',
    0x00C3: 'DSTDEVP',
    0x00C4: 'DVARP',
    0x00C5: 'TRUNC',
    0x00C6: 'ISLOGICAL',
    0x00C7: 'DCOUNTA',
    0x00C8: 'DELETE.BAR',
    0x00C9: 'UNREGISTER',
    0x00CC: 'USDOLLAR',
    0x00CD: 'FINDB',
    0x00CE: 'SEARCHB',
    0x00CF: 'REPLACEB',
    0x00D0: 'LEFTB',
    0x00D1: 'RIGHTB',
    0x00D2: 'MIDB',
    0x00D3: 'LENB',
    0x00D4: 'ROUNDUP',
    0x00D5: 'ROUNDDOWN',
    0x00D6: 'ASC',
    0x00D7: 'DBCS',
    0x00D8: 'RANK',
    0x00DB: 'ADDRESS',
    0x00DC: 'DAYS360',
    0x00DD: 'TODAY',
    0x00DE: 'VDB',
    0x00DF: 'ELSE',
    0x00E0: 'ELSE.IF',
    0x00E1: 'END.IF',
    0x00E2: 'FOR.CELL',
    0x00E3: 'MEDIAN',
    0x00E4: 'SUMPRODUCT',
    0x00E5: 'SINH',
    0x00E6: 'COSH',
    0x00E7: 'TANH',
    0x00E8: 'ASINH',
    0x00E9: 'ACOSH',
    0x00EA: 'ATANH',
    0x00EB: 'DGET',
    0x00EC: 'CREATE.OBJECT',
    0x00ED: 'VOLATILE',
    0x00EE: 'LAST.ERROR',
    0x00EF: 'CUSTOM.UNDO',
    0x00F0: 'CUSTOM.REPEAT',
    0x00F1: 'FORMULA.CONVERT',
    0x00F2: 'GET.LINK.INFO',
    0x00F3: 'TEXT.BOX',
    0x00F4: 'INFO',
    0x00F5: 'GROUP',
    0x00F6: 'GET.OBJECT',
    0x00F7: 'DB',
    0x00F8: 'PAUSE',
    0x00FB: 'RESUME',
    0x00FC: 'FREQUENCY',
    0x00FD: 'ADD.TOOLBAR',
    0x00FE: 'DELETE.TOOLBAR',
    0x00FF: 'User Defined Function',
    0x0100: 'RESET.TOOLBAR',
    0x0101: 'EVALUATE',
    0x0102: 'GET.TOOLBAR',
    0x0103: 'GET.TOOL',
    0x0104: 'SPELLING.CHECK',
    0x0105: 'ERROR.TYPE',
    0x0106: 'APP.TITLE',
    0x0107: 'WINDOW.TITLE',
    0x0108: 'SAVE.TOOLBAR',
    0x0109: 'ENABLE.TOOL',
    0x010A: 'PRESS.TOOL',
    0x010B: 'REGISTER.ID',
    0x010C: 'GET.WORKBOOK',
    0x010D: 'AVEDEV',
    0x010E: 'BETADIST',
    0x010F: 'GAMMALN',
    0x0110: 'BETAINV',
    0x0111: 'BINOMDIST',
    0x0112: 'CHIDIST',
    0x0113: 'CHIINV',
    0x0114: 'COMBIN',
    0x0115: 'CONFIDENCE',
    0x0116: 'CRITBINOM',
    0x0117: 'EVEN',
    0x0118: 'EXPONDIST',
    0x0119: 'FDIST',
    0x011A: 'FINV',
    0x011B: 'FISHER',
    0x011C: 'FISHERINV',
    0x011D: 'FLOOR',
    0x011E: 'GAMMADIST',
    0x011F: 'GAMMAINV',
    0x0120: 'CEILING',
    0x0121: 'HYPGEOMDIST',
    0x0122: 'LOGNORMDIST',
    0x0123: 'LOGINV',
    0x0124: 'NEGBINOMDIST',
    0x0125: 'NORMDIST',
    0x0126: 'NORMSDIST',
    0x0127: 'NORMINV',
    0x0128: 'NORMSINV',
    0x0129: 'STANDARDIZE',
    0x012A: 'ODD',
    0x012B: 'PERMUT',
    0x012C: 'POISSON',
    0x012D: 'TDIST',
    0x012E: 'WEIBULL',
    0x012F: 'SUMXMY2',
    0x0130: 'SUMX2MY2',
    0x0131: 'SUMX2PY2',
    0x0132: 'CHITEST',
    0x0133: 'CORREL',
    0x0134: 'COVAR',
    0x0135: 'FORECAST',
    0x0136: 'FTEST',
    0x0137: 'INTERCEPT',
    0x0138: 'PEARSON',
    0x0139: 'RSQ',
    0x013A: 'STEYX',
    0x013B: 'SLOPE',
    0x013C: 'TTEST',
    0x013D: 'PROB',
    0x013E: 'DEVSQ',
    0x013F: 'GEOMEAN',
    0x0140: 'HARMEAN',
    0x0141: 'SUMSQ',
    0x0142: 'KURT',
    0x0143: 'SKEW',
    0x0144: 'ZTEST',
    0x0145: 'LARGE',
    0x0146: 'SMALL',
    0x0147: 'QUARTILE',
    0x0148: 'PERCENTILE',
    0x0149: 'PERCENTRANK',
    0x014A: 'MODE',
    0x014B: 'TRIMMEAN',
    0x014C: 'TINV',
    0x014E: 'MOVIE.COMMAND',
    0x014F: 'GET.MOVIE',
    0x0150: 'CONCATENATE',
    0x0151: 'POWER',
    0x0152: 'PIVOT.ADD.DATA',
    0x0153: 'GET.PIVOT.TABLE',
    0x0154: 'GET.PIVOT.FIELD',
    0x0155: 'GET.PIVOT.ITEM',
    0x0156: 'RADIANS',
    0x0157: 'DEGREES',
    0x0158: 'SUBTOTAL',
    0x0159: 'SUMIF',
    0x015A: 'COUNTIF',
    0x015B: 'COUNTBLANK',
    0x015C: 'SCENARIO.GET',
    0x015D: 'OPTIONS.LISTS.GET',
    0x015E: 'ISPMT',
    0x015F: 'DATEDIF',
    0x0160: 'DATESTRING',
    0x0161: 'NUMBERSTRING',
    0x0162: 'ROMAN',
    0x0163: 'OPEN.DIALOG',
    0x0164: 'SAVE.DIALOG',
    0x0165: 'VIEW.GET',
    0x0166: 'GETPIVOTDATA',
    0x0167: 'HYPERLINK',
    0x0168: 'PHONETIC',
    0x0169: 'AVERAGEA',
    0x016A: 'MAXA',
    0x016B: 'MINA',
    0x016C: 'STDEVPA',
    0x016D: 'VARPA',
    0x016E: 'STDEVA',
    0x016F: 'VARA',
    0x0170: 'BAHTTEXT',
    0x0171: 'THAIDAYOFWEEK',
    0x0172: 'THAIDIGIT',
    0x0173: 'THAIMONTHOFYEAR',
    0x0174: 'THAINUMSOUND',
    0x0175: 'THAINUMSTRING',
    0x0176: 'THAISTRINGLENGTH',
    0x0177: 'ISTHAIDIGIT',
    0x0178: 'ROUNDBAHTDOWN',
    0x0179: 'ROUNDBAHTUP',
    0x017A: 'THAIYEAR',
    0x017B: 'RTD',
}

# ref/val = one operand; commas add; / chooses; [] is optional;
# *N(group) repeats 0..N times. Include only min == max.
# Variable functions take the arity from PtgFuncVar.
# No compatibility overrides belong in this specification data.
FIXED_ARGUMENT_COUNTS = {
    0x0002: 1,  # ISNA: isna-params = val
    0x0003: 1,  # ISERROR: iserror-params = val
    0x000A: 0,  # NA: This function takes no parameters
    0x000F: 1,  # SIN: sin-params = val
    0x0010: 1,  # COS: cos-params = val
    0x0011: 1,  # TAN: tan-params = val
    0x0012: 1,  # ATAN: atan-params = val
    0x0013: 0,  # PI: This function takes no parameters
    0x0014: 1,  # SQRT: sqrt-params = val
    0x0015: 1,  # EXP: exp-params = val
    0x0016: 1,  # LN: ln-params = val
    0x0017: 1,  # LOG10: log10-params = val
    0x0018: 1,  # ABS: abs-params = val
    0x0019: 1,  # INT: int-params = val
    0x001A: 1,  # SIGN: sign-params = val
    0x001B: 2,  # ROUND: round-params = val, val
    0x001E: 2,  # REPT: rept-params = val, val
    0x001F: 3,  # MID: mid-params = val, val, val
    0x0020: 1,  # LEN: len-params = val
    0x0021: 1,  # VALUE: value-params = val
    0x0022: 0,  # TRUE: This function takes no parameters
    0x0023: 0,  # FALSE: This function takes no parameters
    0x0026: 1,  # NOT: not-params = val
    0x0027: 2,  # MOD: mod-params = val, val
    0x0028: 3,  # DCOUNT: dcount-params = ref, (ref / val), (ref / val)
    0x0029: 3,  # DSUM: dsum-params = ref, (ref / val), (ref / val)
    0x002A: 3,  # DAVERAGE: daverage-params = ref, (ref / val), (ref / val)
    0x002B: 3,  # DMIN: dmin-params = ref, (ref / val), (ref / val)
    0x002C: 3,  # DMAX: dmax-params = ref, (ref / val), (ref / val)
    0x002D: 3,  # DSTDEV: dstdev-params = ref, (ref / val), (ref / val)
    0x002F: 3,  # DVAR: dvar-params = ref, (ref / val), (ref / val)
    0x0030: 2,  # TEXT: text-params = val, val
    0x0035: 1,  # GOTO: goto-params = ref
    0x003D: 3,  # MIRR: mirr-params = (ref / val), val, val
    0x003F: 0,  # RAND: This function takes no parameters
    0x0041: 3,  # DATE: date-params = val, val, val
    0x0042: 3,  # TIME: time-params = val, val, val
    0x0043: 1,  # DAY: day-params = val
    0x0044: 1,  # MONTH: month-params = val
    0x0045: 1,  # YEAR: year-params = val
    0x0047: 1,  # HOUR: hour-params = val
    0x0048: 1,  # MINUTE: minute-params = val
    0x0049: 1,  # SECOND: second-params = val
    0x004A: 0,  # NOW: This function takes no parameters
    0x004B: 1,  # AREAS: areas-params = ref
    0x004C: 1,  # ROWS: rows-params = (ref / val)
    0x004D: 1,  # COLUMNS: columns-params = (ref / val)
    0x004F: 2,  # ABSREF: absref-params = val, ref
    0x0050: 2,  # RELREF: relref-params = ref, ref
    0x0053: 1,  # TRANSPOSE: transpose-params = val
    0x0055: 0,  # STEP: This function takes no parameters
    0x0056: 1,  # TYPE: type-params = val
    0x0059: 0,  # CALLER: This function takes no parameters
    0x005A: 1,  # DEREF: deref-params = ref
    0x005E: 0,  # ACTIVE.CELL: This function takes no parameters
    0x005F: 0,  # SELECTION: This function takes no parameters
    0x0061: 2,  # ATAN2: atan2-params = val, val
    0x0062: 1,  # ASIN: asin-params = val
    0x0063: 1,  # ACOS: acos-params = val
    0x0069: 1,  # ISREF: isref-params = (ref / val)
    0x006A: 1,  # GET.FORMULA: get-formula-params = (ref / val)
    0x006C: 2,  # SET.VALUE: set-value-params = ref, val
    0x006F: 1,  # CHAR: char-params = val
    0x0070: 1,  # LOWER: lower-params = val
    0x0071: 1,  # UPPER: upper-params = val
    0x0072: 1,  # PROPER: proper-params = val
    0x0075: 2,  # EXACT: exact-params = val, val
    0x0076: 1,  # TRIM: trim-params = val
    0x0077: 4,  # REPLACE: replace-params = val, val, val, val
    0x0079: 1,  # CODE: code-params = val
    0x007E: 1,  # ISERR: iserr-params = val
    0x007F: 1,  # ISTEXT: istext-params = val
    0x0080: 1,  # ISNUMBER: isnumber-params = val
    0x0081: 1,  # ISBLANK: isblank-params = val
    0x0082: 1,  # T: t-params = (ref / val)
    0x0083: 1,  # N: n-params = (ref / val)
    0x0085: 1,  # FCLOSE: fclose-params = val
    0x0086: 1,  # FSIZE: fsize-params = val
    0x0087: 1,  # FREADLN: freadln-params = val
    0x0088: 2,  # FREAD: fread-params = val, val
    0x0089: 2,  # FWRITELN: fwriteln-params = val, val
    0x008A: 2,  # FWRITE: fwrite-params = val, val
    0x008C: 1,  # DATEVALUE: datevalue-params = val
    0x008D: 1,  # TIMEVALUE: timevalue-params = val
    0x008E: 3,  # SLN: sln-params = val, val, val
    0x008F: 4,  # SYD: syd-params = val, val, val, val
    0x00A1: 1,  # DIALOG.BOX: dialog-box-params = (ref / val)
    0x00A2: 1,  # CLEAN: clean-params = val
    0x00A3: 1,  # MDETERM: mdeterm-params = val
    0x00A4: 1,  # MINVERSE: minverse-params = val
    0x00A5: 2,  # MMULT: mmult-params = val, val
    0x00AC: 1,  # WHILE: while-params = val
    0x00AD: 0,  # BREAK: This function takes no parameters
    0x00AE: 0,  # NEXT: This function takes no parameters
    0x00AF: 2,  # INITIATE: initiate-params = val, val
    0x00B0: 2,  # REQUEST: request-params = val, val
    0x00B1: 3,  # POKE: poke-params = val, (ref / val), (ref / val)
    0x00B2: 2,  # EXECUTE: execute-params = val, val
    0x00B3: 1,  # TERMINATE: terminate-params = val
    0x00B8: 1,  # FACT: fact-params = val
    0x00BA: 1,  # GET.WORKSPACE: get-workspace-params = val
    0x00BD: 3,  # DPRODUCT: dproduct-params = ref, (ref / val), (ref / val)
    0x00BE: 1,  # ISNONTEXT: isnontext-params = val
    0x00C3: 3,  # DSTDEVP: dstdevp-params = ref, (ref / val), (ref / val)
    0x00C4: 3,  # DVARP: dvarp-params = ref, (ref / val), (ref / val)
    0x00C6: 1,  # ISLOGICAL: islogical-params = val
    0x00C7: 3,  # DCOUNTA: dcounta-params = ref, (ref / val), (ref / val)
    0x00C8: 1,  # DELETE.BAR: delete-bar-params = val
    0x00C9: 1,  # UNREGISTER: unregister-params = val
    0x00CF: 4,  # REPLACEB: replaceb-params = val, val, val, val
    0x00D2: 3,  # MIDB: midb-params = val, val, val
    0x00D3: 1,  # LENB: lenb-params = val
    0x00D4: 2,  # ROUNDUP: roundup-params = val, val
    0x00D5: 2,  # ROUNDDOWN: rounddown-params = val, val
    0x00D6: 1,  # ASC: asc-params = val
    0x00D7: 1,  # DBCS: dbcs-params = val
    0x00DD: 0,  # TODAY: This function takes no parameters
    0x00DF: 0,  # ELSE: This function takes no parameters
    0x00E0: 1,  # ELSE.IF: else-if-params = val
    0x00E1: 0,  # END.IF: This function takes no parameters
    0x00E5: 1,  # SINH: sinh-params = val
    0x00E6: 1,  # COSH: cosh-params = val
    0x00E7: 1,  # TANH: tanh-params = val
    0x00E8: 1,  # ASINH: asinh-params = val
    0x00E9: 1,  # ACOSH: acosh-params = val
    0x00EA: 1,  # ATANH: atanh-params = val
    0x00EB: 3,  # DGET: dget-params = ref, (ref / val), (ref / val)
    0x00EE: 0,  # LAST.ERROR: This function takes no parameters
    0x00F4: 1,  # INFO: info-params = val
    0x00F5: 0,  # GROUP: This function takes no parameters
    0x00FC: 2,  # FREQUENCY: frequency-params = (ref / val), (ref / val)
    0x00FE: 1,  # DELETE.TOOLBAR: delete-toolbar-params = val
    0x0100: 1,  # RESET.TOOLBAR: reset-toolbar-params = val
    0x0101: 1,  # EVALUATE: evaluate-params = val
    0x0105: 1,  # ERROR.TYPE: error-type-params = val
    0x0109: 3,  # ENABLE.TOOL: enable-tool-params = val, val, val
    0x010A: 3,  # PRESS.TOOL: press-tool-params = val, val, val
    0x010F: 1,  # GAMMALN: gammaln-params = val
    0x0111: 4,  # BINOMDIST: binomdist-params = val, val, val, val
    0x0112: 2,  # CHIDIST: chidist-params = val, val
    0x0113: 2,  # CHIINV: chiinv-params = val, val
    0x0114: 2,  # COMBIN: combin-params = val, val
    0x0115: 3,  # CONFIDENCE: confidence-params = val, val, val
    0x0116: 3,  # CRITBINOM: critbinom-params = val, val, val
    0x0117: 1,  # EVEN: even-params = val
    0x0118: 3,  # EXPONDIST: expondist-params = val, val, val
    0x0119: 3,  # FDIST: fdist-params = val, val, val
    0x011A: 3,  # FINV: finv-params = val, val, val
    0x011B: 1,  # FISHER: fisher-params = val
    0x011C: 1,  # FISHERINV: fisherinv-params = val
    0x011D: 2,  # FLOOR: floor-params = val, val
    0x011E: 4,  # GAMMADIST: gammadist-params = val, val, val, val
    0x011F: 3,  # GAMMAINV: gammainv-params = val, val, val
    0x0120: 2,  # CEILING: ceiling-params = val, val
    0x0121: 4,  # HYPGEOMDIST: hypgeomdist-params = val, val, val, val
    0x0122: 3,  # LOGNORMDIST: lognormdist-params = val, val, val
    0x0123: 3,  # LOGINV: loginv-params = val, val, val
    0x0124: 3,  # NEGBINOMDIST: negbinomdist-params = val, val, val
    0x0125: 4,  # NORMDIST: normdist-params = val, val, val, val
    0x0126: 1,  # NORMSDIST: normsdist-params = val
    0x0127: 3,  # NORMINV: norminv-params = val, val, val
    0x0128: 1,  # NORMSINV: normsinv-params = val
    0x0129: 3,  # STANDARDIZE: standardize-params = val, val, val
    0x012A: 1,  # ODD: odd-params = val
    0x012B: 2,  # PERMUT: permut-params = val, val
    0x012C: 3,  # POISSON: poisson-params = val, val, val
    0x012D: 3,  # TDIST: tdist-params = val, val, val
    0x012E: 4,  # WEIBULL: weibull-params = val, val, val, val
    0x012F: 2,  # SUMXMY2: sumxmy2-params = val, val
    0x0130: 2,  # SUMX2MY2: sumx2my2-params = val, val
    0x0131: 2,  # SUMX2PY2: sumx2py2-params = val, val
    0x0132: 2,  # CHITEST: chitest-params = val, val
    0x0133: 2,  # CORREL: correl-params = val, val
    0x0134: 2,  # COVAR: covar-params = val, val
    0x0135: 3,  # FORECAST: forecast-params = val, val, val
    0x0136: 2,  # FTEST: ftest-params = val, val
    0x0137: 2,  # INTERCEPT: intercept-params = val, val
    0x0138: 2,  # PEARSON: pearson-params = val, val
    0x0139: 2,  # RSQ: rsq-params = val, val
    0x013A: 2,  # STEYX: steyx-params = val, val
    0x013B: 2,  # SLOPE: slope-params = val, val
    0x013C: 4,  # TTEST: ttest-params = val, val, val, val
    0x0145: 2,  # LARGE: large-params = (ref / val), val
    0x0146: 2,  # SMALL: small-params = (ref / val), val
    0x0147: 2,  # QUARTILE: quartile-params = (ref / val), val
    0x0148: 2,  # PERCENTILE: percentile-params = (ref / val), val
    0x014B: 2,  # TRIMMEAN: trimmean-params = (ref / val), val
    0x014C: 2,  # TINV: tinv-params = val, val
    0x0151: 2,  # POWER: power-params = val, val
    0x0156: 1,  # RADIANS: radians-params = val
    0x0157: 1,  # DEGREES: degrees-params = val
    0x015A: 2,  # COUNTIF: countif-params = ref, val
    0x015B: 1,  # COUNTBLANK: countblank-params = ref
    0x015D: 1,  # OPTIONS.LISTS.GET: options-lists-get-params = val
    0x015E: 4,  # ISPMT: ispmt-params = val, val, val, val
    0x015F: 3,  # DATEDIF: datedif-params = val, val, val
    0x0160: 1,  # DATESTRING: datestring-params = val
    0x0161: 2,  # NUMBERSTRING: numberstring-params = val, val
    0x0168: 1,  # PHONETIC: phonetic-params = ref
    0x0170: 1,  # BAHTTEXT: bahttext-params = val
    0x0171: 1,  # THAIDAYOFWEEK: thaidayofweek-params = val
    0x0172: 1,  # THAIDIGIT: thaidigit-params = val
    0x0173: 1,  # THAIMONTHOFYEAR: thaimonthofyear-params = val
    0x0174: 1,  # THAINUMSOUND: thainumsound-params = val
    0x0175: 1,  # THAINUMSTRING: thainumstring-params = val
    0x0176: 1,  # THAISTRINGLENGTH: thaistringlength-params = val
    0x0177: 1,  # ISTHAIDIGIT: isthaidigit-params = val
    0x0178: 1,  # ROUNDBAHTDOWN: roundbahtdown-params = val
    0x0179: 1,  # ROUNDBAHTUP: roundbahtup-params = val
    0x017A: 1,  # THAIYEAR: thaiyear-params = val
}
