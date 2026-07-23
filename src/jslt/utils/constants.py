import operator
import re

# Operator mapping for safe comparisons
COMPARATORS = {
    "=": operator.eq,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}

COMPARATOR_CHARS = "".join(set("".join(COMPARATORS.keys())))

# Regex for parsing comparison expressions: term1 OP term2
COMP_RE = re.compile(
    f"^([^{COMPARATOR_CHARS}]+)({'|'.join(COMPARATORS.keys())})([^{COMPARATOR_CHARS}]+)$"
)

# Regex for identifying numbers
NUMBER_RE = re.compile(r"^([0-9]*)(\.[0-9]+)?$")

# Regex for identifying strings
STRING_RE = re.compile(r'^"([^"]*)"$')

# Regex for JSLT function signature
JSLT_FUNC_RE = re.compile(r"^([a-z]+):([a-z\_]+)$")

JSL_FUNC_RE = re.compile(r"^\_([a-z]+)\_([a-z\_]+)$")
