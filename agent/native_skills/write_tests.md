---
contract_version: "1.0.0"
name: write_tests
version: "1.0.0"
description: "Generate thorough unit and integration tests for a given module or diff."
---

# Skill: Write Tests

## Description

Produce a suite of automated tests that verify the correctness of new or
changed code. Tests must cover the happy path, edge cases, and expected
failure modes. Prefer real code paths over mocks; use mocks only when the
dependency is a network call, clock, or other non-deterministic resource.

## Inputs

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| target | string | Yes | The module path, function name, or diff to write tests for |
| framework | string | No | Test framework to use (default: `pytest`) |
| context_files | list[str] | No | Source files that provide context (imports, fixtures, etc.) |

## Outputs

| Name | Type | Description |
| ---- | ---- | ----------- |
| test_file | string | Complete, ready-to-run test file |
| coverage_notes | string | Brief description of what is and is not covered |

## Usage

```text
Write a comprehensive pytest test suite for the following module. Include:
1. A test for each public function / method (happy path).
2. Edge-case tests (empty inputs, boundary values, None, etc.).
3. Tests for expected exceptions (use pytest.raises).
4. A brief docstring on each test function explaining what it verifies.

Target module:
{{ target }}
```

---

## Examples

### Input

```text
Write tests for this Python function:

def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

### Expected output

```python
import pytest
from mymodule import divide


def test_divide_basic():
    assert divide(10, 2) == 5.0


def test_divide_negative_numerator():
    assert divide(-6, 3) == -2.0


def test_divide_float_result():
    assert divide(1, 3) == pytest.approx(0.333, rel=1e-3)


def test_divide_by_zero_raises():
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(4, 0)
```

## Limitations

- Generated tests must be reviewed before merging; the agent cannot run them
  to confirm they pass.
- Very complex stateful systems (e.g. database migrations) may require
  hand-written fixtures that the agent cannot fully infer.

## See Also

- [code_review.md](code_review.md) — review the implementation before or after
  generating tests to catch issues early
- [SKILL_TEMPLATE.md](SKILL_TEMPLATE.md) — template for authoring new skills
