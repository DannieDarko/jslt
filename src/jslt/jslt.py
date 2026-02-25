import jmespath
import json
import logging
import re
from abc import ABC, abstractmethod
from functools import reduce
from typing import Self, Union
from copy import deepcopy


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
    def __init__(self, children: list[JSON] = []):
        logger = logging.getLogger(self.__class__.__name__)
        object.__setattr__(self, "__logger__", logger)
        object.__setattr__(self, "__children__", children)

    def append(self, child: JSON):
        children = object.__getattribute__(self, "__children__")
        children.append(child)

    def to_json(self):
        return [c.to_json() if isinstance(c, JSON) else c for c in self.__children__]

    def copy(self):
        return type(self)(c.copy() for c in self.__children__)

    def first(self):
        return self.__children__[0] if self.__children__ else JSONDict({})

    def last(self):
        return self.__children__[-1] if self.__children__ else JSONDict({})

    def current(self):
        return self

    def __str__(self):
        return f"[{', '.join([str(c) for c in self.__children__])}]"

    def __iter__(self):
        return iter(self.__children__)

    def __getitem__(self, key: str):
        children = object.__getattribute__(self, "__children__")
        if isinstance(key, int):
            return children[key]
        match = re.match(r"^([^<>=!]+)(={1,2}|!=|<|>|<=|>=)([^<>=!]+)$", key)
        found = []
        if match:
            comp = "==" if match.group(2) == "=" else match.group(2)
            for child in children:
                if isinstance(child, dict):
                    child = JSONDict(child)
                if not isinstance(child, JSONDict):
                    continue
                term1 = str(child.jpath(match.group(1)))
                term2 = str(child.jpath(match.group(3)))
                if not re.match(r"^[0-9]*(\.[0-9]+)?$", term1):
                    term1 = f"'{term1}'"
                if not re.match(r"^[0-9]*(\.[0-9]+)?$", term2):
                    term2 = f"'{term2}'"
                self.__logger__.info(f"Filter: {term1} {comp} {term2}")
                if eval(f"{term1}{comp}{term2}"):
                    found.append(child)
        return JSONList(found)


class JSONDict(JSON):
    def __init__(self, _json: dict = {}, _value=None, _parent=None):
        object.__setattr__(
            self, "__logger__", logging.getLogger(self.__class__.__name__)
        )
        object.__setattr__(self, "__value__", _value)
        object.__setattr__(self, "__json__", _json)
        object.__setattr__(self, "__parent__", _parent)

    def __getitem__(self, key: str):
        match = re.match(r"^([^<>=!]+)(={1,2}|!=|<|>|<=|>=)([^<>=!]+)$", key)
        found = type(self)()
        if match:
            comp = "==" if match.group(2) == "=" else match.group(2)
            term1 = str(self.jpath(match.group(1)))
            term2 = str(self.jpath(match.group(3)))
            if not re.match(r"^[0-9]*(\.[0-9]+)?$", term1):
                term1 = f"'{term1}'"
            if not re.match(r"^[0-9]*(\.[0-9]+)?$", term2):
                term2 = f"'{term2}'"
            self.__logger__.info(f"Filter: {term1} {comp} {term2})")
            if eval(f"{term1}{comp}{term2}"):
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

    def __iter__(self):
        return iter(self.__json__)

    def __str__(self):
        if self.__value__:
            return str(self.__value__)
        else:
            return str(self.__json__)

    def __float__(self):
        return 0.1

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
        default: Union[None, object] = None,
        vars: dict = {},
        options: jmespath.Options | None = None,
    ):
        res = None
        try:
            path = re.sub(r"\$([^\.]+)", r"var(`\1`)", path)
            res = jmespath.search(path, self.__json__, options=options)
        except Exception as e:
            self.__logger__.error(f"Error in path {path}: {e}")
            pass
        return res if res is not None else default


class JSLTFunctions(jmespath.functions.Functions):

    def __init__(self, vars={}):
        self._vars = vars

    @jmespath.functions.signature()
    def _func_root(self):
        return self._vars.get("root", {})

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
        name: str | None = None,
        value: type | None = None,
        path: str | None = None,
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

    def jsl_eval(self, path):
        res = eval(
            path,
            {
                "__builtins__": {
                    "str": str,
                    "int": int,
                    "float": float,
                    "abs": abs,
                    "round": round,
                    "copy": self.copy,
                    "text": self.text,
                    "number": self.number,
                    "current": self.current,
                }
            },
            {
                **{k: self.get(k) for k in self.keys()},
                **{f"__vars__{k}": v for k, v in vars.items()},
            },
        )
        return res

    def jsl_path(self, path, default=None):
        self.__logger__.info(f"Path: {path} ({default})")
        options = jmespath.Options(custom_functions=JSLTFunctions(vars=self.vars))
        res = self.context.jpath(path, default, options=options)
        if not res:
            return default
        return (
            JSONList(res)
            if isinstance(res, list)
            else JSONDict(_json=res) if isinstance(res, dict) else JSONDict(_value=res)
        )

    def jsl_if(self, test, then, other):
        match = re.match(r"^([^<>=!]+)(={1,2}|!=|<|>|<=|>=)([^<>=!]+)$", test)
        if match:
            comp = "==" if match.group(2) == "=" else match.group(2)
            term1 = match.group(1)
            if term1[:5] == "path:":
                term1 = str(self.jsl_path(term1[5:]))
            term2 = match.group(3)
            if term2[:5] == "path:":
                term2 = str(self.jsl_path(term2[5:]))
            if not re.match(r"^[0-9]*(\.[0-9]+)?$", term1):
                term1 = f"'{term1}'"
            if not re.match(r"^[0-9]*(\.[0-9]+)?$", term2):
                term2 = f"'{term2}'"
            self.__logger__.info((term1, comp, term2))
            if eval(f"{term1}{comp}{term2}"):
                return then
        return other

    def jsl_each(self, path=[], template={}):
        context = self.jsl_path(path)
        jslt = JSLT(template, defaults=self.defaults)
        jslt.vars["root"] = self.vars.get("root") or self.context.to_json()
        for var_name, var_value in self.vars.items():
            if var_name == "root":
                continue
            jslt.vars[var_name] = var_value
        if context is None:
            return None
        elif not isinstance(context, JSONList):
            return jslt.transform(context)
        res = []
        for item in context:
            jslt.vars["current"] = item
            res.append(jslt.transform(item))
        return res

    def jsl_keep(self, keep: str):
        keep = bool(re.match(r"^([Tt][Rr][Uu][Ee]|1)$", keep))
        self.parentContext.keep = keep
        return False

    def transform(self, json):
        class StackItem:
            def __init__(
                self,
                cur_itm: object,
                cur_obj: list | dict,
                cur_key: int | str,
                parent: Self | None = None,
                keep: bool = False,
            ):
                self.cur_itm = cur_itm
                self.cur_obj = cur_obj
                self.cur_key = cur_key
                self.parent = parent
                self.keep = keep

        self.context = JSONDict(json) if not isinstance(json, JSON) else json
        self.parentContext = None
        copy_obj = {"root": type(self.jslt)()}
        cur_itm = None
        stack_item = None
        copy_stack = [StackItem(self.jslt, copy_obj, "root")]
        while copy_stack:
            stack_item = copy_stack.pop(0)
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
        return copy_obj["root"]
