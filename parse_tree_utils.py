from __future__ import annotations

from antlr4 import ParserRuleContext
from antlr4.tree.Tree import TerminalNodeImpl


def node_label(node, parser=None) -> str:
    if isinstance(node, TerminalNodeImpl):
        text = node.getText().replace("\n", "\\n").replace("\t", "\\t")
        return f"TOKEN  {text}"
    if isinstance(node, ParserRuleContext):
        if parser is not None:
            try:
                rule = parser.ruleNames[node.getRuleIndex()]
            except Exception:
                rule = type(node).__name__.replace("Context", "")
        else:
            rule = type(node).__name__.replace("Context", "")
        text = node.getText().replace("\n", " ")
        if len(text) > 70:
            text = text[:67] + "..."
        return f"{rule}  ·  {text}"
    return str(node)


def tree_to_indented_text(root, parser=None, max_nodes: int = 3000) -> str:
    lines: list[str] = []
    seen = 0

    def walk(node, depth: int) -> None:
        nonlocal seen
        if seen >= max_nodes:
            return
        seen += 1
        lines.append("  " * depth + node_label(node, parser))
        for i in range(getattr(node, "getChildCount", lambda: 0)()):
            walk(node.getChild(i), depth + 1)

    walk(root, 0)
    if seen >= max_nodes:
        lines.append("... árbol truncado por tamaño ...")
    return "\n".join(lines)
