import logging
import math
import re
from functools import reduce
from typing import Any, Optional

import jmespath
from simpleeval import simple_eval

from jslt.models import JSON, JSONDict, JSONList
from jslt.utils.constants import COMP_RE, COMPARATORS, JSL_FUNC_RE, NUMBER_RE, STRING_RE
from jslt.utils.tools import get_methods

"""
Metaclass for registering new DSL functions
"""


class FunctionRegistry(type):
    def __init__(cls, name, bases, attrs):
        cls._register_functions()

    def _register_functions(cls):
        for fnc_signature, fnc in get_methods(cls):
            if not (match := JSL_FUNC_RE.match(fnc_signature)):
                continue
            fnc_namespace, fnc_name = match.groups()
            cls.FUNCTION_LUT[f"{fnc_namespace}_{fnc_name}"] = fnc


"""
Base class for registering new DSL functions
"""


class Functions(metaclass=FunctionRegistry):
    FUNCTION_LUT = {}


"""
DSL functions available to use inside templates
- jsl:var to define an assign variables
- jsl:vars to assign multiple variables at once
- jsl:if to control templates behaviour based on value tests
- jsl:each to apply subtemplates to each item of an array
- jsl:keep to instruct the engine to keep an element even if it's empty
- jsl:eval evaluate an expression
- jsl:path extract data based on JMESPath
"""


class JSLFunctions(Functions):
    def _jsl_path(ctx, path: str, default: Any = None) -> Any:
        ctx._logger.info(f"Path: {path} (default: {default})")
        options = jmespath.Options(custom_functions=JMESPathFunctions(vars=ctx.vars))
        res = ctx.current.jpath(path, default, options=options)
        if not res:
            return default
        return (
            JSONList(res)
            if isinstance(res, list)
            else JSONDict(_json=res) if isinstance(res, dict) else JSONDict(_value=res)
        )

    def _jsl_var(
        ctx,
        name: Optional[str] = None,
        value: Optional[type] = None,
        path: Optional[str] = None,
    ):
        var_name = name or (ctx.context.parent and ctx.context.parent.cur_key)
        if not var_name:
            ctx._logger.error("Variable name is not set")
            return
        if path:
            res = ctx._jsl_path(path)
            if res is not None:
                value = res.to_json()
        ctx._logger.info(f"Variable: {var_name} = {value}")
        ctx.vars[var_name] = value
        return False

    def _jsl_vars(ctx, *vars):
        for var in vars:
            ctx._jsl_var(**var)
        return False

    def _jsl_eval(ctx, path: str):
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
            "copy": ctx.current.copy,
            "text": ctx.current.text,
            "number": ctx.current.number,
            "current": ctx.current.current,
            "count": len,
            "sum": sum,
        }
        safe_names = {
            **{k: ctx.current.get(k) for k in ctx.current.keys()},
            **{f"__vars__{k}": v for k, v in ctx.vars.items()},
        }
        res = simple_eval(path, functions=safe_functions, names=safe_names)
        return res

    def _jsl_if(ctx, test: str, then: Any, other: Any = None):
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
                term1 = str(ctx._jsl_path(term1))
            if NUMBER_RE.match(term2):
                term2 = float(term2)
                if not is_numeric and NUMBER_RE.match(term1):
                    term1 = float(term1)
            elif match := STRING_RE.match(term2):
                term2 = match.group(1)
            else:
                term2 = str(ctx._jsl_path(term2))
                if is_numeric and NUMBER_RE.match(term2):
                    term2 = float(term2)
            ctx._logger.info(f"Filter: {term1} {comp} {term2})")
            comp_fn = COMPARATORS[comp]
            if comp_fn(term1, term2):
                return then
        return other

    def _jsl_each(ctx, path: Optional[str] = None, template: dict | list = {}):
        context = ctx._jsl_path(path) if path else ctx.current
        jslt = ctx.engine_class(template, defaults=ctx.defaults)
        jslt.context.vars["root"] = ctx.vars.get("root")
        jslt.context.vars["parent"] = ctx.current.to_json()
        for var_name, var_value in ctx.vars.items():
            if var_name in ("root", "parent"):
                continue
            jslt.context.vars[var_name] = var_value
        if context is None:
            return None
        elif not isinstance(context, JSONList):
            return jslt.transform(context)

        return [item for child in context if (item := ctx._jsl_each_item(jslt, child))]

    def _jsl_each_item(ctx, jslt: Any, item: list | dict | JSON):
        jslt.context.vars["current"] = item
        return jslt.transform(item)

    def _jsl_keep(ctx, keep: str):
        keep = bool(re.match(r"^([Tt][Rr][Uu][Ee]|1)$", keep))
        ctx.parent.keep = keep
        return False


"""
Custom functions for JMESPath
"""


class JMESPathFunctions(jmespath.functions.Functions):
    __slots__ = ["_logger", "_vars"]

    def __init__(self, vars={}):
        self._logger = logging.getLogger(__name__)
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
