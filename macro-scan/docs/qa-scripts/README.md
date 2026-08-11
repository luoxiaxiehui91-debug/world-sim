# qa-scripts — 开阳 M-1 news_geo 图层验收脚本

> 对应验收文档：`../arg-map-qa-2026-08-11.md`（§1/§4/§5/§6）。
> 维护：qa-map + data-map。脚本与验收文档同步更新，二者不一致时以文档为准并回改脚本。

## 文件清单

| 文件 | 作者 | 职责 | 运行位置 |
|------|------|------|---------|
| `verify_data.py` | qa-map | **AC-M1-01~12 + AC-R-04 + 门禁 G-M1/M2/M4/M5** 数据层断言（news_geo.json 契约/值域/新鲜度/时间窗/单写者） | NAS 侧 `python3` |
| `verify_data_map.py` | data-map | **jsonl→news_geo.json 派生正确性抽查**（event_code/root_code 持久化、字段映射、24h 窗口）。已含双 WARN 路径：GDELT 断供降 WARN、部署后首个带码增量未到降 WARN；tail 取样自动取最新增量批次判定（避免新旧行混合误 FAIL） | NAS 容器内 `python3` |
| `verify_front.sh` | qa-map | **AC-R-05 前端单测**（npm test）+ **浏览器人工项清单**（AC-F-01~05 / G-M3） | 构建机 bash（npm test）+ 主理人浏览器复核 |

## 部署后验收流程（先重采基线 → 再跑门禁）

```bash
# 0) 部署完成（arch-map 通知）后，先重采基线（§0 对照锚点）：
ssh nas 'python3 /vol2/1000/software/world-sim/macro-scan/docs/qa-scripts/verify_data.py --baseline'

# 1) 数据层主闸（每日一次，建议 07:15 后）：
ssh nas 'python3 /vol2/1000/software/world-sim/macro-scan/docs/qa-scripts/verify_data.py'
#    —— 连续 3 天加 --snapshot 累积观测，之后跑门禁：
ssh nas 'python3 /vol2/1000/software/world-sim/macro-scan/docs/qa-scripts/verify_data.py --snapshot --gate'
#    部署满 48h 后追加 --enforce-unknown（unknown<5% 硬判定）：
ssh nas 'python3 /vol2/1000/software/world-sim/macro-scan/docs/qa-scripts/verify_data.py --gate --enforce-unknown'

# 2) 派生正确性抽查（data-map 脚本，容器内只读）：
ssh nas 'docker exec -i macro-scan-macro-scan-1 python3 -' < verify_data_map.py

# 3) 前端单测 + 人工清单（构建机）：
bash verify_front.sh            # npm test 全绿 + 打印浏览器人工项清单（由主理人复核）
```

## 参数速查

- `verify_data.py`：`--data-dir DIR`（默认 /vol2/1000/software/macro-scan/data）、
  `--enforce-unknown`、`--snapshot`、`--gate`、`--bench-jsonl`、`--baseline`、
  `--window-hours N`（默认 168=7d，24h 窗传 24）、`--max-age-hours N`（默认 36h，I15 传 1）。
- `verify_front.sh`：`--npm-only`（只跑单测）、`--list-only`（只打印人工清单）、
  `--kaiyang-dir PATH`（默认 ../kaiyang-build）。

## 退出码约定

- 全 PASS = 0；任一 FAIL 或门禁未决（观测不足）= 1；运行环境缺失 = 2。
