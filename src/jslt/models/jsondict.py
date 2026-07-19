import jmespath
import logging
import re
from copy import deepcopy
from typing import Optional, Any, Self

from jslt.utils.types import Number
from .json import JSON
from .jsonlist import JSONList

class JSONDict(JSON):
    """Wrapper for JSON objects with attribute access, JMESPath, and DSL support."""
    
    __slots__ = ["__logger__", "__value__", "__json__", "__parent__"]

    def __init__(
        self,
        _json: Optional[dict] = {},
        _value: Any = None,
        _parent: Optional[JSON] = None,
    ):
        super().__setattr__(
            "__logger__", logging.getLogger(self.__class__.__name__)
        )
        super().__setattr__("__value__", _value)
        super().__setattr__("__json__", _json)
        super().__setattr__("__parent__", _parent)
    
    def __getitem__(self, key: str) -> JSON:
        match = _COMP_RE.match(key)
        found = type(self)()
        if match:
            comp = match.group(2)
            term1 = match.group(1).strip()
            term2 = match.group(3).strip()
            is_numeric = False
            if _NUMBER_RE.match(term1):
                term1 = float(term1)
                is_numeric = True
            elif match := _STRING_RE.match(term1):
                term1 = match.group(1)
            else:
                term1 = str(self.jpath(term1))
            if _NUMBER_RE.match(term2):
                term2 = float(term2)
                if not is_numeric and _NUMBER_RE.match(term1):
                    term1 = float(term1)
            elif match := _STRING_RE.match(term2):
                term2 = match.group(1)
            else:
                term2 = str(self.jpath(term2))
                if is_numeric and _NUMBER_RE.match(term2):
                    term2 = float(term2)
            self.__logger__.info(f"Filter: {term1} {comp} {term2})")
            comp_fn = _COMPARATORS[comp]
            if comp_fn(term1, term2):
                found = self
        return found

    def __getattr__(self, name: str):
        if name[:2] == "__":
            return super().__getattribute__(name)
        attr = self.__json__.get(name, {})
        if isinstance(attr, dict):
            return type(self)(_json=attr)
        elif isinstance(attr, list):
            return JSONList(
                [
                    (
                        type(self)(_json=i)
                        if isinstance(i, dict)
                        else (
                            JSONList(
                                [
                                    (
                                        type(self)(_json=e)
                                        if isinstance(e, dict)
                                        else type(self)(_value=e)
                                    )
                                    for e in i
                                ]
                            )
                            if isinstance(i, list)
                            else type(self)(_value=i)
                        )
                    )
                    for i in attr
                ]
            )
        return type(self)(_value=attr)

    def __setattr__(self, attr: str, val: Any):
        if attr[:2] == "__":
            super().__setattr__(attr, val)
        self.__json__[attr] = val

    def __hasattr__(self, attr: str):
        print("hasattr", attr)

    def __len__(self) -> int:
        return len(self.__json__)

    def __iter__(self):
        return iter(self.__json__)

    def __str__(self):
        if self.__value__:
            return str(self.__value__)
        else:
            return str(self.__json__)

    def __int__(self) -> float:
        if self.__value__ is not None:
            return int(self.__value__)
        raise TypeError("Cannot convert JSONDict without a scalar value to float")

    def __float__(self) -> float:
        if self.__value__ is not None:
            return float(self.__value__)
        raise TypeError("Cannot convert JSONDict without a scalar value to float")

    def __add__(self, summand: Number | JSON):
        return self.number() + float(summand)

    def __sub__(self, minuend: Number | JSON):
        return self.number() - float(minuend)

    def __mul__(self, multiplicand: Number | JSON):
        return self.number() * float(multiplicand)

    def __truediv__(self, divisor: Number | JSON):
        return self.number() / float(divisor)

    def to_json(self):
        return self.__value__ or dict(self.__json__.copy())

    def keys(self):
        return self.__json__.keys()

    def items(self):
        return self.__json__.items()

    def values(self):
        return self.__json__.values()

    def get(self, name: str, default: Any={}):
        attr = self.__json__.get(name, default)
        if isinstance(attr, list):
            return JSONList(attr)
        elif isinstance(attr, dict):
            return type(self)(_json=attr)
        return type(self)(_value=attr)

    def copy(self):
        if self.__value__:
            return type(self)(_value=self.__value__)
        return type(self)(_json=deepcopy(self.__json__))

    def current(self):
        return self

    def text(self):
        return str(self)

    def number(self):
        return float(self.__value__)

    def parent(self):
        return self.__parent__

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
            res = jmespath.search(path, self.__json__, options=options)
        except Exception as e:
            self.__logger__.error(f"Error in path {path}: {e}")
        return res if res is not None else default
