"""
fetch_sipri_backdrop.py — SIPRI/NTI 军事背景静态卡片管理

SIPRI（斯德哥尔摩国际和平研究所）年度军费和武器转让数据，
NTI 核态势评估数据。

这些是年度/季度静态数据，不走日频调度。
本脚本：
  1. 从预设位置读取手工维护的 SIPRI 摘要
  2. 写入 /data/static/military_backdrop.md
  3. 天璇激活时读取此文件注入推演初始化 system prompt

手工维护流程：
  每年 SIPRI 发布新年鉴（通常4-6月）后，
  运维者更新 /data/static/sipri_summary.txt，
  然后运行此脚本重新生成 military_backdrop.md。
"""
import os
from datetime import datetime

try:
    from optim_config import DATA_DIR
except ImportError:
    DATA_DIR = os.path.join(
        os.environ.get("OPENCLAW_WORKSPACE", "/workspace"), "data"
    )

STATIC_DIR    = os.path.join(DATA_DIR, "static")
BACKDROP_PATH = os.path.join(STATIC_DIR, "military_backdrop.md")


# ── 硬编码的 2025 年基线数据（待年度手工更新） ────────────────────────────────

SIPRI_2025_BASELINE = """
## 军事结构背景（SIPRI 2025 年鉴基线 · 年度更新）

> 来源：SIPRI Yearbook 2025 | 更新日期：{date}
> 注意：此为结构性背景数据，反映长期军事格局，非实时事件信号。

### 全球军费开支（2024年）
- **全球总计**：约 2.44 万亿美元（历史新高，连续9年增长）
- **美国**：9,160 亿美元（占全球 37%）
- **中国**：估计 3,100 亿美元（占全球 13%，官方低报）
- **俄罗斯**：约 1,490 亿美元（GDP占比 7.1%，战时峰值）
- **欧洲 NATO**：同比增 17%，多国突破 GDP 2% 目标

### 核武器态势（NTI 2025 评估）
- **美国**：约 5,550 枚（部署 1,700 枚）
- **俄罗斯**：约 6,255 枚（部署 1,674 枚）；2023 年宣布暂停 New START
- **中国**：约 500 枚（快速扩张中，预计 2035 年达 1,000 枚）
- **北朝鲜**：约 40-50 枚，持续测试中程弹道导弹

### 关键军事技术扩散
- **高超音速武器**：俄中美均已服役，欧洲加速研发
- **无人机战争**：乌俄冲突验证大规模集群战术，台海和中东高度关注
- **太空军事化**：反卫星武器测试增加，GPS/通信卫星脆弱性上升
- **AI军事应用**：自主武器系统研发加速，尚无国际规范

### 热点地区军事态势
- **台海**：解放军台海演习常态化；美台军售创历史新高；
  第一岛链美军部署增强（关岛THAAD、菲律宾基地扩展）
- **乌克兰**：俄军持续消耗战；NATO 持续武器供应；
  双方均面临弹药短缺，战线相对稳定
- **中东**：以色列-哈马斯/黎巴嫩冲突持续；
  胡塞武装红海威胁；伊朗核计划接近核门槛

### 供应链军事风险
- **半导体**：台积电占全球先进芯片 92%，台海风险直接威胁军事电子供应链
- **稀土**：中国控制全球 60% 稀土开采，美国已启动国内供应链重建（2027 年见效）
- **火药/弹药**：乌克兰冲突暴露西方弹药库存严重不足，欧洲产能扩充需 3-5 年
""".strip()


def generate_military_backdrop(custom_summary: str = None) -> str:
    """生成 military_backdrop.md 内容。"""
    summary = custom_summary or SIPRI_2025_BASELINE.format(
        date=datetime.now().strftime("%Y-%m-%d")
    )
    content = f"""# 军事结构背景卡片
> 天璇推演初始化时注入此文件（一次性），提供结构性军事背景。
> 此为静态数据，反映长期格局，不替代实时事件信号。
> 年度更新：运行 `python fetch_sipri_backdrop.py --update` 重新生成。

{summary}

---
*生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")} | 数据来源：SIPRI Yearbook + NTI Nuclear Security Index*
"""
    return content


def update_backdrop(custom_summary: str = None):
    os.makedirs(STATIC_DIR, exist_ok=True)
    content = generate_military_backdrop(custom_summary)
    _tmp_95 = BACKDROP_PATH + ".tmp"
    with open(_tmp_95, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(_tmp_95, BACKDROP_PATH)
    print(f"[sipri_backdrop] 军事背景卡片已更新 → {BACKDROP_PATH}")
    print(f"  字符数：{len(content)}")


def load_backdrop() -> str:
    """天璇推演时调用，返回背景卡片内容。"""
    if not os.path.exists(BACKDROP_PATH):
        # 首次运行自动生成
        update_backdrop()
    try:
        with open(BACKDROP_PATH, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


if __name__ == "__main__":
    import sys
    if "--update" in sys.argv or not os.path.exists(BACKDROP_PATH):
        update_backdrop()
    else:
        content = load_backdrop()
        print(f"[sipri_backdrop] 当前背景卡片：{len(content)} 字符")
        print(content[:500] + "...")
