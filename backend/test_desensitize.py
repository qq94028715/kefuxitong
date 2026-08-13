"""昵称/手机号脱敏验证（直接调 _clean_chat，不碰库）。"""
import sys

sys.path.insert(0, r"E:\project\kefuxitong_v0.7_dev_20260813\kefuxitong\backend")

from app.main import _clean_chat

RAW = """聊天对象\t聊天内容\t聊天时间
张三\t这个 PVC 板能做耐温的吗？\t2026-08-01 10:00:00
中科立得旗舰店:小王\t可以的，常规耐温 60 度。张三，你用途环境是多少度？\t2026-08-01 10:01:00
张三\t大概 80 度，能做吗？\t2026-08-01 10:02:00
中科立得旗舰店:小王\t80 度建议 CPVC。小王这边给你报价，电话 13812345678\t2026-08-01 10:03:00
张三\t好的 13812345678 那就按这个来\t2026-08-01 10:04:00
李四\t这个我也要问问，张三你那边收到样品了吗？\t2026-08-01 10:05:00
中科立得旗舰店:小王\t李四您好，样品已寄出 13900001234\t2026-08-01 10:06:00
"""

text, title = _clean_chat(RAW)
print("=== 标题 ===")
print(title)
print("=== 清洗+脱敏结果 ===")
print(text)

# 断言
assert "张三" not in text, "张三 未脱敏"
assert "李四" not in text, "李四 未脱敏"
assert "小王" not in text, "小王 未脱敏"
assert "13812345678" not in text, "手机号1 未打码"
assert "13900001234" not in text, "手机号2 未打码"
assert "138****5678" in text, "手机号1 打码格式错误"
assert "客户1" in text, "客户1 未出现"
assert "客户2" in text, "客户2 未出现"
assert "客服" in text, "客服 未出现"
print("=== 断言全部通过 ===")
