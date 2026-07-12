# JSLT

**JSLT** is a JSON templating and transformation engine. It enables developers to declaratively map, filter, and reshape JSON data using pure JSON templates, powered by JMESPath for data extraction and a safe, stack-based execution model.

---

## 📦 Installation

```bash
pip install jslt
```

---

## 🚀 Quick Start

```python
import json
from jslt import JSLT

data = {
    "users": [
        {"name": "Alice", "age": 25, "score": 88.5},
        {"name": "Bob", "age": 17, "score": 92.0}
    ],
    "threshold": 18
}

template = {
    # Extract only adult users
    "adults": {
      "jsl:each": {
        "path": "users",
        "template": {
          "jsl:if": {
            "test": "age >= root().threshold",
            "then": {
              "name": {
                "jsl:path": "name"
              }
            }
          }
        }
      }
    },
    
    # Extract only adult users using jmespath
    "adults_jpath": {
      "jsl:var": {
        "name": "threshold",
        "path": "threshold"
      },
      "jsl:each": {
        "path": "users[?age>var('threshold')]",
        "template": {
          "name": {
            "jsl:path": "name"
          }
        }
      }
    },
    
    # Find names with score > 90
    "top_scorers": {"jsl:path": "users[?score>`90`].name"},
    
    # Calculate average score
    "avg_score": {"jsl:eval": "round(sum(users['*'].score) / count(users), 2)"},
    
    # Calculate average score using jmespath
    "avg_score_jpath": {"jsl:path": "avg(users[*].score)"}
}

jslt = JSLT(template)
result = jslt.transform(data)
print(json.dumps(result, indent=2))
```

**Output:**
```json
{
  "adults": [
    {
      "name": "Alice"
    }
  ],
  "adults_jpath": [
    {
      "name": "Alice"
    }
  ],
  "top_scorers": [
    "Bob"
  ],
  "avg_score": 90.25,
  "avg_score_jpath": 90.25
}
```

---

## 🔑 Core Features

- **JMESPath Integration:** Leverage full JMESPath syntax for powerful data extraction and filtering.
- **Custom DSL Functions:** Transform data using internal functions (`jsl:var`, `jsl:if`, `jsl:each`, `jsl:keep`, `jsl:eval`, `jsl:path`).
- **Stack-Based Iteration:** Uses an iterative stack engine to process templates, completely avoiding Python recursion limits.
- **Safe Expression Evaluation:** Math and logic expressions are evaluated securely via `simple_eval()`, preventing arbitrary code execution.

---

## 📝 Template DSL & Syntax

Templates are standard JSON objects. Each key defines an output field, and its value contains transformation instructions.

### 🔹 `JSL` Functions
All operations are prefixed with `jsl:` (namespace).
Object keys are passed to the function as named parameters. If the value is an array, the values are used as positional parameters.
The engine provides the following functions:
| Function | Description |
|----------|-------------|
| `jsl:var` | Store intermediate values for reuse |
| `jsl:if` | Conditional branching (`[test, then, other]`) |
| `jsl:each` | Iterate over arrays and apply child templates (`[path, template]`) |
| `jsl:keep` | Instructs the engine to keep this object, even if it resolves to None |
| `jsl:eval` | Evaluate arithmetic/logic expressions |
| `jsl:path` | Resolve a JMESPath |

---

## 🧭 JMESPath custom functions

Custom functions are injected into JMESPath to provide additional functionality:

- **Context Helpers:** 
  - `root()` → References the root node
  - `parent()` → Move up the data tree
  - `current()` → Reference the active node
  - `var()` → Gives access to previously defined variables 
- **Math:** 
  - `multiply()` → Multiply all values
- **Text**
  - `strip()` → Remove whitespace from string

---

## 📜 License
This project is licensed under the MIT License. See `LICENSE` for details.
