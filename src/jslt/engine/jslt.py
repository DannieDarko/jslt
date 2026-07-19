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
from collections import deque
from copy import deepcopy
from simpleeval import simple_eval
from typing import Optional, Self

from jslt.engine.functions import JSLTFunctions
from jslt.models import JSON, JSONDict, JSONList
from jslt.utils.constants import COMPARATORS, COMP_RE, NUMBER_RE, STRING_RE, JSLT_FUNC_RE

class JSLT:
    __slots__ = ['_logger', 'jslt', 'defaults', 'vars', 'context', 'parentContext']
    
    def __init__(self, jslt: list | dict, defaults: dict = {}):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.jslt = deepcopy(jslt)
        self.defaults = defaults.copy()
        self.vars = {}
        self.context = None
        self.parentContext = None

    def _jsl_var(
        self,
        name: Optional[str] = None,
        value: Optional[type] = None,
        path: Optional[str] = None,
    ):
        var_name = name or (self.parentContext and self.parentContext.cur_key)
        if not var_name:
            self._logger.error("Variable name is not set")
            return
        if path:
            res = self._jsl_path(path)
            if res is not None:
                value = res.to_json()
        self._logger.info(f"Variable: {var_name} = {value}")
        self.vars[var_name] = value
        return False

    def _jsl_vars(self, *vars):
        for var in vars:
            self._jsl_var(**var)
        return False

    def _jsl_eval(self, path: str):
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

    def _jsl_path(self, path: str, default: Any=None) -> Any:
        self._logger.info(f"Path: {path} (default: {default})")
        options = jmespath.Options(custom_functions=JSLTFunctions(vars=self.vars))
        res = self.context.jpath(path, default, options=options)
        if not res:
            return default
        return (
            JSONList(res)
            if isinstance(res, list)
            else JSONDict(_json=res) if isinstance(res, dict) else JSONDict(_value=res)
        )

    def _jsl_if(self, test: str, then: Any, other: Any=None):
        match = COMP_RE.match(test)
        if match:
            comp = match.group(2)
            term1 = match.group(1).strip()
            term2 = match.group(3).strip()
            is_numeric = False
            if NUMBER_RE.match(term1):
                term1 = float(term1)
                is_numeric = True
            elif match := STRING_RE.match(term1):
                term1 = match.group(1)
            else:
                term1 = str(self._jsl_path(term1))
            if NUMBER_RE.match(term2):
                term2 = float(term2)
                if not is_numeric and NUMBER_RE.match(term1):
                    term1 = float(term1)
            elif match := STRING_RE.match(term2):
                term2 = match.group(1)
            else:
                if term2[:4] == 'root':
                    print('ROOT', self.vars['root'])
                term2 = str(self._jsl_path(term2))
                if is_numeric and NUMBER_RE.match(term2):
                    term2 = float(term2)
            self._logger.info(f"Filter: {term1} {comp} {term2})")
            comp_fn = COMPARATORS[comp]
            if comp_fn(term1, term2):
                return then
        return other

    def _jsl_each(self, path:Optional[str]=None, template: dict | list={}):
        context = self._jsl_path(path) if path else self.context
        jslt = JSLT(template, defaults=self.defaults)
        jslt.vars["root"] = self.vars.get('root')
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
    
    def _jsl_each_item(self, jslt: JSLT, item: list | dict | JSON):
        jslt.vars["current"] = item
        return jslt.transform(item)
        
    def _jsl_keep(self, keep: str):
        keep = bool(re.match(r"^([Tt][Rr][Uu][Ee]|1)$", keep))
        self.parentContext.keep = keep
        return False

    def transform(self, json: dict | list | JSON, root: Optional[list | dict] = None):
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
        if root:
            self.vars['root'] = root
        elif not self.vars.get('root'):
            self.vars['root'] = json
            
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
            if isinstance(cur_key, str) and (fn_match := JSLT_FUNC_RE.match(cur_key)):
                fn_namespace, fn_name = fn_match.groups()
                jsl_function_name = f'_{fn_namespace}_{fn_name}'
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
                    self._logger.error(f"No such function: {jsl_function_name}")
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
