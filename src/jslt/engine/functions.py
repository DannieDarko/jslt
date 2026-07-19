import jmespath
import logging
from functools import reduce

class JSLTFunctions(jmespath.functions.Functions):
    __slots__ = ['_logger', '_vars']
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
        self._logger.info(f"VAR {name} => {self._vars.get(name, {})}")
        return self._vars.get(name, {})

    @jmespath.functions.signature({"types": ["array-number"]})
    def _func_multiply(self, numbers: list):
        return reduce(lambda result, mult: mult * result, numbers, 1)

    @jmespath.functions.signature({"types": ["string"]})
    def _func_strip(self, strval: str):
        return strval.strip()
