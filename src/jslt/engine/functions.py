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
        """
        Extract data from current node using JMESPath

        Args:
            path: JMESPatch to search for
            default: Default value to return if result is empty

        Returns:
            JMESPath result or default value if empty
        """
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
        """
        Declares internal variable

        Args:
            name: The variables name. If omitted, the enclosing objects key will be used
            value: Constant value to assign to variable
            path: JMESPath to extract data from to assign to variable
        """
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
        """
        Declare multiple variables at once

        Args:
            *vars: List of variable definitions (see _jsl_var)
        """
        for var in vars:
            ctx._jsl_var(**var)
        return False

    def _jsl_eval(ctx, expression: str):
        """
        Safely evaluate a Python-like expression using simpleeval.

        Args:
            expression: Expression to evaluate
        """
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
        res = simple_eval(expression, functions=safe_functions, names=safe_names)
        return res

    def _jsl_if(ctx, test: str, then: Any, other: Any = None):
        """
        Test an expression do determine which value/subtemplate to use

        Args:
            test: Expression to test
            then: Value/Subtemplate to use when expression evaluates to True
            otehr: Value/Subtemplate to use otherwise
        """
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
        """
        Apply subtemplate to all list members

        Args:
            path: JMESPath used to identify list to iterate over. If omitted, current context will be used.
            template: Subtemplate to apply to each list item
        """
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
        """
        Internal function used to apply template to each list item

        Args:
            jslt: Templating engine with active template to use
            item: List item
        """
        jslt.context.vars["current"] = item
        return jslt.transform(item)

    def _jsl_keep(ctx, keep: str):
        """
        Tells engine to keep enclosing object even if it evaluates to empty

        Args:
            keep: Defines whether to keep object
        """
        keep = bool(re.match(r"^([Tt][Rr][Uu][Ee]|1)$", keep))
        ctx.parent.keep = keep
        return False


"""
Custom functions for JMESPath
"""


class JMESPathFunctions(jmespath.functions.Functions):
    __slots__ = ["_logger", "_vars"]

    def __init__(self, vars={}):
        self._logger = logging.getLogger(__class__.__qualname__)
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
