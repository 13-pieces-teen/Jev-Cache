"""Display only observed facts; this module does not choose or execute actions."""

from dataclasses import dataclass


def human_bytes(number: int | float, signed=False) -> str:
    prefix = "+" if signed and number > 0 else "−" if number < 0 else ""
    value = abs(number)
    if value >= 1024**3:
        return f"{prefix}{value / 1024**3:.1f} GB"
    return f"{prefix}{value / 1024**2:.0f} MB"


def observation_text(measurement: dict) -> str:
    if not measurement.get("valid"):
        if measurement.get("reason") == "measuring":
            return "正在观察内存变化…"
        return "本次无法确定内存变化"
    delta = measurement["delta_bytes"]
    if abs(delta) < 1024**2:
        return "处理后可用内存基本没有变化"
    direction = "增加" if delta > 0 else "减少"
    return f"处理后可用内存{direction}约 {human_bytes(abs(delta))}"


@dataclass(frozen=True)
class ReceiptView:
    headline: str = "还没有处理记录"
    object_text: str = "清理完成后，这里会显示实际处理的内容。"
    observation: str = ""
    detail: str = ""


def receipt_view(state: dict) -> ReceiptView:
    history = state.get("history", [])
    if not history:
        return ReceiptView()
    record = max(history, key=lambda r: r.get("at", 0))
    status = record.get("status")
    name = record.get("name", "")
    if status != "completed":
        return ReceiptView(
            "正在等待处理结果" if status == "requested" else "本次未确认完成",
            name,
            "",
            record.get("message", "尚未收到完成回执。"),
        )
    is_tab = record.get("kind") == "tab"
    measurement = record.get("measurement", {})
    pending_result = state.get("last_result") or {}
    # A previous action (even one with the same name) must never supply this action's number.
    if not measurement and pending_result.get("action_id") == record.get("id"):
        measurement = pending_result
    return ReceiptView(
        "已释放 1 个网页" if is_tab else "已退出 1 个应用",
        name + (" · 标签页仍保留" if is_tab else " · 已确认退出"),
        observation_text(measurement),
        "其他应用的活动也可能影响这个数值。" if measurement.get("valid") else "",
    )


def status_text(state: dict) -> str:
    phase = state.get("phase", "idle")
    if state.get("paused"):
        return "清理已暂停"
    if phase == "judging":
        return "正在判断哪些暂时用不上"
    if phase == "connecting":
        return "正在测试 Jev 连接"
    if phase == "executing":
        return "正在清理，请稍候"
    if not state.get("sample"):
        return "正在了解这台电脑"
    return "内存有点紧张" if state.get("memory_pressure") else "内存目前够用"
