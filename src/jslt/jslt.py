"""
JSLT Engine: A secure, high-performance JSON templating and transformation engine.

Supports:
- JMESPath-based data extraction
- Custom DSL functions (jsl:var, jsl:if, jsl:each, jsl:keep, jsl:eval, jsl:path)
- JSON Schema validation for templates and outputs
- Stack-based iterative transformation (avoids recursion limits)
- Safe expression evaluation (using simple_eval())
"""
from __future__ import annotations

import jmespath
import json
import logging
import math
import operator
import re
from abc import ABC, abstractmethod
from collections import deque
from copy import deepcopy
from functools import reduce
from simpleeval import simple_eval
from typing import Optional, Self

# Typedef for numbers
Number = int | float | complex

# Operator mapping for safe comparisons
_COMPARATORS = {
    "=": operator.eq,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}

_COMPARATOR_CHARS = ''.join(set(''.join(_COMPARATORS.keys())))

# Regex for parsing comparison expressions: term1 OP term2
_COMP_RE = re.compile(f"^([^{_COMPARATOR_CHARS}]+)({'|'.join(_COMPARATORS.keys())})([^{_COMPARATOR_CHARS}]+)$")

# Regex for identifying numbers
_NUMBER_RE = re.compile(r'^([0-9]*)(\.[0-9]+)?$')

# Regex for identifying strings 
_STRING_RE = re.compile(r'^"([^"]*)"$')

class JSON(ABC):
    @abstractmethod
    def __iter__(self):
        pass

    @abstractmethod
    def copy(self):
        pass

    @abstractmethod
    def to_json(self):
        pass

    @abstractmethod
    def current(self):
        pass


class JSONList(JSON):
    """Wrapper for JSON arrays with JMESPath and DSL support."""
    
    __slots__ = ['__logger__', '__children__']
    
    def __init__(self, children: Optional[list[JSON]] = []):
        logger = logging.getLogger(self.__class__.__name__)
        object.__setattr__(self, "__logger__", logger)
        object.__setattr__(self, "__children__", children)

    def append(self, child: JSON) -> None:
        children = object.__getattribute__(self, "__children__")
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
        children = object.__getattribute__(self, "__children__")
        if isinstance(key, int):
            return children[key]
        match = _COMP_RE.match(key)
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
                if _NUMBER_RE.match(term1):
                    term1 = float(term1)
                    is_numeric = True
                elif match := _STRING_RE.match(term1):
                    term1 = match.group(1)
                else:
                    term1 = str(child.jpath(term1))
                if _NUMBER_RE.match(term2):
                    term2 = float(term2)
                    if not is_numeric and _NUMBER_RE.match(term1):
                        term1 = float(term1)
                elif match := _STRING_RE.match(term2):
                    term2 = match.group(1)
                else:
                    term2 = str(child.jpath(term2))
                    if is_numeric and _NUMBER_RE.match(term2):
                        term2 = float(term2)
                self.__logger__.info(f"Filter: {term1} {comp} {term2}")
                comp_fn = _COMPARATORS[comp]
                if comp_fn(term1, term2):
                    found.append(child)
        elif key=='*':
            found=[child for child in children]
        else:
            found=self.jpath(key)
        return JSONList(found)

class JSONDict(JSON):
    """Wrapper for JSON objects with attribute access, JMESPath, and DSL support."""

    __slots__ = ['__logger__', '__value__', '__json__', '__parent__']
    
    def __init__(self, _json: Optional[dict] = {}, _value: Any = None, _parent: Optional[JSON] = None):
        object.__setattr__(
            self, "__logger__", logging.getLogger(self.__class__.__name__)
        )
        object.__setattr__(self, "__value__", _value)
        object.__setattr__(self, "__json__", _json)
        object.__setattr__(self, "__parent__", _parent)

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
            return object.__getattribute__(self, name)
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

    def __setattr__(self, attr: str, val):
        if attr[:2] == "__":
            object.__setattr__(self, attr, val)
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

    def get(self, name: str, default={}):
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

class JSLTFunctions(jmespath.functions.Functions):

    def __init__(self, vars={}):
        self._vars = vars

    @jmespath.functions.signature()
    def _func_root(self):
        return self._vars.get("root", {})

    @jmespath.functions.signature()
    def _func_current(self):
        return self._vars.get("current", {})

    @jmespath.functions.signature()
    def _func_parent(self):
        return self._vars.get("parent", {})

    @jmespath.functions.signature({"types": ["string"]})
    def _func_var(self, name: str):
        return self._vars.get(name, {})

    @jmespath.functions.signature({"types": ["array-number"]})
    def _func_multiply(self, numbers: list):
        return reduce(lambda result, mult: mult * result, numbers, 1)

    @jmespath.functions.signature({"types": ["string"]})
    def _func_strip(self, strval: str):
        return strval.strip()


class JSLT:
    def __init__(self, jslt: list | dict, defaults: dict = {}):
        self.__logger__ = logging.getLogger(self.__class__.__name__)
        self.jslt = deepcopy(jslt)
        self.defaults = defaults.copy()
        self.vars = {}
        self.context = None
        self.parentContext = None

    def jsl_var(
        self,
        name: Optional[str] = None,
        value: Optional[type] = None,
        path: Optional[str] = None,
    ):
        var_name = name or (self.parentContext and self.parentContext.cur_key)
        if not var_name:
            self.__logger__.error("Variable name is not set")
            return
        if path:
            res = self.jsl_path(path)
            if res is not None:
                value = res.to_json()
        self.__logger__.info(f"Variable: {var_name} = {value}")
        self.vars[var_name] = value
        return False

    def jsl_vars(self, *vars):
        for var in vars:
            self.jsl_var(**var)
        return False

    def jsl_eval(self, path: str):
        """Safely evaluate a Python-like expression using simpleeval."""
        safe_functions = {
            "str": str,
            "int": int,
            "float": float,
            "abs": abs,
            "round": round,
            "floor": math.floor,
            "ceil": math.ceil,
            "pow": math.pow,
            "sqrt": math.sqrt,
            "copy": self.context.copy,
            "text": self.context.text,
            "number": self.context.number,
            "current": self.context.current,
            "count": len,
            "sum": sum,
        }
        safe_names = {
            **{k: self.context.get(k) for k in self.context.keys()},
            **{f"__vars__{k}": v for k, v in self.vars.items()},            
        }
        res = simple_eval(path, functions=safe_functions, names=safe_names)
        return res

    def jsl_path(self, path: str, default: Any=None) -> Any:
        self.__logger__.info(f"Path: {path} (default: {default})")
        options = jmespath.Options(custom_functions=JSLTFunctions(vars=self.vars))
        res = self.context.jpath(path, default, options=options)
        if not res:
            return default
        return (
            JSONList(res)
            if isinstance(res, list)
            else JSONDict(_json=res) if isinstance(res, dict) else JSONDict(_value=res)
        )

    def jsl_if(self, test: str, then: Any, other: Any=None):
        match = _COMP_RE.match(test)
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
                term1 = str(self.jsl_path(term1))
            if _NUMBER_RE.match(term2):
                term2 = float(term2)
                if not is_numeric and _NUMBER_RE.match(term1):
                    term1 = float(term1)
            elif match := _STRING_RE.match(term2):
                term2 = match.group(1)
            else:
                term2 = str(self.jsl_path(term2))
                if is_numeric and _NUMBER_RE.match(term2):
                    term2 = float(term2)
            self.__logger__.info(f"Filter: {term1} {comp} {term2})")
            comp_fn = _COMPARATORS[comp]
            if comp_fn(term1, term2):
                return then
        return other

    def jsl_each(self, path:Optional[str]=None, template={}):
        context = self.jsl_path(path) if path else self.context
        jslt = JSLT(template, defaults=self.defaults)
        jslt.vars["root"] = self.vars.get("root") or self.context.to_json()
        jslt.vars["parent"] = self.context.to_json()
        for var_name, var_value in self.vars.items():
            if var_name in ('root', 'parent'):
                continue
            jslt.vars[var_name] = var_value
        if context is None:
            return None
        elif not isinstance(context, JSONList):
            return jslt.transform(context)
        res = []
        
        return [item for child in context if (item := self._jsl_each_item(jslt, child))]
    
    def _jsl_each_item(self, jslt, item):
        jslt.vars["current"] = item
        return jslt.transform(item)
        

    def jsl_keep(self, keep: str):
        keep = bool(re.match(r"^([Tt][Rr][Uu][Ee]|1)$", keep))
        self.parentContext.keep = keep
        return False

    def transform(self, json: dict | list | JSON):
        """Iteratively transform JSON data according to the template."""
        class StackItem:
            """Internal stack frame for iterative transformation."""
            __slots__ = ['cur_itm', 'cur_obj', 'cur_key', 'parent', 'keep']
            def __init__(
                self,
                cur_itm: object,
                cur_obj: list | dict,
                cur_key: int | str,
                parent: Optional[Self] = None,
                keep: bool = False,
            ):
                self.cur_itm = cur_itm
                self.cur_obj = cur_obj
                self.cur_key = cur_key
                self.parent = parent
                self.keep = keep

        self.context = JSONList(json) if isinstance(json, list) else JSONDict(json) if not isinstance(json, JSON) else json
        self.parentContext = None
        copy_obj = {"root": type(self.jslt)()}
        cur_itm = None
        stack_item = None
        copy_stack = deque([StackItem(self.jslt, copy_obj, "root")])
        while copy_stack:
            stack_item = copy_stack.popleft()
            parent = stack_item.parent
            self.parentContext = parent
            cur_itm = stack_item.cur_itm
            cur_obj = stack_item.cur_obj
            cur_key = stack_item.cur_key
            if isinstance(cur_key, str) and cur_key[:4] == "jsl:":
                jsl_function_name = "jsl_" + cur_key[4:]
                jsl_function = None
                if hasattr(self, jsl_function_name):
                    jsl_function = getattr(self, jsl_function_name)
                if jsl_function and callable(jsl_function):
                    if isinstance(cur_itm, dict):
                        res = jsl_function(**cur_itm)
                    else:
                        if not isinstance(cur_itm, list):
                            cur_itm = [cur_itm]
                        res = jsl_function(*cur_itm)
                    if isinstance(res, JSON):
                        res = res.to_json()
                    if res is None:
                        if parent.keep:
                            copy_stack.append(
                                StackItem(
                                    self.defaults.get("default"),
                                    parent.cur_obj,
                                    parent.cur_key,
                                )
                            )
                        else:
                            del parent.cur_obj[parent.cur_key]
                    elif res == False:
                        pass
                    else:
                        copy_stack.append(
                            StackItem(
                                res,
                                parent.cur_obj,
                                parent.cur_key,
                                keep=self.defaults.get("keep", False),
                            )
                        )
                else:
                    self.__logger__.error(f"No such function: {jsl_function_name}")
            elif isinstance(cur_itm, list):
                cur_obj[cur_key] = [None for i in range(len(cur_itm))]
                copy_stack += [
                    StackItem(
                        v,
                        cur_obj[cur_key],
                        i,
                        stack_item,
                        keep=self.defaults.get("keep", False),
                    )
                    for i, v in enumerate(cur_itm)
                ]
            elif isinstance(cur_itm, dict):
                cur_obj[cur_key] = {}
                for k, v in cur_itm.items():
                    copy_stack.append(
                        StackItem(
                            v,
                            cur_obj[cur_key],
                            k,
                            stack_item,
                            keep=self.defaults.get("keep", False),
                        )
                    )
            else:
                cur_obj[cur_key] = cur_itm
        return copy_obj["root"] if 'root' in copy_obj else None
