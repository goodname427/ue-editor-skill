"""
编辑器侧模块共用的小工具：取 AgentTools 的 C++ 库、解析它返回的 JSON。ue_input / ue_wbp 都从这里取，不各写一份。
"""
import json
import unreal


def require(name):
    """取 unreal 上的 AgentTools 函数库；插件没编译或没启用时给出明确提示。"""
    lib = getattr(unreal, name, None)
    if lib is None:
        raise RuntimeError('%s not found: compile and enable plugin AgentTools, then restart the editor' % name)
    return lib


def parse(raw):
    """解析 C++ 返回的 JSON；{"success": false, ...} 或 {"error": ...} 时抛异常。"""
    data = json.loads(raw)
    if isinstance(data, dict) and (data.get('error') or data.get('success') is False):
        raise RuntimeError(data.get('error') or data.get('message'))
    return data
