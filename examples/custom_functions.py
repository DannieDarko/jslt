import logging
from jslt.engine.functions import Functions
from jslt.engine.transform import JSLT


class CustomFunctions(Functions):
    def _custom_decorate_string(ctx: JSLT.Context, value: str):
        return f"### {value} ###"


def run_tranform():
    tmpl = {
        "root": {
            "my_value": "some",
            "custom_value": {"custom:decorate_string": "static value"},
        }
    }

    jslt_engine = JSLT(tmpl)
    print(jslt_engine.transform({}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    run_tranform()
