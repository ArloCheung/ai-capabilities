"""State：整张图共享的"黑板"。

LangGraph 的核心约定：
- 节点函数接收当前 State，返回一个 dict，只包含它想更新的字段（部分更新）。
- 默认规则是"覆盖"：新值替换旧值。
- 用 Annotated[类型, reducer] 给字段指定合并规则。并行分支（Send 扇出）同一步里
  写同一个字段时，必须有 reducer，否则 LangGraph 会报 InvalidUpdateError。
- State 每一步都会被 checkpointer 序列化保存，所以只放可 JSON/pickle 的小数据
  （路径、计数、摘要），大文件（图片/视频）留在磁盘上，State 里存路径即可。
"""
from typing import Annotated, Literal, TypedDict


def merge_dict(old: dict | None, new: dict | None) -> dict:
    """并行的 render_chain 各自返回 {镜头id: 视频路径}，这里合并成一个大 dict。"""
    return {**(old or {}), **(new or {})}


def collect_failures(old: list | None, new: list | None) -> list:
    """失败的链累加；传入 None 表示"清空"（每一轮重新派发前由 plan_videos 清空）。"""
    if new is None:
        return []
    return (old or []) + new


class GenState(TypedDict, total=False):
    # ---- 运行参数（入口写入，之后只读）----
    mode: Literal["novel", "daily"]
    mock: bool                  # 离线模式：不调用火山方舟
    review: bool                # 分镜+定妆图后是否暂停等人工审核
    env: dict                   # 传给原脚本 config.py 的环境变量（决定输出目录等）
    input_path: str             # 小说 txt
    chars: int
    storyboard_file: str | None  # 直接用现成分镜 JSON
    date: str                   # 每日模式的日期

    # ---- 各步骤产物 ----
    trends_count: int
    story: dict                 # {topic, title, logline, ...}
    story_path: str
    storyboard_path: str
    shot_count: int
    total_seconds: int
    assets: list[str]
    feedback: str               # 审核时给分镜的修改意见，会追加进分镜提示词

    # ---- 视频：扇出/汇总 ----
    video_round: int
    videos: Annotated[dict, merge_dict]
    failed_chains: Annotated[list, collect_failures]

    audio_lines: int
    final_path: str
    outbox_path: str
    error: str


class ChainTask(TypedDict):
    """Send 派发给 render_chain 的私有输入：不是整个 GenState，只是一条镜头链。"""
    env: dict
    mock: bool
    chain_ids: list[str]
