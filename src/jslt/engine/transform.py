# ruff: noqa: E712
import logging
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Self, Type

from jslt.engine.functions import Functions
from jslt.models import JSON, JSONDict, JSONList
from jslt.utils.constants import JSL_FUNC_RE, JSLT_FUNC_RE

"""
JSLT Engine: A secure, high-performance JSON templating and transformation engine.

Supports:
- JMESPath-based data extraction
- Custom DSL function support
- Stack-based iterative transformation (avoids recursion limits)
- Safe expression evaluation (using simple_eval())
"""


class JSLT:
    @dataclass(slots=True)
    class Context:
        engine_class: Type
        defaults: Dict[str, Any]
        functions: Dict[str, Functions] = field(default_factory=dict)
        current: Any = None
        parent: Any = None
        vars: Dict[str, Any] = field(default_factory=dict)
        _logger: logging.Logger = field(
            default_factory=lambda: logging.getLogger(__class__.__qualname__)
        )

        def __getattr__(self, name):
            if fn_match := JSL_FUNC_RE.match(name):
                fn_namespace, fn_name = fn_match.groups()
                fn = self.functions.get(f"{fn_namespace}_{fn_name}")
                context = self

                def fn_wrapper(*args, **kwargs):
                    nonlocal context
                    return fn(context, *args, **kwargs)

                return fn_wrapper
            return None

    __slots__ = ["_logger", "jslt", "context"]

    def __init__(self, jslt: list | dict, defaults: dict = {}):
        self._logger = logging.getLogger(self.__class__.__qualname__)
        self.jslt = deepcopy(jslt)
        self.context = JSLT.Context(
            engine_class=self.__class__,
            defaults=defaults.copy(),
            functions=Functions.FUNCTION_LUT,
        )

    def transform(
        self, json_data: dict | list | JSON, root: Optional[list | dict] = None
    ):
        """Iteratively transform JSON data according to the template."""

        class StackItem:
            """Internal stack frame for iterative transformation."""

            __slots__ = ["cur_itm", "cur_obj", "cur_key", "parent", "keep"]

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

        self.context.current = (
            JSONList(json_data)
            if isinstance(json_data, list)
            else JSONDict(json_data) if not isinstance(json_data, JSON) else json_data
        )
        if root:
            self.context.vars["root"] = root
        elif not self.context.vars.get("root"):
            self.context.vars["root"] = json_data

        self.context.parent = None
        copy_obj = {"root": type(self.jslt)()}
        cur_itm = None
        stack_item = None
        copy_stack = deque([StackItem(self.jslt, copy_obj, "root")])
        while copy_stack:
            stack_item = copy_stack.popleft()
            parent = stack_item.parent
            self.context.parent = parent
            cur_itm = stack_item.cur_itm
            cur_obj = stack_item.cur_obj
            cur_key = stack_item.cur_key
            if isinstance(cur_key, str) and (fn_match := JSLT_FUNC_RE.match(cur_key)):
                fn_namespace, fn_name = fn_match.groups()
                jsl_function_name = f"{fn_namespace}_{fn_name}"
                jsl_function = None
                if jsl_function_name in self.context.functions:
                    jsl_function = self.context.functions[jsl_function_name]
                if jsl_function and callable(jsl_function):
                    if isinstance(cur_itm, dict):
                        res = jsl_function(self.context, **cur_itm)
                    else:
                        if not isinstance(cur_itm, list):
                            cur_itm = [cur_itm]
                        res = jsl_function(self.context, *cur_itm)
                    if isinstance(res, JSON):
                        res = res.to_json()
                    if res is None:
                        if parent.keep:
                            copy_stack.append(
                                StackItem(
                                    self.context.defaults.get("default"),
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
                                keep=self.context.defaults.get("keep", False),
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
                        keep=self.context.defaults.get("keep", False),
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
                            keep=self.context.defaults.get("keep", False),
                        )
                    )
            else:
                cur_obj[cur_key] = cur_itm
        return copy_obj["root"] if "root" in copy_obj else None
