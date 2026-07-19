import jmespath
import logging
import re
from typing import Optional, Any, Self

from jslt.utils.constants import COMPARATORS, COMPARATOR_CHARS, COMP_RE, NUMBER_RE, STRING_RE
from jslt.utils.types import Number

from jslt.models.json import JSON

class JSONList(JSON):
    """Wrapper for JSON arrays with JMESPath and DSL support."""
    
    __slots__ = ["__logger__", "__children__"]
        
    def __init__(self, children: Optional[list[JSON]] = []):
        logger = logging.getLogger(self.__class__.__name__)
        super().__setattr__("__logger__", logger)
        super().__setattr__("__children__", children)

    def append(self, child: JSON) -> None:
        children = super().__getattribute__("__children__")
        children.append(child)

    def to_json(self) -> list:
        return [c.to_json() if isinstance(c, JSON) else c for c in self.__children__]

    def copy(self) -> Self:
        return type(self)(c.copy() for c in self.__children__)

    def first(self) -> JSON:
        return self.__children__[0] if self.__children__ else JSONDict({})

    def last(self) -> JSON:
        return self.__children__[-1] if self.__children__ else JSONDict({})

    def current(self) -> Self:
        return self

    def jpath(
        self,
        path: str,
        default: Optional[object] = None,
        vars: dict = {},
        options: jmespath.Options | None = None,
    ):
        res = None
        try:
            path = re.sub(r"\$([^\.]+)", r"var(`\1`)", path)
            res = jmespath.search(f'[*].{path}', self.__children__, options=options)
        except Exception as e:
            self.__logger__.error(f"Error in path {path}: {e}")
        return res if res is not None else default

    def __str__(self) -> str:
        return f"[{', '.join([str(c) for c in self.__children__])}]"
    
    def __len__(self) -> int:
        return len(self.__children__)

    def __iter__(self):
        return iter(self.__children__)

    def __getitem__(self, key: str | int) -> JSON:
        children = super().__getattribute__("__children__")
        if isinstance(key, int):
            return children[key]
        match = COMP_RE.match(key)
        found = []
        if match:
            comp = match.group(2)
            for child in children:
                if isinstance(child, dict):
                    child = JSONDict(child)
                elif not isinstance(child, JSONDict):
                    continue
                term1 = match.group(1).strip()
                term2 = match.group(3).strip()
                is_numeric = False
                if NUMBER_RE.match(term1):
                    term1 = float(term1)
                    is_numeric = True
                elif match := STRING_RE.match(term1):
                    term1 = match.group(1)
                else:
                    term1 = str(child.jpath(term1))
                if NUMBER_RE.match(term2):
                    term2 = float(term2)
                    if not is_numeric and NUMBER_RE.match(term1):
                        term1 = float(term1)
                elif match := STRING_RE.match(term2):
                    term2 = match.group(1)
                else:
                    term2 = str(child.jpath(term2))
                    if is_numeric and NUMBER_RE.match(term2):
                        term2 = float(term2)
                self.__logger__.info(f"Filter: {term1} {comp} {term2}")
                comp_fn = COMPARATORS[comp]
                if comp_fn(term1, term2):
                    found.append(child)
        elif key=='*':
            found=[child for child in children]
        else:
            found=self.jpath(key)
        return JSONList(found)
