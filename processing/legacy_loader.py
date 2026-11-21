from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LegacyModuleLoadError(RuntimeError):
    """Raised when a reusable legacy definition cannot be loaded."""


def _is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(
            node.value,
            ast.Constant,
        )
        and isinstance(
            node.value.value,
            str,
        )
    )


def _assignment_names(
    node: ast.AST,
) -> set[str]:
    names = set()

    targets = []

    if isinstance(
        node,
        (
            ast.Assign,
            ast.AnnAssign,
        ),
    ):
        if isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = [node.target]

    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)

    return names


def _is_safe_constant_expression(
    node: ast.AST,
) -> bool:
    """
    Return True for configuration expressions that are safe
    to execute while loading reusable legacy definitions.

    Supported examples:
        MONEY_TOLERANCE = 0.01
        MONEY_TOLERANCE = Decimal("0.01")
        KNOWN_TYPES = {"ZHV", "BCD", "CCD", "ZPT"}
        MAX_VALUE = BASE_VALUE * 2

    Runtime expressions involving Streamlit, DataFrames,
    models, file access, or function execution are rejected.
    """
    safe_node_types = (
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.Set,
        ast.Dict,
        ast.UnaryOp,
        ast.BinOp,
        ast.BoolOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.And,
        ast.Or,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Call,
        ast.keyword,
    )

    for child in ast.walk(node):
        if not isinstance(
            child,
            safe_node_types,
        ):
            return False

        if isinstance(child, ast.Name):
            name = child.id

            if (
                name not in {
                    "True",
                    "False",
                    "None",
                    "Decimal",
                }
                and not name.isupper()
            ):
                return False

        if isinstance(child, ast.Call):
            if not (
                isinstance(
                    child.func,
                    ast.Name,
                )
                and child.func.id
                in {
                    "Decimal",
                    "tuple",
                    "list",
                    "set",
                    "dict",
                }
            ):
                return False

    return True


def load_definitions(
    relative_path: str,
    module_name: str,
    required_names: Iterable[str],
) -> ModuleType:
    """
    Load imports, constants, classes, and functions from a
    page module without executing its top-level Streamlit UI.
    """
    source_path = (
        PROJECT_ROOT
        / relative_path
    )

    if not source_path.exists():
        raise LegacyModuleLoadError(
            f"Legacy module was not found: {source_path}"
        )

    source = source_path.read_text(
        encoding="utf-8-sig"
    )

    try:
        tree = ast.parse(
            source,
            filename=str(source_path),
        )

    except SyntaxError as error:
        raise LegacyModuleLoadError(
            f"Legacy module contains invalid Python: {error}"
        ) from error

    retained_nodes = []

    for node in tree.body:
        if _is_docstring(node):
            retained_nodes.append(node)
            continue

        if isinstance(
            node,
            ast.Import,
        ):
            retained_names = [
                alias
                for alias in node.names
                if alias.name != "streamlit"
            ]

            if retained_names:
                retained_nodes.append(
                    ast.Import(
                        names=retained_names
                    )
                )

            continue

        if isinstance(
            node,
            ast.ImportFrom,
        ):
            if node.module != "streamlit":
                retained_nodes.append(node)

            continue

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            retained_nodes.append(node)
            continue

        if isinstance(
            node,
            (
                ast.Assign,
                ast.AnnAssign,
            ),
        ):
            names = _assignment_names(node)

            if not names:
                continue

            value_node = getattr(
                node,
                "value",
                None,
            )

            if value_node is None:
                continue

            uppercase_constants = all(
                name.isupper()
                for name in names
            )

            if (
                uppercase_constants
                and _is_safe_constant_expression(
                    value_node
                )
            ):
                retained_nodes.append(node)

            # Lowercase runtime assignments such as
            # result = st.session_state.get(...)
            # feature_df = build_invoice_features(...)
            # model = IsolationForest(...)
            # are intentionally excluded.

            continue

    safe_tree = ast.Module(
        body=retained_nodes,
        type_ignores=[],
    )

    ast.fix_missing_locations(
        safe_tree
    )

    module = ModuleType(module_name)

    module.__file__ = str(
        source_path
    )

    module.__package__ = ""

    sys.modules[module_name] = module

    try:
        code = compile(
            safe_tree,
            str(source_path),
            "exec",
        )

        exec(
            code,
            module.__dict__,
        )

    except Exception as error:
        sys.modules.pop(
            module_name,
            None,
        )

        raise LegacyModuleLoadError(
            f"Could not load reusable definitions "
            f"from {relative_path}: {error}"
        ) from error

    missing = [
        name
        for name in required_names
        if not hasattr(
            module,
            name,
        )
    ]

    if missing:
        raise LegacyModuleLoadError(
            f"Required definitions are missing from "
            f"{relative_path}: {', '.join(missing)}"
        )

    return module


def load_processing_modules() -> dict[str, ModuleType]:
    return {
        "parser": load_definitions(
            relative_path=(
                "page_code/2_Parse_and_Structure.py"
            ),
            module_name=(
                "legacy_parse_and_structure"
            ),
            required_names=[
                "parse_d2021",
            ],
        ),
        "validation": load_definitions(
            relative_path=(
                "page_code/3_Data_Validation.py"
            ),
            module_name=(
                "legacy_data_validation"
            ),
            required_names=[
                "validate_invoices",
            ],
        ),
        "reconciliation": load_definitions(
            relative_path=(
                "page_code/4_Invoice_Reconciliation.py"
            ),
            module_name=(
                "legacy_invoice_reconciliation"
            ),
            required_names=[
                "reconcile_invoices",
            ],
        ),
        "anomaly": load_definitions(
            relative_path=(
                "page_code/5_Anomaly_Detection.py"
            ),
            module_name=(
                "legacy_anomaly_detection"
            ),
            required_names=[
                "build_invoice_features",
                "find_unusual_features",
                "assign_risk",
            ],
        ),
        "risk": load_definitions(
            relative_path=(
                "page_code/"
                "6_Risk_Scoring_AI_Explanation.py"
            ),
            module_name=(
                "legacy_risk_scoring"
            ),
            required_names=[
                "create_risk_results",
            ],
        ),
    }