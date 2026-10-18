"""windows-uia MCP Server (WIP).

通过 Windows UI Automation 读取桌面窗口与控件树。仅支持 Windows 原生运行。
"""
import uiautomation as auto
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("windows-uia")


def _describe(control) -> dict:
    rect = control.BoundingRectangle
    return {
        "name": control.Name,
        "type": control.ControlTypeName,
        "class": control.ClassName,
        "automation_id": control.AutomationId,
        "rect": [rect.left, rect.top, rect.right, rect.bottom],
    }


@mcp.tool()
def list_windows() -> list[dict]:
    """列出桌面上所有可见的顶层窗口。"""
    root = auto.GetRootControl()
    return [_describe(w) for w in root.GetChildren() if w.Name]


def _walk(control, depth: int, max_depth: int, max_children: int) -> dict:
    node = _describe(control)
    if depth < max_depth:
        children = control.GetChildren()[:max_children]
        node["children"] = [
            _walk(c, depth + 1, max_depth, max_children) for c in children
        ]
    return node


@mcp.tool()
def get_window_tree(window_name: str, max_depth: int = 3, max_children: int = 50) -> dict:
    """获取指定窗口的控件树。

    Args:
        window_name: 窗口标题（包含匹配）
        max_depth: 最大遍历深度，避免输出过大
        max_children: 每层最多返回的子控件数
    """
    window = auto.WindowControl(searchDepth=1, SubName=window_name)
    if not window.Exists(maxSearchSeconds=3):
        return {"error": f"未找到标题包含 '{window_name}' 的窗口"}
    return _walk(window, 0, max_depth, max_children)


if __name__ == "__main__":
    mcp.run()
