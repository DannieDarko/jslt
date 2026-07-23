import json
import logging
from jslt.engine.functions import Functions
from jslt.engine.transform import JSLT


class CustomFunctions(Functions):
    def _custom_decorate_string(ctx: JSLT.Context, value: str):
        return f"### {value} ###"


def run_tranform():
    tmpl = {
        "root": {
            "my_value": "some value",
            "custom_value": {"custom:decorate_string": "custom value"},
        }
    }

    jslt_engine = JSLT(tmpl)
    return jslt_engine.transform({})


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(json.dumps(run_tranform(), indent=4))
