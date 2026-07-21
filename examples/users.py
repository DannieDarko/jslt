import json
import logging

from jslt import JSLT

logging.basicConfig(level=logging.DEBUG)

data = {
    "users": [
        {"name": "Alice", "age": 25, "score": 88.5},
        {"name": "Bob", "age": 17, "score": 92.0},
    ],
    "threshold": 18,
}

template = {
    # Extract only adult users
    "adults": {
        "jsl:each": {
            "path": "users",
            "template": {
                "jsl:if": {
                    "test": "age >= root().threshold",
                    "then": {"name": {"jsl:path": "name"}},
                }
            },
        }
    },
    # Extract only adult users using jmespath
    "adults_jpath": {
        "jsl:var": {"name": "threshold", "path": "threshold"},
        "jsl:each": {
            "path": "users[?age>var('threshold')]",
            "template": {"name": {"jsl:path": "name"}},
        },
    },
    # Extract only adult users using jmespath
    "adults_jpath_2": {
        "jsl:each": {
            "path": "users[?age>root().threshold]",
            "template": {"name": {"jsl:path": "name"}},
        }
    },
    # Find names with score > 90
    "top_scorers": {"jsl:path": "users[?score>`90`].name"},
    # Calculate average score
    "avg_score": {"jsl:eval": "round(sum(users['*'].score) / count(users), 2)"},
    # Calculate average score using jmespath
    "avg_score_jpath": {"jsl:path": "avg(users[*].score)"},
}

jslt_engine = JSLT(template)
result = jslt_engine.transform(data)
print(json.dumps(result, indent=2))
