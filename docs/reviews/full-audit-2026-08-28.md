# world-sim 全量审核报告

**日期**: 2026-08-28  
**方法**: 多 agent 多轮次编排。分两波：第一波审 kaiyang / macro-sim / macro-ji / infra-sql / docs（11 单元）；第二波补审最初被漏掉的 `macro-scan/核心代码`（42,566 行 / 119 文件采集+推演引擎，9 单元）。每单元并行审计 → 对每条 critical/high/medium 发现派独立 agent 读实际代码做对抗式验证 → 完整性复核。  
**验证**: 两波合计 100+ 条发现经独立对抗验证，**0 条被推翻（refuted）**；个别 severity 经核实有上下调整。  
**执行说明**: 第一波报告撰写 agent 两次遭网络中断、第二波一度触发 LLM 代理每日预算上限，均已断点续跑补齐。本报告由主控从审计 journal 汇编。

## 1. 执行摘要

两波合计 135 条发现。按严重度：

| 严重度 | 数量 |
|---|---|
| 🔴 critical | 1 |
| 🟠 high | 21 |
| 🟡 medium | 64 |
| ⚪ low | 49 |
| **合计** | **135** |

**整体健康度**：这是一个雄心很大、工程纪律总体在线的多子系统（天枢采集 / 天璇仿真 / 天玑验证 / 开阳可视化）。基础设施有明显加固痕迹（control_server fail-closed、FetcherBase 统一限速/重试/原子写/降级、部署脚本 set -euo pipefail、PG 绑 127.0.0.1）。但审计暴露出三类系统性问题：

1. **密钥与远程通道安全**：源码中硬编码真实凭据（Space-Track 邮箱+明文密码、NASA FIRMS key、ntfy 口令 1900），且 ntfy 指令通道建在公共 broker 上、口令空时 fail-open。
2. **“迁移只做一半”的 split-brain**：macro-scan 与 macro-ji 存在同名模块的已分叉双活副本（tianji_db/weight_matrix），文档称“已迁出”实为复制；契约模块 contracts.py 零采用；双 Monte Carlo 引擎并存且功能最全的一套已成死代码。
3. **预测验证闭环从未真正跑通**：多个 agent 独立指出——月度预测校验作业不在实际调度器里、结构层 LLM 评估/GDELT 调制无法进入生产衰退概率输出、Brier/校准不自动更新。这与系统“可验证的世界推演”的核心定位直接冲突。

## 2. 关键发现汇总（critical + high，跨两波）

### 🔴 [CRITICAL] fetch_spacetrack.py 硬编码真实邮箱与明文密码作为默认凭证

- **单元/维度**: 地缘/信号类爬虫 · 安全配置
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_spacetrack.py:41-42（另 line 3-4 注释暴露凭证与 S:\KEY\Space-Track.txt 路径）`
- **描述**: SPACETRACK_ID = os.environ.get('SPACETRACK_ID', 'REDACTED_SPACETRACK_ID') 与 SPACETRACK_PASS = os.environ.get('SPACETRACK_PASS', 'REDACTED_SPACETRACK_PASS') 把真实的 163 邮箱账号和明文密码写死为默认值，文件头注释也直接写出凭证。任何能读到该仓库（S 共享盘 / git 历史）的人即可用该凭证登录 Space-Track.org，且若该邮箱口令在别处复用则波及更广。这是明确的密钥泄露（critical）。失败场景：仓库被任何第三方读取即拿到可用明文口令。
- **证据**: SPACETRACK_ID   = os.environ.get("SPACETRACK_ID",   "REDACTED_SPACETRACK_ID")
SPACETRACK_PASS = os.environ.get("SPACETRACK_PASS",  "REDACTED_SPACETRACK_PASS")
- **建议**: 移除硬编码默认值，凭证缺失即 fail-loud（无 env 就报错退出、不内置回退）；轮换该 Space-Track 密码及关联 163 邮箱口令；清除 git 历史；文件头注释不应写明凭证或凭证文件路径。

### 🟠 [HIGH] 控制API令牌经 VITE_ 前缀注入，会被打入客户端产物并优先于用户令牌

- **单元/维度**: kaiyang 构建/部署/配置 · 安全配置
- **位置**: `kaiyang/src/config/controlConfig.ts:32-35, kaiyang/src/state/ControlContext.tsx:37-40, kaiyang/.env.local:1`
- **描述**: getEnvToken() 通过 import.meta.env.VITE_CONTROL_API_TOKEN 读取控制API令牌，resolveInitialToken() 让该 env 令牌优先于用户在 localStorage 输入的令牌。Vite 会把所有 VITE_ 前缀变量在构建期内联进客户端 JS。该令牌用于向天枢 control_server（DEFAULT_API_BASE_URL='http://192.168.31.108:8900/api/v1/control/'）鉴权控制/写操作。任何在 .env.local 存在时执行的 `vite build`（package.json build 脚本默认加载 .env.local）都会把明文令牌 d76af2153b36...（.env.local 实测有值）烘焙进任何人打开页面即可查看的 bundle。缓解事实：控制服务器为局域网地址(192.168.31.108)，且当前 kaiyang/dist 经 grep 未发现该令牌、.env.local 已被 gitignore 且不在 git 历史中——即当前尚未泄露，属设计层面的前瞻性风险。
- **证据**: controlConfig.ts:33 `const t = import.meta.env.VITE_CONTROL_API_TOKEN`；ControlContext.tsx:38-39 `const env = getEnvToken(); if (env) return env;`；.env.local:1 `VITE_CONTROL_API_TOKEN=d76af2153b36dcc23a3b4de1515200047d79315c0974fcfa`；grep dist 无匹配(exit 1)；git check-ignore kaiyang/.env.local 命中。
- **建议**: 控制平面的鉴权令牌不应经前端构建注入。建议移除 getEnvToken()/VITE_CONTROL_API_TOKEN 路径，仅保留用户手动输入(localStorage)方式；或改为由后端在受信任环境下持有令牌、前端通过会话/反向代理鉴权。若必须保留 env 注入，务必确保生产构建绝不加载含真实令牌的 .env.local，并将令牌视为已泄露定期轮换。

### 🟠 [HIGH] 生效中的 FRED_API_KEY 明文硬编码在多个受版本控制的文件中

- **单元/维度**: 安全与密钥专项 · 安全配置
- **位置**: `macro-scan/知识库/财经知识库/01_核心变量因果链/fetch_fred_ultra.py:10（及 fetch_fred_req.py:12 / fetch_fred_batch1.py:9 / fetch_fred_batch2.py:7 / P5_实时宏观分析标准化工作流.md:67，01_ 与 02_ 两套目录均有，共 8+ 处）`
- **描述**: FRED_API_KEY = "REDACTED_FRED_KEY" 直接写死在多个 git 受追踪的 .py 与 .md 文件里。经比对，该值与 macro-ji/.env、macro-sim/.env 中当前使用的 FRED_API_KEY 完全一致，即这是一把仍在生效的真实密钥被提交进了版本库。项目自己的审计文档（docs/archive/pre-deploy-audit-prompt-v3.8.6.md:97、macro-scan/TuiYan_CHANGELOG.md:3333）早已记录该问题但源码未清除。FRED 为免费只读公共数据 key、价值较低，故非 critical，但仍属版本库内的活跃凭据泄露。
- **证据**: fetch_fred_ultra.py:10 `FRED_API_KEY = "REDACTED_FRED_KEY"`；同值出现在 macro-ji/.env `FRED_API_KEY=REDACTED_FRED_KEY`（后者已被 .gitignore 忽略，未入库）。git ls-files --error-unmatch 对上述 .py/.md 均返回 tracked=YES。
- **建议**: 轮换该 FRED key；将所有 fetch_fred_*.py 改为 os.environ["FRED_API_KEY"] 读取（与 compose 的 ${FRED_API_KEY} 注入一致）；文档中的 key 用占位符替换。若曾对外/公开推送仓库，需在 git 历史中一并清除（filter-repo）。

### 🟠 [HIGH] 贝叶斯路径权重写回因 Path + str 抛 TypeError，calibration_score 永不落盘

- **单元/维度**: macro-ji 校准与验证 · 代码正确性
- **位置**: `macro-ji/verify_hypothesis.py:281`
- **描述**: update_path_weights 在 commit 分支用 _tmp_281 = PATHS_FILE + '.tmp' 构造临时文件名，但 PATHS_FILE 是 pathlib.Path 对象（第 40 行）。Python 中 Path + str 抛 TypeError（已实测：unsupported operand type(s) for +）。异常被第 286 行 except 捕获仅打印'写入失败'，导致 propagation_paths.yaml 的 calibration_score 永不写回。tianji_verify_cron.py 每月 1 日正以 --commit --update-weights 运行该脚本（第 30 行），Phase 3C 贝叶斯权重闭环实际完全失效——命中被计算打印但权重从不更新。
- **证据**: L40: PATHS_FILE = Path(WORKSPACE) / ... / 'propagation_paths.yaml'; L281: _tmp_281 = PATHS_FILE + '.tmp'; L286-287: except Exception as e: print('写入失败: '...)
- **建议**: 用 str(PATHS_FILE) + '.tmp' 或 PATHS_FILE.with_suffix(...) 构造临时路径；并将写失败从静默 print 升级为醒目告警。

### 🟠 [HIGH] 核心价值闭环（预测→验证→反哺）从未在真实数据上跑通，预测有效性近一年内无法检验

- **单元/维度**: 项目合理性与发展前景 · 项目合理性
- **位置**: `docs/tianji-design.md §六 · docs/reviews/roadmap-recommendations-20260815.md §0 · docs/arch_review_20260802.md 附录A`
- **描述**: 整个系统的存在理由是「观测→仿真预测→事后验证准确率→反哺权重」的科学闭环，但玉衡权重反馈（weight_update_log）从未产生过一行记录，Brier/BSS 从未在真实预测上计算过。由于绝大多数地缘预测到期日在 2027-02，系统的预测准确率在近一年内根本无法被度量。这意味着系统已运行数月，却没有任何证据表明其预测输出优于随机猜测。这是最大的战略风险：核心科学价值命题至今完全未被验证。
- **证据**: tianji-design.md §六：predictions 表实测「predictions=1（测试预测）… weight_update_log/actuals/evaluations=0」「反哺触发需 ≥8 条已验证样本，当前不触发」，且「当前 48 条 geo 预测 due_at 2027-02 未到期，2027-02 后自动验证首轮触发」。roadmap-recommendations §0：「本系统当前的瓶颈不是缺能力，而是已有能力空转…玉衡的评分→校准→权重反馈闭环代码就绪却数月空转」。arch_review 附录A：「这是一个能生成有说服力叙事的报告引擎，但其数值输出目前与有效预测无关」。
- **建议**: 承认当前处于「未验证」阶段，把有限精力集中到最小可闭环链路：让至少一批短周期（周/月）可自动验证的定量预测尽快落表并跑出首个真实 Brier/BSS，用预注册方向命中率检验（roadmap-recommendations 与 ADR-0012 均已提出，≥60% vs 随机基线）作为「系统是否值得继续投入」的 go/no-go 门。在此门通过前，冻结一切扩能力动作。

### 🟠 [HIGH] 赋予系统身份的旗舰能力「LLM 推演」在全部 19 个 agent 中零实现

- **单元/维度**: 项目合理性与发展前景 · 项目合理性
- **位置**: `S:/docs/decisions/world-deduction/0012-math-mc-kernel-over-llm-agents.md §4 · AGENTS.md 顶部定位 · macro-sim/README.md`
- **描述**: 系统反复强调自己是「演化/推演」而非「推理」，这个身份差异正建立在「agent 用 LLM 自主决策演化」之上。但该能力从未实现——agent 实际走 soul 规则 / legacy 规则兜底。系统当前是一个规则驱动的 ABM + LLM 叙事包装，与它对外宣称的「LLM 推演」有实质差距。这不是 bug 而是核心愿景与现实的长期背离，且直到 2026-08-25 试点才被发现。
- **证据**: ADR-0012 §4：「use_llm=True 单 run 试点…全程无 LLM 调用痕迹。根因：_decide_llm 方法在全部 19 个 agent 中零实现…「LLM 决策」只到接口声明层，实现从未存在——属「接口存在 ≠ 功能已实现」」。而 AGENTS.md 顶部定位：「macro-sim 演化未来路径（不是推理，是演化）」，README「让它们按各自逻辑互动，结果从演化中涌现」。
- **建议**: 在文档（AGENTS.md/README/design_v2）中把系统如实定位为「规则驱动 ABM + LLM 叙事层」，停止用「LLM 推演」描述现状。若确要实现 agent LLM 决策，按 ADR-0012 承认这是一个开发项目（需为各 agent 写 _decide_llm + prompt + 失败回退），先做门控实验证明其决策质量优于规则，再投入。

### 🟠 [HIGH] 模型本质是金融压力模拟器而非地缘推演器；核心量化缺陷（GRV 与 agent 决策解耦）潜伏约一个月

- **单元/维度**: 项目合理性与发展前景 · 项目合理性
- **位置**: `docs/arch_review_20260802.md 附录A补充 · STATUS.md「当前主线(08-26/08-27)」· docs/roadmap.md 天璇模型线`
- **描述**: 系统由地缘风险（GRV）触发，但推演引擎几乎全是金融传导逻辑，缺少地缘因果路径，与「世界推演」的定位不符。更严重的是，agent/事件决策长期无法影响被度量的标量 GRV（vol_ratio 恒 0.001），意味着相当长一段时间内 LLM/事件注入层对输出零效果却无人察觉，只在一次门控实验中偶然暴露。与此同时 roadmap 仍在持续扩张范围（S6/S7 日韩、政权更迭引擎、S8+ 印度/东南亚/拉美规划），而 arch_review 与 roadmap-recommendations §4 都明确「D1–D6 未关前，增加 Agent 的边际价值接近于零」。
- **证据**: arch_review 附录A：「天璇本质是金融压力模拟器而非地缘推演器…叙事里的台海冲突升级在推演引擎里等价于 GRV升高→A3做空→A6放大恐慌→A10跟风抛售，没有军事对峙→制裁→供应链断裂的路径」。STATUS 08-26：「标量 world.grv…LLM/S 类决策只写并行 dict grv_dimensions，从不回聚标量→agent 决策与度量标量解耦…修复已落地 c618809，vol_ratio 0.001→0.391」——即注入事件+LLM 决策后标量 GRV 波动恒=0.001（与裸推完全相同）。该 GRV 解耦属 08-02 arch_review D3 家族缺陷，直到 08-26 才修。
- **建议**: 把「地缘因果链缺失」和「核心量化缺陷未清零」作为扩 Agent 的硬门控，严格执行既有裁定（D1-D6 未关前不加 Agent）。补一层最小可信的主动监控——把「注入是否影响输出」（如 vol_ratio 非退化）纳入自检探针，避免此类「输出与输入解耦」再次静默潜伏。

### 🟠 [HIGH] 开源/交付就绪度低：明文密钥曾入 git 历史，转公开前存在硬闸

- **单元/维度**: 项目合理性与发展前景 · 项目合理性
- **位置**: `docs/decisions/OPEN-DECISIONS.md (P0-2) · docs/reviews/roadmap-recommendations-20260815.md P0-A · STATUS.md 08-23`
- **描述**: README 提到已建 GitHub 私有仓并有开源意图（迁移说明），但仓库 git 历史中含明文密钥，且 .git/config 曾内嵌可写 PAT。虽然工作树已清理、部分 key 已轮换，但历史泄露未清除、FRED/EIA 未轮换，构成「转公开前的硬闸」。这直接压低交付/开源就绪度，也是当前不敢 push/共享的根因之一。
- **证据**: OPEN-DECISIONS 总册 P0-2：「明文密钥入 git（macro-scan/docker-compose.yml 6 处，git 历史含）…git rm --cached 不够（历史仍含），需轮换受影响密钥…仓库转公开/外部共享前处理」，状态 OPEN。roadmap-recommendations P0-A：「.git/config 内嵌 live GitHub PAT…凡对 NAS 共享有读权限者 cat .git/config 即得写凭证」。STATUS 08-23 记 SF/mimo key 已轮换、工作树明文清零，但 FRED/EIA 待轮换、且 git 历史仍含旧明文。
- **建议**: 在任何对外共享前完成两步：(1) 轮换全部受影响密钥（含 FRED/EIA）使历史泄露失效；(2) 用 git filter-repo/BFG 重写历史清除明文与 PAT。之后固化 ${VAR}+未跟踪 .env 注入规范，并在 CI/pre-commit 加密钥扫描防回流。

### 🟠 [HIGH] Monte Carlo 初始扰动把 market_sentiment 钳到 [0,1]，系统性抹掉悲观起点并给主聚类变量注入正偏置

- **单元/维度**: macro-sim 核心推演逻辑 · 代码正确性
- **位置**: `core/bifurcation.py:236-242 (_add_initial_noise)`
- **描述**: market_sentiment 的语义域是 [-1,1]（apply_sentiment_delta 在 world_state.py:327 明确 clamp 到 [-1,1]，字段默认 0.0）。但 _add_initial_noise 的扰动循环里，除 china_credit_impulse 外所有变量走 else 分支 `max(0.0, min(1.0, current+noise))`，把 market_sentiment 也钳到 [0,1]。预测起点 world.market_sentiment 默认 0.0（load_from_macro_scan 从不给它赋值），noise=gauss(0,0.15)，因此所有负向噪声被截断到 0——初始情绪分布变成 [0,~0.4] 且在 0 处堆积质量，永远不可能为负。
- **证据**: noise_config 含 "market_sentiment": 0.15；循环 `else: setattr(w, var, max(0.0, min(1.0, current+noise)))`。而 run_prediction 的聚类主判据正是终态 sentiment（bifurcation.py:621 `primary_vals = final_sent_values if sent_std>0.15`）。world_state.py:55 `market_sentiment: float = 0.0`，load_from_macro_scan 返回的 MacroWorldState 未传 market_sentiment。
- **建议**: market_sentiment（以及任何语义可负的内生变量）在扰动时应 clamp 到 [-1,1]，与 _apply_delta/apply_sentiment_delta 口径一致。当前实现使整个集合的初始情绪带正偏，削弱路径多样性（悲观分叉起点被结构性排除），直接影响分叉/概率结论。

### 🟠 [HIGH] ntfy 指令通道建立在公共主题上且密钥可选（未设即零鉴权 fail-open）

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `ntfy_listener.py:74-80, 587-619 (url 构造在 595); 对比 control_server.py:79-84`
- **描述**: listen() 轮询 https://ntfy.sh/{NTFY_CMD_TOPIC}/json（595 行），ntfy.sh 是公共服务，任何知道主题名的人都可向该主题 publish 消息，消息会被 handle() 当作指令执行。唯一的鉴权是 parse_command 中的共享密钥前缀，但 line 74 `if NTFY_CMD_SECRET:` 是 fail-open：环境变量未设置时完全跳过密钥校验，任意一条主题消息即可触发指令。这与同项目 control_server.py:79-84 明确记录的 'fail-closed，未配置 token 拒绝所有控制操作' 的加固方向相反——ntfy_listener 未被同等硬化。可触发的指令包括 silence（静默 synthesis 规则，可压制真实告警）、dismiss_situation（归档追踪事件）、cmd_ask/cmd_analysis/cmd_hypothesis（调用 LLM，产生成本与 DoS），构成对推演系统信号完整性的篡改与资源耗尽。注：指令均以 argv 列表传给 subprocess（无 shell=True），未发现 shell 注入/RCE。
- **证据**: line 74: `if NTFY_CMD_SECRET:` (仅当非空才校验); line 75: `if parts[0] != NTFY_CMD_SECRET:`; line 595: `url = f"https://ntfy.sh/{NTFY_CMD_TOPIC}/json"`; 对比 control_server.py:84 `raise HTTPException(status_code=503, detail="CONTROL_TOKEN 未配置，控制 API 已禁用（fail-closed）")`
- **建议**: 强制要求 NTFY_CMD_SECRET，未配置时拒绝监听或拒绝执行（与 control_server fail-closed 一致）；密钥比较改用 hmac.compare_digest；考虑改用鉴权主题/自建带访问控制的通道而非公共 ntfy.sh。

### 🟠 [HIGH] ntfy 指令密钥以明文随消息发送在世界可读的公共主题上（泄露+重放）

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `ntfy_listener.py:69-80, 50-62`
- **描述**: parse_command 把消息首个 token 当密钥（`parts[0] != NTFY_CMD_SECRET`）。由于指令走公共 ntfy.sh 主题，密钥本身作为消息正文的第一个词在明文中传输，并被 ntfy.sh 缓存/对任何订阅该主题者可见。任何能读到该主题（只需主题名）的人都能从历史消息中读出密钥并重放，鉴权形同虚设。密钥前缀方案本质上把秘密暴露在它本应保护的同一信道里。此外 parts[0] != SECRET 为非恒定时间比较（次要，因信道本身已公开）。
- **证据**: line 75-77: `if parts[0] != NTFY_CMD_SECRET: return None` `parts = parts[1:]`（密钥即消息首词）; push_text line 55-60 向 https://ntfy.sh/ 明文 POST，佐证信道为公共 ntfy
- **建议**: 不要在公共信道传输长期共享密钥；改用一次性/时效性签名（如 HMAC over nonce+timestamp）或迁移到带传输层鉴权的私有主题；轮换现有密钥。

### 🟠 [HIGH] RAG 索引原子重建使用非法 SQL：TRUNCATE ... WHERE，重建路径必然失败

- **单元/维度**: DB 写入/RAG/迁移 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/rag_engine.py:200-203`
- **描述**: _build_index_pg 执行 `cur.execute("TRUNCATE rag.embeddings WHERE collection_name = %s", (COLLECTION_NAME,))`。PostgreSQL 的 TRUNCATE 语句不支持 WHERE 子句，也不接受绑定参数——这是语法错误（应为 DELETE FROM ... WHERE）。该语句在 `with pg.transaction()` 内执行，抛错后被外层 except 捕获，_build_index_pg 返回 0。build_index 是知识库重建的唯一在线路径（build_rag_index.py:58-60 调用），count==0 会让 build_rag_index.py:63-65 判定「索引构建失败」并 sys.exit(1)。函数 docstring 与 build_rag_index.py 注释都声称这是「TRUNCATE + INSERT 同事务，原子重建（C6 修复）」，但该修复本身是坏的。后果：知识库任何更新都无法重建向量索引，rag.embeddings 永久停留在 D0 一次性迁移时的旧内容（d0_migrate_rag.py 用的是正确的 ON CONFLICT DO UPDATE，未受影响），查询侧读到陈旧索引，推演的 RAG 检索质量长期漂移。
- **证据**: rag_engine.py:201 `"TRUNCATE rag.embeddings WHERE collection_name = %s"`；build_rag_index.py:60 `count = build_index(KB_DIR)`；build_rag_index.py:63-65 `if count == 0: ... sys.exit(1)`。PostgreSQL TRUNCATE 语法不含 WHERE 为已知事实。
- **建议**: 把 `TRUNCATE rag.embeddings WHERE collection_name = %s` 改为 `DELETE FROM rag.embeddings WHERE collection_name = %s`（DELETE 支持 WHERE 与参数，且在同一事务内即可保持原子重建语义）。改后应实际跑一次 build_rag_index.py 验证 count>0 且退出码为 0。

### 🟠 [HIGH] 月度预测校验 verify_predictions.py 从未按计划自动运行

- **单元/维度**: 调度/部署/供应链 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/scheduler.py (JOBS 列表 41-119) 对照 S:/world-sim/macro-scan/crontab:23 与 S:/world-sim/macro-scan/entrypoint.sh`
- **描述**: crontab 第22-23行安排 verify_predictions.py 每月1日09:00运行，且 update_kb_numbers 注释称『建议跟在 verify_predictions 之后』。但 entrypoint.sh 明确用 Python scheduler 取代 cron(注释:『seccomp blocks cron fork』)且从不启动 cron；而 scheduler.py 的 JOBS 里有 kb_update(0905 dom=1)却完全没有 verify_predictions 作业项。grep 确认 verify_predictions 仅在 ntfy_listener.py 的手动指令 cmd_verify() 里被调用。结果:自动化预测校验(Brier/校准跟踪)在生产调度里从不发生，只能靠人手 ntfy 触发；而 kb_update 每月仍在未经校验的预测上照跑。对一个以预测准确度为核心的系统，这是静默的功能缺失。
- **证据**: crontab:23 `0 9 1 * * root cd /app && python3 verify_predictions.py`；entrypoint.sh 只 `python3 scheduler.py ... &` 从不启动 cron；scheduler.py JOBS 无 verify_predictions；grep 结果仅 ntfy_listener.py cmd_verify() 与 update_kb_numbers.py 文档注释引用它。
- **建议**: 把 verify_predictions.py 作为独立作业加入 scheduler.py JOBS(每月1日、排在 kb_update 0905 之前，如 0900 dom=1)，或彻底删除已死的 crontab 避免误导。并在 startup_checks 里加一条『crontab 与 scheduler JOBS 一致性』断言防止再次漂移。

### 🟠 [HIGH] deploy.sh --build 构建的镜像 tag 与线上 compose 期望 tag 不一致(v7 vs v8)

- **单元/维度**: 调度/部署/供应链 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/deploy.sh:68-74 (_build), 对照 docker-compose.yml:3 与 docker-compose.example.yml:6`
- **描述**: _build() 用 `grep 'image:' docker-compose.example.yml | grep -o 'macro-scan:v[0-9]*'` 取 IMAGE_TAG，example 文件写的是 v7；随后 `docker build -t $IMAGE_TAG .` 构建 macro-scan:v7，再 `docker compose up -d`。但线上 docker-compose.yml 写的是 `image: macro-scan:v8`。因此 compose 启动的是 v8(旧镜像或不存在),刚构建的 v7 被完全忽略——即『重建部署』实际不会让新代码/新依赖生效，或直接因找不到 v8 失败。根因是 tag 真相源取自被 .gitignore 排除、已与线上 compose 漂移的模板文件。
- **证据**: deploy.sh:70 `IMAGE_TAG=$(grep 'image:' docker-compose.example.yml | grep -o 'macro-scan:v[0-9]*' | head -1)`；docker-compose.example.yml:6 `image: macro-scan:v7`；docker-compose.yml:3 `image: macro-scan:v8`。
- **建议**: _build 应从实际使用的 docker-compose.yml 取 tag(或改用 `docker compose build`),避免从 example 模板推导；并统一 example 与线上 compose 的 image tag。

### 🟠 [HIGH] narrative_processor 冷启动分支缩进错误：PG 密度标记无条件写入，与 SQLite 发散，向推演引擎持续注入虚假密度突增

- **单元/维度**: LLM/叙事与注入面 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/narrative_processor.py:282-291`
- **描述**: 在 update_density_flags 的冷启动分支（hist_rows<7），SQLite 的 conn.execute(INSERT ... narrative_density_flags) 位于 `if today_count > avg_7 * 1.5:` 块内（第285行，缩进44空格），是有条件的；但紧随其后的 PG 镜像写 `upsert_tianji_narrative_density_flag(dim, now.isoformat(), 1.6, 0)`（第290行，缩进20空格）被 dedent 到 `if len(hist_rows) >= 1:` 层级，与第284行的 `if today_count` 平级，因此它是无条件执行的——只要该维度有 ≥1 天历史，每次运行都会向 PG 的 tianji.narrative_density_flags 写入一条 z_score=1.6、consumed=0 的'密度突增'标记，而不管 today_count 是否真的超阈值。get_flagged_dimensions() 从 PG（pg_read）读取 consumed=0 的标记，故所有处于冷启动的维度都会被误报为密度突增。冷启动分支低于阈值时也从不 DELETE 旧标记（与 z-score 分支不同），标记被消费后下轮又被重新写回 consumed=0，形成持久噪声。对低频维度（如 seismic_risk / japan_monetary，可能长期 <7 天有内容）等于永久误报。
- **证据**: 第284-290行：`                    if today_count > avg_7 * 1.5:` (20空格) / `                                            conn.execute("""...INSERT OR REPLACE INTO narrative_density_flags...""", (dim, now.isoformat(), 1.6))` (conn.execute缩进44空格，属于if块) / `                    upsert_tianji_narrative_density_flag(dim, now.isoformat(), 1.6, 0)` (20空格，与if today_count平级=无条件)。z-score 正常分支（第299-311行）对 SQLite 和 PG 都做了 insert/delete 配对，冷启动分支缺失该配对且缩进错位。
- **建议**: 将第290行 upsert_tianji_narrative_density_flag 缩进到与第285行 conn.execute 同层（即 `if today_count > avg_7 * 1.5:` 块内），并为冷启动'低于阈值'情形补上 SQLite+PG 的 DELETE 配对，使双写一致。修复后建议一次性清理 PG 中冷启动期误写的 consumed=0 标记。

### 🟠 [HIGH] 生产 US 蒙特卡洛与结构先验/GDELT/反馈回路完全脱钩(功能引擎为死代码)

- **单元/维度**: 第二套 Monte Carlo/评分栈 · 架构一致性
- **位置**: `mc_engine.py:207-487 (run_monte_carlo); mc_engine.py:296-328,424-454; run_macro_analysis.py:63-69,2698-2701`
- **描述**: 事实：run_macro_analysis.py 第63-69行只从 mc_engine 导入 FEEDBACK_LOOPS/SCENARIOS/run_china_monte_carlo/run_stress_test/compare_all_scenarios，并不导入 run_monte_carlo；第2699-2701行美国 MC 走的是 monte_carlo_v2.run_monte_carlo_compat。全仓 grep 'run_monte_carlo\b' 除 def 与文档字符串外无任何调用点，故 mc_engine.run_monte_carlo(约280行 v1 GBM 引擎)是死代码。事实：仿真内的三项高级建模全部只存在于这个死引擎里——(a)结构层调制 compute_structural_mc_adjustments/load_structural_priors(第307-328行调整 _crisis_prob、oil_cpi_mult、unrate_sensitivity、gdp_drag)，(b)GDELT 地缘尾风险 get_gdelt_geo_modifier(第298-303、376、382、467行)，(c)FEEDBACK_LOOPS 的强度/衰减放大应用(第424-454行)。grep 确认 compute_structural_mc_adjustments/get_gdelt_geo_modifier 的唯一消费者就是 run_monte_carlo(死)+assess_structural 自身的 --show CLI。推断(标注)：因此 assess_structural_dimensions.py 每季度花费一次 LLM 调用产出并落盘的六维结构脆弱性评分，以及 GDELT 亚太尾风险上调(上限45%)，对生产输出的 recession_prob 零影响；run_monte_carlo_compat 明确忽略 coeffs 且不读结构先验/GDELT。
- **建议**: 明确二选一：要么删除死引擎 mc_engine.run_monte_carlo 并把结构先验/GDELT/反馈回路的调制逻辑迁移进 monte_carlo_v2(或 run_monte_carlo_compat 的封装层)，让它们真正影响生产 recession_prob；要么保留 v1 并在 run_macro_analysis 改回调用它。当前状态下应在 assess_structural_dimensions.py 顶部标注'此评估当前未接入生产 MC'，避免误以为结构层在起作用。

### 🟠 [HIGH] v2 衰退概率定义与文档口径不符：'任意≥2个负增长月'冒充'连续2季度负增长'

- **单元/维度**: 第二套 Monte Carlo/评分栈 · 代码正确性
- **位置**: `monte_carlo_v2.py:364-366`
- **描述**: 事实：_summarize 第364-366行 `any_negative_gdp = (paths[:, :, gdp_j] < 0).sum(axis=1) >= 2`，紧邻注释写的是'衰退：GDP持续2季度负增长'。代码实际是统计整个 horizon+1 个【月度】步中 gdp<0 的步数是否≥2，既非'连续'(可为任意两个不相邻的月)，也非'季度'(步长 DT=1/12 为月度)。事实：该 probabilities['recession'] 正是生产 recession_prob 的来源——run_monte_carlo_compat 第592行 `'recession_prob': round(probs.get('recession',0)*100,1)`，而 run_macro_analysis:2705 直接打印它。推断(标注)：'≥2个月 gdp<0'的门槛远比'连续两个季度'宽松，会系统性高估衰退概率(尤其危机档跳跃使个别月频繁转负)。这也与 mc_engine 死引擎里 signals>=2 的口径不一致，形成第三套定义。
- **建议**: 按文档意图改为检测连续负增长：例如对 gdp 路径求最长连续 gdp<0 段长度是否 ≥ 对应的季度月数(连续6个月)，或明确改注释与语义为'累计≥N个月负增长'并据此重新标定期望区间。修正后需重跑 calibrate_mc 校验单调性与档位期望。

### 🟠 [HIGH] c0 权重归一被 WEIGHT_FLOOR 钳位吞没：大维度全部塌成 0.05 且破坏 sum=1

- **单元/维度**: 第二套 Monte Carlo/评分栈 · 代码正确性
- **位置**: `c0_compute_weights.py:353-368,304-328`
- **描述**: 事实：compute_weights 第353-365行先在同一 target_type 内按逆波动率归一(`w = raw/tot`，注释'权重和=1')，再 `w = min(max(w, WEIGHT_FLOOR), WEIGHT_CEIL)`，WEIGHT_FLOOR=0.05。事实：FRED_SEED 里映射到 global_composite 的 FRED 序列约有 ~39 个(利率/通胀/增长/就业/股指/信用/美元/GPR家族/GSCPI 等)。归一后每个权重≈1/39≈0.026，全部 < 0.05，于是被 floor 统一钳到 0.05。后果(事实推导)：该维度所有序列权重变成同一个 0.05，逆波动率打分(_score_series 的 coverage×fresh×inv_cv)产生的差异被完全抹平；且和为 39×0.05≈1.95≠1，'权重和=1'不变量破裂。事实：verify() 第530-595行只校验 PG==yaml==派生行三者一致，不校验归一不变量，故这个塌缩静默通过验收。任何成员数 >20 的 target_type(1/N<floor)都会触发。
- **建议**: 在钳位后对每个 target_type 重新归一(clip→renormalize 迭代或 water-filling)，使和恢复为1并保留相对差异；或把 WEIGHT_FLOOR 设为相对于组规模的自适应下限(如 floor/N)。并在 verify() 增加'同 target_type 权重和≈1 且非全等'的断言。

### 🟠 [HIGH] tianji_db.py / weight_matrix.py 双活分叉，"必须同步"契约已破，INDEX 谎称"已迁出"

- **单元/维度**: 分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim · 架构一致性
- **位置**: `S:/world-sim/macro-scan/核心代码/tianji_db.py:4-16, S:/world-sim/macro-scan/核心代码/weight_matrix.py:207-209, S:/world-sim/macro-ji/tianji_db.py, S:/world-sim/macro-scan/INDEX.md:11`
- **描述**: diff 证实 tianji_db.py（ji 308 行 / scan 437 行）与 weight_matrix.py（ji 415 行 / scan 421 行）已分叉且行为不同。macro-scan/核心代码/tianji_db.py 顶部有明确维护警示：'⛔ 08-17 维护警示：本文件与 macro-ji/tianji_db.py 是两份独立实现…改本文件必须同步 macro-ji 版（或反之），两份接口签名应保持一致'。但契约已破：macro-ji 版 update_prediction_verified 带 human_note 参数并写 human_note 列、且在 weight_update_log 写 updated_at（注释'08-18 P1-5'），macro-scan 版两者皆无——签名和写入列已不一致。两份都仍在生产被 import：macro-scan 侧 tianji_db 被 narrative_processor.py + weight_matrix.py 引用，weight_matrix 被 c0_compute_weights.py 引用（grep 确认），且两份最终都写同一个 worldsim-pg tianji schema。此外 weight_matrix.py 的分叉方向相反：macro-scan 版有 M11(08-17) 加固（except 改 fail-loud 打印、写盘改 tmp+os.replace 原子写），而 macro-ji README 明确宣称 weight_matrix（玉衡）是天玑'四件套'自有模块，其副本却缺这些加固。同时 INDEX.md:11 备注称 'tianji_db/tianji_verifier/weight_matrix 已迁出'——但 tianji_verifier/verify_watchdog 确实已从 macro-scan 删除（ls 不存在），tianji_db/weight_matrix 却只是被复制、两处双活。'已迁出'表述与实际不符。
- **建议**: 按已登记的 review-todo P2 方向合并为单一实现：预测链既已转 PG（world-sim/README 声明），让 macro-scan 侧 tianji_db 写路径直接复用 macro-ji 的 PG 实现或抽成共享包，删除 macro-scan 侧 SQLite 脚手架（_PG_ONLY=1 下已是 Noop 死码）。合并前至少立即对齐两份的 human_note/updated_at 列与 weight_matrix 的原子写/fail-loud 加固，并修正 INDEX '已迁出'为'已复制分叉（待合并）'。

### 🟠 [HIGH] contracts.py 契约从未被任何生产者采用，其文档点名的 schema_version 语义错位在生产代码中仍然存在

- **单元/维度**: 采集框架与契约 · 文档漂移
- **位置**: `contracts.py:59,218; compute_fci.py:62,298; compute_probit.py:42,276`
- **描述**: contracts.py 自我定位为「天枢所有指标产出的唯一记录形状」，并在文档 §schema_version 明确指出『现网 fci_latest.json 把 "fci-1.1" 写进 schema_version，这是语义错位，本契约的直接动因之一』，设计了 IndicatorPoint（schema_version Literal["1.0"] 与 model_ver 两个独立字段）来根治。但全库 Grep（import contracts / IndicatorEnvelope / IndicatorPoint / build_point / dump_envelope / missing_point）仅命中 contracts.py 自身——没有任何生产者导入它。实际生产者仍在犯它要修的错：compute_fci.py:62 `SCHEMA_VERSION = 'fci-1.1'`，:298 payload `'schema_version': SCHEMA_VERSION` 直接把模型版本写进 schema_version，且 payload 无 model_ver 字段；compute_probit.py:276 `"schema_version": MODEL_VER` 并注释『对齐 FCI 模式：此处为 model_ver』，同样把 model_ver（"probit-1.0"）写进 schema_version。更矛盾的是 compute_probit.py:42 定义 `SCHEMA_VERSION = "1.0.0"`（三段 SemVer），而 contracts.py Literal 锁死的是 "1.0"——即便契约被启用，"1.0.0" 也会被 ValidationError 拒收。三处 schema_version 约定（contracts "1.0" / fci "fci-1.1" / probit "1.0.0"+"probit-1.0"）互不一致。
- **证据**: compute_fci.py:62 `SCHEMA_VERSION = 'fci-1.1'`；:298 `'schema_version': SCHEMA_VERSION`（payload 无 model_ver）。compute_probit.py:42 `SCHEMA_VERSION = "1.0.0"`；:276 `"schema_version": MODEL_VER,  # 对齐 FCI 模式：此处为 model_ver`。contracts.py:218 `schema_version: Literal["1.0"]`；文档第22-24行点名此错位。Grep 全库仅 contracts.py 自身命中契约符号。
- **建议**: 二选一并落地：(a) 让 compute_fci.py / compute_probit.py 真正走 contracts.build_point + dump_envelope 产出 *_latest.json，从而消除 schema_version/model_ver 混用；或 (b) 若暂不迁移，则在 contracts.py 顶部显式标注其为『目标契约，尚未接线，当前生产文件不符合』，避免它被误读为已生效的强约束。同时统一 schema_version 取值（"1.0" vs "1.0.0"）。

### 🟠 [HIGH] fetch_firms.py 硬编码 NASA FIRMS API key 作为默认值

- **单元/维度**: 地缘/信号类爬虫 · 安全配置
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_firms.py:45`
- **描述**: FIRMS_MAP_KEY = os.environ.get('FIRMS_MAP_KEY', 'REDACTED_FIRMS_KEY') 把 NASA FIRMS MAP_KEY 明文写死在源码，且该 key 直接拼进请求 URL。泄露后他人可冒用该 key 拉取并触发限流。失败场景：key 随源码外泄→第三方大量请求触发限流→fetch_firms 拿到非 200/空数据全源失败，下游 climate/热异常图层失去火点输入。
- **证据**: FIRMS_MAP_KEY = os.environ.get('FIRMS_MAP_KEY', 'REDACTED_FIRMS_KEY')
- **建议**: 移除硬编码默认，凭证缺失时降级或 fail-loud；轮换该 FIRMS key；清除 git 历史。

### 🟠 [HIGH] fetch_gdelt_geo.py 增量拉取把 last_success_slot 记成最旧槽而非最新槽

- **单元/维度**: 地缘/信号类爬虫 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_gdelt_geo.py:955（配合 _gdelt_urls_last_slots 与 _compute_new_slots）`
- **描述**: _gdelt_urls_last_slots 生成的 URL 顺序是最新在前（offset 15,30,45,60 → 槽时间戳降序）。run_incremental 按 zip(urls, now_slots) 顺序 append 到 slots_ok，故 slots_ok 降序，slots_ok[-1] 是本轮最旧的成功槽。state[LAST_SLOT] 被设成这个最旧槽。下一轮 _compute_new_slots 用 s > last 过滤，凡比'上轮最旧槽'新的槽（含上轮已成功拉过的较新槽）都 > last，被重复拉取；last_success_slot 永不推进到最新，'no_new' 短路几乎不触发，每轮重复下载/解析 num_slots-1 个已处理槽。数据不重复仅因 _merge_jsonl 按 event_id 去重兜底，但增量设计失效、带宽/解析浪费、统计虚高。
- **证据**: state[STATE_KEY_LAST_SLOT] = slots_ok[-1] if slots_ok else state.get(STATE_KEY_LAST_SLOT)  # slots_ok 因 urls/now_slots 降序而降序，[-1] 是最旧槽
- **建议**: 把 state[STATE_KEY_LAST_SLOT] 设为 max(slots_ok)（最新成功槽）而非 slots_ok[-1]；或赋值前排序取最大。补单测覆盖'降序 URL → last 取最新'。

---

## 3. 第一波详细发现（kaiyang / macro-sim / macro-ji / infra-sql / docs）

> critical/high 已在第 2 节列出，此处含 medium / low。

### 🟡 [MEDIUM] standalone 产物目录未纳入 .gitignore，可能提交带明文令牌的可分发单文件

- **单元/维度**: kaiyang 构建/部署/配置 · 安全配置
- **位置**: `kaiyang/.gitignore:1-4, kaiyang/vite.config.standalone.ts:16, kaiyang/inject-standalone.mjs:12`
- **描述**: .gitignore 仅忽略 `dist`（git check-ignore 验证 kaiyang/dist 命中），未忽略 standalone 构建输出目录 dist-standalone（vite.config.standalone.ts outDir）与 kaiyang-standalone（inject-standalone.mjs 的 OUT）。这两个目录正是设计上要对外分发的“双击打开单文件”产物。若在 .env.local 存在时执行 standalone 构建，前述 VITE_CONTROL_API_TOKEN 会被内联进 kaiyang-standalone/index.html，而该目录不被忽略即可被 git add 并连同明文令牌一起提交/分发。当前这两个目录在磁盘上不存在（未构建），属前瞻性风险。
- **证据**: .gitignore 内容仅为 `node_modules / dist / *.local / .DS_Store`；vite.config.standalone.ts:16 `outDir: 'dist-standalone'`；inject-standalone.mjs:12 `const OUT = path.join(ROOT, 'kaiyang-standalone')`；git ls-files 对两目录返回空、磁盘 ls 亦不存在。
- **建议**: 在 kaiyang/.gitignore 中追加 `dist-standalone` 与 `kaiyang-standalone`（或统一 `dist*`/`*-standalone`）。结合上一条，避免任何对外分发产物携带控制令牌。

### 🟡 [MEDIUM] @rollup/rollup-linux-x64-gnu 被固定为硬 dependencies，破坏 Windows/macOS 上的 npm 安装

- **单元/维度**: kaiyang 构建/部署/配置 · 架构一致性
- **位置**: `kaiyang/package.json:15, kaiyang/package-lock.json:406-417`
- **描述**: package.json 的 dependencies 中显式加入了平台专属原生二进制 `@rollup/rollup-linux-x64-gnu`，package-lock 显示其 `os: [linux]` 限制且未标记为 optional/dev。当在非 linux 主机（本项目开发机为 win32）执行干净的 `npm ci`/`npm install` 时，npm 对 os/cpu 不匹配的显式依赖会报 EBADPLATFORM 而失败。Rollup 自身会按平台自动解析其可选原生依赖，通常无需手动锁定；此处硬编码很可能是为修复 Docker(linux) 构建而加，但放在 dependencies 会牺牲跨平台可安装性。
- **证据**: package.json:15 `"@rollup/rollup-linux-x64-gnu": "^4.62.3"` 位于 dependencies 段；package-lock.json:406-416 该节点 `"os": ["linux"]` 且无 `"optional": true`/`"dev": true`。
- **建议**: 将该包从 dependencies 移除（交由 rollup 的 optionalDependencies 机制自动解析），或至少移入 optionalDependencies；如需保证 Docker 构建拿到 linux 二进制，改用 CI/Dockerfile 内 `npm install --os=linux --cpu=x64` 或在容器内安装，而非污染主 manifest。

### 🟡 [MEDIUM] readable 兜底模板把 Agent 代号当动作翻译，输出泄漏原始代号

- **单元/维度**: macro-sim 输出/持久化/治理 · 代码正确性
- **位置**: `macro-sim/core/readable_report.py:181-182 (_fallback_template)`
- **描述**: 遍历 actions.items() 时 a=agent_id(键)、x=action(值)，但拼接动向时调用 _zh_action(str(a))，把 agent-id 传给动作词典。ACTION_ZH 里没有 'A1' 之类的键，_zh_action 原样返回，于是输出成『美联储A1』而非『美联储降息25bp』。变量 x 被绑定却从未使用，是明显的笔误。这恰是本模块设计目标（『输出自然零代号』）要杜绝的代号泄漏，且发生在 LLM 失败后的最后兜底路径——本应『永远有可读产出』，反而产出带裸代号的文本。对比同文件 _fmt_step_human:87 的正确写法 _zh_action(str(act)) 可确认这是 bug。
- **证据**: for a, x in (hist[worst].get("actions") or {}).items()) ... f"{_zh_agent(a)}{_zh_action(str(a))}"  —— 应为 _zh_action(str(x))；x 被绑定但从未使用
- **建议**: 改为 _zh_action(str(x))（把动作值而非 agent 键传入动作词典）。

### 🟡 [MEDIUM] chronicler 文档承诺的数字防幻觉校验未实现，校验函数为死代码

- **单元/维度**: macro-sim 输出/持久化/治理 · 代码正确性
- **位置**: `macro-sim/core/chronicler.py:8-11,107-129,179-182 (generate_chronicle)`
- **描述**: 模块 docstring 明确承诺『生成后数字校验器：文中数值必须出现在该卷 JSONL 数值集合（越界重写一次）』，并为此定义了 _numbers_in() 与 _allowed_numbers() 两个函数。但 generate_chronicle 在拼接每卷时（line 179 注释『数字校验：…简化：仅记录警告』）实际上既没有调用这两个函数，也没有输出任何警告或附注——LLM 返回的每卷文本被直接 strip 后写入报告。两个校验函数从头到尾无任何调用点，是死代码；模块标榜的核心『防幻觉』安全机制事实上不存在。缓解因素：run.py:107 已停用编年史生成，仅 replay CLI 仍走此路径，故实际影响有限。
- **证据**: docstring: '生成后数字校验器：文中数值必须出现在该卷 JSONL 数值集合（越界重写一次）'；line 179 注释后无任何校验/告警代码；_numbers_in(107)/_allowed_numbers(121) 全文件零调用
- **建议**: 要么按 docstring 真正实现越界数字标注/重写并调用 _allowed_numbers/_numbers_in，要么删除死代码并修正 docstring 与 line 179 注释，避免文档与行为漂移误导后续维护者以为有防护。

### 🟡 [MEDIUM] narrative_format 在多标签时静默丢弃首个标签前的正文

- **单元/维度**: macro-sim 输出/持久化/治理 · 代码正确性
- **位置**: `macro-sim/core/narrative_format.py:61-71 (format_narrative)`
- **描述**: 当叙事文本含 >=2 个 label 时，用 _SECTION_SPLIT_RE.split 得到 parts，再 zip(labels, parts[1:]) 逐段输出。若 LLM 在第一个 【label】/**label** 之前先输出了引言/前言正文，该正文落在 parts[0]，而 zip 从 parts[1:] 开始——parts[0] 被静默丢弃，不进报告也不告警。format_narrative 的输出直接进 run.py:491-492 的报告 lines，属报告内容丢失路径。虽然典型 LLM 叙事常直接以标签开头（不一定触发），但一旦有前导文字即无声吞掉。
- **证据**: parts = _SECTION_SPLIT_RE.split(narrative); for label, content in zip(labels, parts[1:]) —— parts[0]（首标签前正文）从不进入输出
- **建议**: 若 parts[0].strip() 非空，将其作为无标签前言段保留（追加到输出首部），或至少在检测到非空前导时告警。

### 🟡 [MEDIUM] Postgres 密码明文写入受追踪的决策文档

- **单元/维度**: 安全与密钥专项 · 安全配置
- **位置**: `docs/decisions/worldsim-rename-check.md:45`
- **描述**: 决策文档 P0-2 条目中原样抄录了 backup-pg.sh 的硬编码密码 PGPASSWORD="***REMOVED***"。该文件受 git 追踪。文档本身注明此密码与 connection.env 中的 WORLDSIM_APP_PW/WORLDSIM_RO_PW 不匹配、"已失效"，故实际危害降低；但一个看似真实的 DB 密码字符串进入版本库仍属密钥卫生问题，且无法确证其在任何历史时点从未生效。
- **证据**: worldsim-rename-check.md:45 `PGPASSWORD="***REMOVED***"` 与 connection.env 的 WORLDSIM_APP_PW / WORLDSIM_RO_PW 均不匹配（布尔比对 NO_MATCH）
- **建议**: 从文档中移除该明文，用 <redacted> 描述即可；确认该密码确未在任何 PG 实例上生效，如有疑虑则轮换。

### 🟡 [MEDIUM] .gitignore 声明忽略 macro-scan/docker-compose.yml，但该文件实际被 git 追踪

- **单元/维度**: 安全与密钥专项 · 安全配置
- **位置**: `.gitignore（`macro-scan/docker-compose.yml`）vs git ls-files 实际追踪的 macro-scan/docker-compose.yml`
- **描述**: .gitignore 显式列出 macro-scan/docker-compose.yml（注释意图是让含密钥的 compose 留在 NAS 本地、禁入 git），但 git ls-files 显示该文件仍被追踪——因其在加入忽略规则前已被提交，.gitignore 对已追踪文件无效。当前该文件用 ${FRED_API_KEY}/${SILICONFLOW_API_KEY}/${CONTROL_TOKEN} 等占位符，尚无明文泄露；但忽略意图已被架空：一旦有人在本地把真实 key 填进去（正是忽略规则想防范的操作），git 会静默追踪该改动并可能被提交。macro-ji/docker-compose.yml、macro-sim/docker-compose.yml 同样处于被追踪状态。
- **证据**: .gitignore 第含 `macro-scan/docker-compose.yml`；git ls-files 输出含 `macro-scan/docker-compose.yml`（tracked=YES）；文件内容 macro-scan/docker-compose.yml:30 `SILICONFLOW_API_KEY=${SILICONFLOW_API_KEY}`（占位符，当前无明文）
- **建议**: 确认这些 compose 是否真要入库：若要入库，从 .gitignore 删除对应条目以消除误导，并靠 code review 保证只用 ${VAR}；若不入库，git rm --cached 停止追踪。二者取一，消除声明与实际的漂移。

### 🟡 [MEDIUM] 控制 API token 通过 VITE_ 前缀注入会被打包进客户端 bundle

- **单元/维度**: 安全与密钥专项 · 安全配置
- **位置**: `kaiyang/src/config/controlConfig.ts:33（getEnvToken 读 import.meta.env.VITE_CONTROL_API_TOKEN）；配套 kaiyang/.env.local 内含真实 token`
- **描述**: getEnvToken() 从 import.meta.env.VITE_CONTROL_API_TOKEN 读取控制 API 的 Bearer token，controlApi.ts:212 用它注入 Authorization 头。Vite 的既定行为是把所有 VITE_ 前缀的环境变量在构建时内联进客户端 JS bundle（可验证事实），因此若构建时设置了该变量（kaiyang/.env.local 中确有真实值 d76af2153...），该 token 会被硬编码进发布的前端 JS，任何能加载前端的人都能从 bundle 提取它——而该 token 用于鉴权可触发采集/暂停等操作的控制 API，等于把"密钥"发给了所有前端用户，失去保护意义。当前 .env.local 未被追踪（正确），且代码另有 localStorage 手填 token 的路径可规避此问题。
- **证据**: controlConfig.ts:33 `const t = import.meta.env.VITE_CONTROL_API_TOKEN as string | undefined;`；kaiyang/.env.local `VITE_CONTROL_API_TOKEN=d76af2153b36dcc23a3b4de1515200047d79315c0974fcfa`
- **建议**: 生产构建不要设置 VITE_CONTROL_API_TOKEN，改为完全依赖用户在面板手填 token 存 localStorage 的路径；或将控制 API 置于需登录的反向代理之后，不靠内联到浏览器的静态 token。文档中明确警示 VITE_ 变量会进 bundle。

### 🟡 [MEDIUM] L3 LLM 负向确认（outcome=0）自动落库门槛恒不可达

- **单元/维度**: macro-ji 校准与验证 · 代码正确性
- **位置**: `macro-ji/llm_judge.py:143`
- **描述**: judge_prediction 中 outcome==0 自动落库条件为 conf>=0.85 and window_total>=200。但 window_total=len(arts)，arts 来自 fetch_window_news 且 SQL 带 LIMIT，默认 limit=40（第 66 行）。故 window_total 最多 40，window_total>=200 永远为假，outcome=0 恒走 suggestion_only，绝不自动 verified。设计意图（docstring/prompt 第 124 行'窗口新闻总量>=200'）衡量了错误的量——命中且被 LIMIT 40 截断的条数而非窗口文章总数，既定负向确认路径实为死代码，prompt 还向 LLM 谎报门槛。
- **证据**: L66: def fetch_window_news(due_at, keywords, limit=40); L108-110: arts=fetch_window_news(...); window_total=len(arts); L143: elif outcome==0 and conf>=0.85 and window_total>=200:
- **建议**: 单独查询窗口内文章总数（不带关键词过滤、不受 LIMIT 40 限制）作为覆盖度判据，与喂给 LLM 的命中标题数解耦；或将门槛调至与 limit 一致量级。

### 🟡 [MEDIUM] 反哺降权统计因 LEFT JOIN reasoning_trace 重复计数 brier

- **单元/维度**: macro-ji 校准与验证 · 代码正确性
- **位置**: `macro-ji/tianji_verifier.py:303`
- **描述**: check_and_generate_reweight_suggestions 用 predictions p LEFT JOIN reasoning_trace r ON r.prediction_id=p.id 取行。save_reasoning_trace（tianji_db.py:124）对同一 prediction_id 无去重，可插多条 trace。某预测有 N 条 trace 时其 p.brier_score 在结果集出现 N 次，既污染 all_briers（第 333 行）算出的 global_mean（偏向 trace 多者），也在按信源分组时被重复累加。降权判据 group_mean>global_mean*0.8 建立在扭曲基准上，可能误触发/漏触发权重下调建议。
- **证据**: L303-310: SELECT p.id,...,r.input_signals FROM predictions p LEFT JOIN reasoning_trace r ON r.prediction_id=p.id WHERE p.status='verified'; L333: all_briers=[row['brier_score'] for row in rows if ...]
- **建议**: 全局均值基于 DISTINCT 预测（先按 p.id 去重取 brier 再求均值），或用子查询/窗口聚合避免 JOIN 笛卡尔放大；分组累加同理按预测去重。

### 🟡 [MEDIUM] _fetch_fred_value 依赖 CSV 已按日期升序但从不排序

- **单元/维度**: macro-ji 校准与验证 · 代码正确性
- **位置**: `macro-ji/tianji_verifier.py:135`
- **描述**: _fetch_fred_value 收集 candidates=[(dt,v) for dt,v in rows if dt<=as_of_date] 后直接返回 candidates[-1][1]，依赖文件行序等于日期升序取'最近可用值'。同文件 _fetch_grv_value 显式 sort（第 162 行），verify_geo_auto._load_series 也显式 sort（第 134 行）。此处独缺排序，若某 FRED CSV 非严格升序（追加乱序/修订行），将返回错误 as_of 值，进而算出错误 outcome 与 Brier。
- **证据**: L136: candidates=[(dt,v) for dt,v in rows if dt<=as_of_date and not math.isnan(v)]; L137-138: if candidates: return candidates[-1][1]（无 sort）；对比 L162 _fetch_grv_value 的 candidates.sort(...)
- **建议**: 与 _fetch_grv_value/_load_series 对齐，取值前对 candidates 按日期排序，或改为 max(candidates, key=lambda x: x[0])。

### 🟡 [MEDIUM] BSS 气候学基准率与 Brier 均值样本口径不一致

- **单元/维度**: macro-ji 校准与验证 · 代码正确性
- **位置**: `macro-ji/tianji_verifier.py:459`
- **描述**: print_accuracy_report 中 bs_mean=所有 verified 记录 brier 均值（第 459 行，含地缘 human 确认与量化预测），而传给 _compute_bss 的 outcomes 只对含 target_direction/threshold/outcome_value 的记录构建（第 451-458 行）——地缘预测因 target_direction 为 NULL 被排除。于是气候学基准 bs_clim=p_bar*(1-p_bar) 的 p_bar 仅由量化子集估计，却用来评判含地缘预测的全体 bs_mean。两类基准率差异大时 BSS 被系统性高/低估，削弱'是否优于随机'结论可信度。
- **证据**: L451-458: for r in verified: 仅当 d and th is not None and av is not None 才 outcomes.append(...); L459: bs_mean=sum(briers)/len(briers)（briers 覆盖全部 verified）; L460: bss=_compute_bss(briers, outcomes or None)
- **建议**: 让 bs_mean 与 outcomes 基于同一记录集合（都限定可重建二值 outcome 的记录，或为地缘 human 确认也重建二值 outcome 纳入 p_bar），保证分子分母同源。

### 🟡 [MEDIUM] verify_geo_auto 被 cron 调度与 tianji_verifier 文档称'孤儿脚本从未被调度'矛盾，且 L2 关键词表两文件重复

- **单元/维度**: macro-ji 校准与验证 · 文档漂移
- **位置**: `macro-ji/tianji_verifier.py:45`
- **描述**: tianji_verifier.py 第 45-47 行文档称原 verify_geo_auto.py 从未进镜像/被调度，据此把 L2 判定逻辑与 L2_KEYWORDS 表整份复制进 tianji_verifier（第 53-75 行）。但 tianji_verify_cron.py（更晚，2026-08-24）第 29 行明确每日 09:30 cwd=/app 调度 verify_geo_auto.py——脚本既在镜像内也被调度，文档结论已过期。结果：同一份 L2_KEYWORDS（tianji_verifier L53-75 与 verify_geo_auto L37-59 逐字重复）由两条路径维护，改动需两处同步存在漂移隐患；同批 awaiting_human 的 L2 预测被两条路径重复判定（幂等使其不致损坏但重复处理）。
- **证据**: tianji_verifier.py L45-47: 原 verify_geo_auto.py...从未进天玑镜像/被调度; tianji_verify_cron.py L29: (None,9,30,[sys.executable,'verify_geo_auto.py']); L2_KEYWORDS 在两文件逐字重复
- **建议**: 确立单一 L2 判定实现（抽成共享模块被两处 import），删除复制表；修正 tianji_verifier 文档中'从未被调度'的过期论断，明确 verify_geo_auto 负责 L1+L2、tianji_verifier 仅兜底。

### 🟡 [MEDIUM] test_connection() 引用未定义的 max_tokens，连通性自检必崩

- **单元/维度**: macro-sim Agent 与 LLM 层 · 代码正确性
- **位置**: `core/llm_client.py:204`
- **描述**: test_connection() 内 client.chat.completions.create(..., max_tokens=max_tokens) 引用了名为 max_tokens 的变量，但该函数无此参数、模块级也无此常量（max_tokens 只是 call_llm 的形参）。执行 `python llm_client.py`（__main__ 调用 test_connection）会在首次 create 调用处抛 NameError，两个模型的连通性测试全部失败。这是用来验证 LLM 平台是否可达的诊断入口，等于该诊断工具本身是坏的。
- **证据**: L204: `temperature=0.4, max_tokens=max_tokens,` —— test_connection() 定义为无参函数，作用域内无 max_tokens。
- **建议**: 把第 204 行改为固定值（如 max_tokens=256）或在函数内定义该变量。

### 🟡 [MEDIUM] sovereign.py 重定义 _eval_trigger，遮蔽 base 的修复版（内置函数 bug 回归 + 丢失 missing_strategy）

- **单元/维度**: macro-sim Agent 与 LLM 层 · 代码正确性
- **位置**: `core/agents/sovereign.py:51`
- **描述**: sovereign.py 第 24 行 `from core.agents.base import ... _eval_trigger`（CHANGELOG 记为『改为从 base import（兼容导出）』），但第 51 行又定义了一个本地 _eval_trigger 覆盖了该导入。本地版是旧实现：不跳过内置函数名（abs/min/max…），即 CHANGELOG 明确记录已在 base 修复的『abs(x) 被当作变量替换成 0.0(x) → SyntaxWarning 恒 False』bug 在此仍然存在；且不支持 missing_strategy 参数，缺失变量一律 ctx.get(var,0.0)。当前 _decide_soul 在 base.py 中执行、用的是 base 版本，financial.py 也显式从 base import，故暂无直接触发；但任何 `from core.agents.sovereign import _eval_trigger` 都会拿到这个带 bug 的旧版本，使文档声称的『兼容导出』失效，是一个潜伏 landmine 且与文档意图矛盾。
- **证据**: sovereign.py:24 `from core.agents.base import MacroAgent, AgentParams, ActionDecision, _eval_trigger`；sovereign.py:51 `def _eval_trigger(trigger_str: str, ctx: dict) -> bool:`（无 missing_strategy、无 _BUILTIN_FUNCS 跳过逻辑，val=ctx.get(var,0.0)）。base.py:114 注释确认内置函数不跳过会导致恒 False。
- **建议**: 删除 sovereign.py:51-78 的本地 _eval_trigger 定义，保留第 24 行从 base 的 import 即可。

### 🟡 [MEDIUM] LLM 回退到 soul 时决策来源仍被标为 source="llm"（溯源/标签失真）

- **单元/维度**: macro-sim Agent 与 LLM 层 · 代码正确性
- **位置**: `core/agents/base.py:211`
- **描述**: decide_with_decision 中，只要 use_llm=True 且 Agent 有 _decide_llm，就无条件把结果封装为 source="llm"、faction="llm"、reason="LLM 决策"。但 LLMPilotMixin._decide_llm 在 TIANJI_LLM_PILOT!=1（开关未开）或调用异常时会直接返回 self._decide_soul(ctx).action，即实际来自 soul。结果是：ActionDecision 记录的 source/reason 声称是 LLM 决策，实际动作却来自 soul 派系或 soul fallback。这会污染天玑推理溯源存档与 backtest_eval 的 --engine llm 标签，使『LLM 引擎』的验证结果实际上混入了 soul 决策而无法察觉。
- **证据**: base.py:211-219 无条件 `source="llm"`；llm_pilot.py:53-56 `if os.environ.get("TIANJI_LLM_PILOT") != "1": a = self._decide_soul(ctx).action; ... return a`，L80-84 异常同样 `return self._decide_soul(ctx).action`。
- **建议**: 让 _decide_llm 返回来源标记（如返回 (action, actual_source)），或在 base 里依据 mixin 内部真实路径设置 source；至少在开关未开/异常回退时不要标为 llm。

### 🟡 [MEDIUM] use_llm 对未混入 LLMPilotMixin 的多数 Agent 被静默忽略，形成被误标为纯 LLM 的混合引擎运行

- **单元/维度**: macro-sim Agent 与 LLM 层 · 架构一致性
- **位置**: `core/agents/financial.py:162`
- **描述**: simulation.py 对所有 Agent 统一传入 self.use_llm。但只有 FedAgent、CommercialBankAgent、RetailAgent 与全部 Sovereign 类混入了 LLMPilotMixin（因而有 _decide_llm）。HedgeFundAgent、InstitutionAgent、LongTermCapitalAgent、USTreasuryAgent、ECBAgent、BOJAgent（financial.py）以及 MediaAgent（social.py）、EMCentralBankAgent、ChinaPBOCAgent（geopolitical.py）都未混入。base.decide_with_decision 里 `if use_llm and hasattr(self,"_decide_llm")` 对这些 Agent 为假，静默走 soul/规则，且无任何告警。于是一次 use_llm=True 的推演中，A3 对冲基金（激活率最高、每步近必激活）等关键 Agent 根本没走 LLM，却在 backtest_eval 里被整体标为 engine=llm，破坏 LLM vs 规则对照实验的有效性。
- **证据**: financial.py:162 `class HedgeFundAgent(MacroAgent):`（无 LLMPilotMixin），对比 financial.py:24 `class FedAgent(LLMPilotMixin, MacroAgent):`；base.py:211 `if use_llm and hasattr(self, "_decide_llm")`；simulation.py:582/595 `agent.decide_with_decision(ctx, self.use_llm)`。
- **建议**: 统一策略：要么让所有参与 Agent 都混入 LLMPilotMixin，要么在 use_llm=True 但 Agent 无 _decide_llm 时打印一次显式告警并在 trace/报告中标注实际引擎，避免混合引擎被当作纯 LLM。

### 🟡 [MEDIUM] LLM 调用失败/空返回/输出被截断统一坍缩为 HOLD，无法区分真实 HOLD 与调用故障

- **单元/维度**: macro-sim Agent 与 LLM 层 · 代码正确性
- **位置**: `core/llm_client.py:159`
- **描述**: call_llm 在重试耗尽后返回空字符串（不抛异常，仅 print），parse_action 对空串或无 `ACTION: xxx` 的文本一律返回 "HOLD"。因此 API 故障、限流、输出被 max_tokens 截断（_decide_llm 用 max_tokens=1024，call_llm 默认仅 256）都会静默变成『Agent 选择 HOLD』，与 LLM 真正判断 HOLD 无法区分。对推演结果的影响是系统性偏向 HOLD 且不可观测；若所用模型为 GLM-Z1 这类会先输出推理再给答案的模型，思考文本会挤占 token 预算使末尾的 ACTION 行被截断——这一点我未在对话中确证模型行为，属假设，但『故障与 HOLD 不可区分』本身是代码事实。
- **证据**: llm_client.py:172-173 失败仅 `print(...)` 后 return ""；parse_action L186 `return "HOLD"`；llm_pilot.py:76-78 `raw = call_llm(prompt, max_tokens=1024); action = parse_action(raw, self.VALID_ACTIONS)` 无失败区分。
- **建议**: call_llm 失败时抛出或返回带错误标记的哨兵值，让 _decide_llm 区分『调用失败→回退 soul』与『LLM 判定 HOLD』；parse_action 解析失败时也应可上报『unparseable』而非静默 HOLD；并对推理型模型提高/校验 max_tokens。

### 🟡 [MEDIUM] 架构治理与文档机器复杂度与「单人家用兴趣项目 + 未验证核心」严重不匹配（过度工程）

- **单元/维度**: 项目合理性与发展前景 · 项目合理性
- **位置**: `docs/arch_review_20260802.md · ADR-001/002/003 · STATUS.md · docs/ 目录整体`
- **描述**: 系统七星命名（北斗七星）里瑶光、天权、玉衡三者已被永久关闭或降级为文档/子函数——即命名体系本身制造了 3 个幽灵项目。围绕一个尚未验证预测有效性的核心，投入了企业级的迁移仪式、探针体系与多轮 AI 辩论治理，边际产出低。对单人维护而言，这些治理表面积本身就是持续的维护税，且分散了本应投向「跑通核心闭环」的精力。
- **证据**: STATUS 定位「个人内部宏观推演系统（非商业产品）」。arch_review 决策却由「六角色三轮辩论（19个 agent，1,242,218 tokens）」产出。SQLite→PG 迁移在 08-12（ADR-001 建库）→08-16（P6 删库）四天内完成，配套 pg_read 只读层 + verify_reads_e0c 双读校验台 + reconcile_synthesis + silent_failure_probe 32 项 + A0→…→E0-C→P1-P6 阶段序列。治理文档分散于 docs/reviews、docs/decisions、docs/calib、docs/discussion、docs/governance，两份子系统 OPEN-DECISIONS + 一份总索引，另有 arg-map/arg-round1 多轮辩论存档。评审自身对 6 个提案标记「过度设计 OE」。
- **建议**: 遵循评审已收敛的「不新增星、不新增容器、不新增独立进程」原则并进一步做减法：合并/归档冗余治理文档，用轻量 CHANGELOG + 单一 ADR 目录替代多份评审/辩论存档。把「是否值得再投入一项治理」的判据锚定到「它是否直接服务于闭环跑通」。

### 🟡 [MEDIUM] 战略方向基于未经核实的前提反复翻转（LLM 定位在数天内三次改向）

- **单元/维度**: 项目合理性与发展前景 · 项目合理性
- **位置**: `S:/docs/decisions/world-deduction/0012-math-mc-kernel-over-llm-agents.md · 0012a-blueprint · 0012b · docs/design_v2.md`
- **描述**: 关键定位决策（LLM 是叙事层还是决策玩家）先基于一个后来被自己证伪的成本前提作出，再在数天内被蓝图推翻，最终交给一个尚未执行的门控实验。核心参数（预测期 50→24 月）的变更原因无人记录。这反映决策常在未核实事实的情况下作出，导致方向反复、返工，是「先猜结论」而非「先查证」的模式。
- **证据**: ADR-0012 最初选项C「LLM 退居叙事层」，理由是「100 runs…上亿 token 级不可持续」；随后【08-25 勘误】：「MC 阶段配置的模型是 GLM-Z1-9B…实锤为免费模型…原「上亿 token 成本」论证错误作废」。STATUS 记载 blueprint v6「实际推翻其(ADR-0012)「LLM 退居叙事层」选项…以蓝图 v6 为准」，把 LLM 升为决策玩家；再以 0012b 门控实验裁决。design_v2 与 ADR-0012 附录还记「向后推演 50→24 个月…原因待考」。
- **建议**: 重大定位/参数决策前先做最小事实核验（如模型定价、单 run 实测），把结论建立在证据而非估算上；ADR-0012b 的门控实验是正确做法，应作为定位争议的统一裁决入口，在其出结果前不再翻转定位。补记 50→24 月缩水的真实原因或标注为待考。

### 🟡 [MEDIUM] 文档漂移系统化：权威设计文档与已删除架构矛盾，版本号在根文档间多态不一致

- **单元/维度**: 项目合理性与发展前景 · 项目合理性
- **位置**: `docs/tianji-design.md §3.1/§四 · docs/overview.md:3,29 · README.md:49 · AGENTS.md:14 · STATUS.md · kaiyang/ROADMAP.md:3`
- **描述**: 被标为「现役版」的天玑设计文档描述的是一个已被物理删除的存储架构，任何依此文档维护的人都会被误导。版本号在每份根文档都不同，各文档为此加了「本行仅导航不断言」的免责声明——这实际上是承认版本漂移已成慢性病。文档还跨 repo 内外两处目录，进一步增加迷路成本。对单人项目，这些是自我施加的维护负担，也直接削弱交接与开源可读性。
- **证据**: tianji-design.md（标注「v1.0 现役版」）§3.1 仍写核心存储为「共享 forecast_tracker.db（…三写者 WAL）」「非独立 verification.db」，§四数据流图以 forecast_tracker.db 为中心；但 ADR-003/README:56/AGENTS:24 明确「forecast_tracker.db 已删除（P6 08-16）…全系统 PG-only，data 目录出现任何 .db 复生=CRIT」。kaiyang 版本号：overview.md v1.10.8（第3行）/ v1.9.0（架构图）、README v1.11.11、AGENTS v1.11.34、STATUS v1.11.35、kaiyang/ROADMAP v1.11.27——多态并存。ADR 又分散在 repo 内 docs/decisions 与 repo 外 S:/docs/decisions/world-deduction（16 份）两处。
- **建议**: 把 tianji-design.md 更新为 PG-only 现状或降级为历史归档并显著标注；建立单一版本事实源（各 CHANGELOG/VERSION 为准），移除根文档里的散落版本号而非用免责声明兜底；统一 ADR 到单一目录，消除 repo 内外双份决策记录。

### 🟡 [MEDIUM] 外生事件注入层（ADR-0012a 交付物）完全未接线，事件从不进入仿真

- **单元/维度**: macro-sim 核心推演逻辑 · 架构一致性
- **位置**: `core/exogenous_events.py (ExogenousInjector / build_events_from_history)`
- **描述**: exogenous_events.py 声称是「蓝图 v3 阶段 2 交付物」，通过感知/动作掩码/参数覆盖三通道注入外生事件，并有「注入后 N 步无内生响应→告警」的防静默失效设计。但全仓检索显示 ExogenousInjector、build_events_from_history、.inject()、check_response() 只在该文件自身的 __main__ 块被引用，simulation.py 与 bifurcation.py 均未 import 或调用它。也就是说预测循环里外生事件通道是死代码，真实事件冲击从未进入 agent ctx。
- **证据**: `grep -rn ExogenousInjector|build_events_from_history|.inject(|check_response core/ run.py` 仅命中 exogenous_events.py:74/115（类定义与 __main__）。simulation.MacroSimModel.step 与 bifurcation.run_prediction 中无任何外生注入调用。
- **建议**: 要么在 run_prediction/step 中真正接入 ExogenousInjector（按月 inject + check_response 告警），要么在文档/ADR 中明确标注该层为未启用原型，避免「已交付」与实际未生效的漂移。

### 🟡 [MEDIUM] credit_spread 与 t10y2y 无均值回归/上下限，出血规则驱动无界单调漂移

- **单元/维度**: macro-sim 核心推演逻辑 · 代码正确性
- **位置**: `core/world_state.py:297-303 (apply_bleed_rules) 与 330-353 (apply_natural_decay)`
- **描述**: apply_natural_decay 对 sentiment/credit_tightening/liquidity/grv/grv_energy/vix 等都做了衰减或均值回归，但 credit_spread 和 t10y2y 完全不在其列。同时出血规则 3 在 bank_credit_tightening>0.5 时每步 credit_spread += 8.0（无 clamp），出血规则 4 在 em_capital_outflow>0.4 时每步 t10y2y -= 5.0（无 clamp）。这两个变量既被出血单向推动，又无任何回复力，24 步预测内可累积到 +192bp / -120bp 且无上界；grv_energy 出血亦注明「无上限截断」。credit_spread 又反馈进 fed/commercial_bank 的 ctx，可能与 A2 收紧决策形成正反馈。
- **证据**: apply_bleed_rules: `world.credit_spread += params["credit_spread_bleed_rate"]`（rate=8.0）、`world.t10y2y -= 5.0`，均无 min/max。apply_natural_decay 中无 credit_spread/t10y2y 项（对比 D4 fix 明确为其它变量补了均值回归）。
- **建议**: 为 credit_spread/t10y2y（及 grv_energy）补上限/均值回归，或给出血累积设封顶（如 vix 的 vix_bleed_max 那样），防止长时预测中这些外生量脱离合理区间并污染下游 agent 决策。

### 🟡 [MEDIUM] 预测期 dff（联邦基金利率）从不被更新，Fed 行动只累加 fed_rate_change 而不改变实际政策利率

- **单元/维度**: macro-sim 核心推演逻辑 · 代码正确性
- **位置**: `core/simulation.py:657-693 (_apply_delta) 与 world_state get_agent_context`
- **描述**: gm_resolve_rules 里 Fed 的 CUT/HIKE 只写 fed_rate_change（±25/50），_apply_delta 中 `self.world.fed_rate_change += val`（无缩放、无 clamp、从不重置）。而实际政策利率 world.dff 在整个预测循环中从不被任何 delta/bleed/decay 修改（全仓检索 dff 无写入点，仅从历史注入读取）。结果：自由预测期 dff 全程冻结，Fed 连续降息只让 fed_rate_change 单调累积（24 步可达数百 bp），fed ctx 里的 dff 却纹丝不动。fed 自身决策规则若依赖 dff 水平，将看不到自己此前动作的效果。
- **证据**: _apply_delta 分支：`elif key == "fed_rate_change": self.world.fed_rate_change += val`；无 `dff` 分支。`grep world.dff=|.dff += core/` 无预测期写入，仅 world_state 从 FRED/历史行读取初值。
- **建议**: 确认设计意图：若 dff 应随 Fed 行动变化，应在 _apply_delta 中把 fed_rate_change 折算进 dff（并对 fed_rate_change 设界或按月清零表示单月增量）；若 fed_rate_change 才是唯一政策信号，应在文档中说明 dff 在预测期为常量，避免 agent ctx 中 dff 语义误导。

### 🟡 [MEDIUM] overview.md 称仿真为「12-Agent」，实际 agents.yaml 已是 20 个 agent

- **单元/维度**: 文档与现实漂移 · 文档漂移
- **位置**: `docs/overview.md:12`
- **描述**: docs/overview.md 第一节写「GRV 告警时自动触发 12-Agent Monte Carlo 仿真」，但 macro-sim/config/agents.yaml 实测 20 个 id（A1–A13 共 13 宏观 + S1_usa…S7_korea 共 7 主权 = 20）。STATUS.md 专门有一节记录 12→17→20 的演进，说明 overview 停留在最早的 12-Agent 快照。此为未对冲的事实性错误，直接误导读者对系统规模的理解。
- **证据**: overview.md:12「12-Agent Monte Carlo 仿真」；agents.yaml grep -c id = 20；STATUS.md:241「关于「Agent 数」的口径（08-18 更新：17 → 20）」「A1–A13（13 宏观）+ S1_usa…S7_korea（7 主权）= 20」
- **建议**: 将 overview.md 的「12-Agent」改为「20-Agent（A1–A13 + S1–S7）」或改为不含数字并指向 agents.yaml，与 STATUS.md 的 20 口径对齐。

### 🟡 [MEDIUM] overview.md 版本号自相矛盾且全线过时

- **单元/维度**: 文档与现实漂移 · 文档漂移
- **位置**: `docs/overview.md:3 与架构图注释`
- **描述**: overview.md 顶部 header 写 macro-scan v3.8.17 / macro-sim v2.0.40 / kaiyang v1.10.8，但同一文件下方架构图注释写 macro-scan v3.8.15 / macro-sim v2.0.24 / kaiyang v1.9.0——同一文档内部互相矛盾（kaiyang header v1.10.8 vs 图 v1.9.0）。二者又都远落后于实际 VERSION：kaiyang=1.11.35 / macro-sim=v2.0.50 / macro-scan=3.8.24。header 的「不断言版本」对冲无法解释内部两处版本互不一致。
- **证据**: overview.md:3「macro-scan v3.8.17 · macro-sim v2.0.40 · kaiyang v1.10.8」；架构图「macro-scan ... v3.8.15」「macro-sim ... v2.0.24」「kaiyang v1.9.0」；VERSION 文件 kaiyang 1.11.35 / macro-sim v2.0.50 / macro-scan 3.8.24
- **建议**: 删除架构图内嵌版本号（保留纯架构），或由脚本从 VERSION 文件注入；至少消除 header 与图之间的版本冲突。

### 🟡 [MEDIUM] 构建标签与运行标签不一致：--build 构建 v7 但 compose 运行 v8，部署到旧镜像

- **单元/维度**: infra + sql + 部署 · 代码正确性
- **位置**: `macro-scan/deploy.sh:70 + macro-scan/docker-compose.yml:3 + macro-scan/docker-compose.example.yml:6`
- **描述**: macro-scan/deploy.sh 的 _build 从模板文件推导镜像标签（grep docker-compose.example.yml 得 macro-scan:v7），据此构建 v7 镜像；但真实运行的 docker-compose.yml 声明 image: macro-scan:v8，随后 docker compose up -d 使用 v8。结果刚构建的 v7 不会被启用，compose 用旧 v8 镜像（或 v8 缺失时报错）。运维执行 --build 会误以为部署了新代码，实际跑旧镜像。
- **证据**: deploy.sh:70 IMAGE_TAG=$(grep image: docker-compose.example.yml | grep -o macro-scan:v[0-9]* | head -1)；example.yml:6 image: macro-scan:v7；docker-compose.yml:3 image: macro-scan:v8
- **建议**: 从真实 docker-compose.yml 而非 example 模板提取标签，或在 compose 加 build: 段用 docker compose build 保证构建与运行同标签，并保持两处标签同步。

### 🟡 [MEDIUM] 备份脚本在 pg_dump 失败时留下损坏/零字节 dump，且无完整性校验

- **单元/维度**: infra + sql + 部署 · 代码正确性
- **位置**: `infra/pg/backup-pg.sh:21-24`
- **描述**: 第21行 docker exec ... pg_dump -Fc ... > $OUT：shell 在运行 pg_dump 前已创建/截断 $OUT。若 pg_dump 中途失败，磁盘残留带当日时间戳、看似正常的损坏 custom-format dump。set -euo pipefail 会随后中止（好处是不执行第24行 14 天清理，历史好备份得以保留），但损坏文件成为最新一次备份，日后 pg_restore 会失败。脚本对 dump 无任何完整性校验（如 pg_restore --list 或非零大小检查）。成功 marker 只在成功时写，freshness 探针能抓完全失败，但抓不到文件存在而内容损坏的情形。
- **证据**: backup-pg.sh:21 docker exec PG_CONTAINER pg_dump -Fc -U worldsim_admin -h localhost -p 5432 -d worldsim > $OUT（无后续 pg_restore --list 校验）
- **建议**: 先 dump 到临时文件，成功且通过 pg_restore --list 校验后再原子重命名为最终名；失败时删除临时文件，避免损坏 dump 冒充最新备份。

### 🟡 [MEDIUM] deploy-pg.sh 用 Python repr 把口令拼进 SQL 字面量，特殊字符会出错且被 || true 静默吞掉

- **单元/维度**: infra + sql + 部署 · 安全配置
- **位置**: `infra/pg/deploy-pg.sh:34-54`
- **描述**: 角色创建把口令用 Python f-string 的 app!r / ro!r 直接拼进 CREATE ROLE ... PASSWORD。Python repr 的转义与 PostgreSQL 字符串字面量不一致：口令含单引号时 Python 可能改用双引号包裹，而 SQL 双引号是标识符不是字符串，导致语法错误；口令含反斜杠时 PG16 默认 standard_conforming_strings=on 不当转义，口令值被改变或语法破坏。更严重的是整条 python | psql 以 || true 收尾（第34行末），任何失败含上述语法错误都被吞掉，脚本照报成功，但 worldsim_app/worldsim_ro 可能没建成或口令不对，应用随后连不上库。
- **证据**: deploy-pg.sh:39 CREATE ROLE worldsim_app LOGIN PASSWORD {app!r}；deploy-pg.sh:34 python3 - <<PY | docker exec -i PG_CONTAINER psql ... -f - || true
- **建议**: 改用参数化/安全转义设置口令（psql 变量 :'var'、quote_literal，或 ALTER ROLE 配合 \set），去掉角色创建这步的 || true 让失败可见并中止部署。

### 🟡 [MEDIUM] deploy-pg.sh 宣称幂等可重跑，但建库/角色/授权/collation 仅在容器首次创建时执行

- **单元/维度**: infra + sql + 部署 · 架构一致性
- **位置**: `infra/pg/deploy-pg.sh:16-55`
- **描述**: 脚本头注释写明幂等可安全重跑，但 REFRESH COLLATION、CREATE DATABASE、CREATE ROLE、REVOKE/GRANT、ALTER DEFAULT PRIVILEGES 全部包在 if 容器不存在 分支内（16-55行）。容器已存在时重跑只执行 pg_hba ACL 追加与 network connect，不会重新应用角色与授权。若授权块日后修改、或角色权限被手动改动，重跑无法修复，与幂等可重跑承诺相悖。只有 pg_hba 段是真幂等。
- **证据**: deploy-pg.sh:2 注释 幂等，可安全重跑；deploy-pg.sh:16 if ! docker ps -a --format {{.Names}} | grep -qx PG_CONTAINER; then（16-55 行角色/授权/建库均在此 if 内）
- **建议**: 将角色、GRANT、ALTER DEFAULT PRIVILEGES 等幂等 DDL 移出容器创建分支，每次运行都执行（这些语句本就可重复执行），以兑现幂等承诺。

### 🟡 [MEDIUM] entrypoint 后台服务无监督：web/control/ntfy 崩溃后容器仍存活但服务已死

- **单元/维度**: infra + sql + 部署 · 代码正确性
- **位置**: `macro-scan/entrypoint.sh:11-41`
- **描述**: entrypoint 用 & 后台启动 ntfy_listener(13行)、web_server(18行)、control_server(22行)，最后只 wait SCHED_PID 等 scheduler(41行)。set -e 对后台任务不生效。若 web_server 或 control_server 崩溃，容器因 scheduler 仍在而保持 running（restart: unless-stopped 只在容器退出时重启），于是 8899/8900 已死但对外表现为容器健康，无自动重启，compose 也未给 macro-scan 服务加 healthcheck。
- **证据**: entrypoint.sh:18 python3 web_server.py ... &；:22 python3 control_server.py ... &；:41 wait $SCHED_PID（仅等 scheduler）
- **建议**: 为 macro-scan 服务加 compose healthcheck 探测 8899/8900，或用轻量进程管理器（supervisord/s6）监督后台进程并在崩溃时重启或退出容器触发 restart 策略。

### 🟡 [MEDIUM] 控制面 API(8900)与 Web UI(8899)绑定 0.0.0.0，暴露到整个局域网

- **单元/维度**: infra + sql + 部署 · 安全配置
- **位置**: `macro-scan/docker-compose.yml:8-10, 28-29`
- **描述**: macro-scan 端口映射 8899:8899 与 8900:8900 未指定绑定地址，默认绑宿主 0.0.0.0，整个局域网可访问控制 API(8900)与 Web UI。对比 PG 明确用 -p 127.0.0.1:5434:5432 只绑本机，控制面反而全网暴露。8900 仅靠 CONTROL_TOKEN 保护，一旦 token 弱或泄露即可被 LAN 内任意主机调用控制接口。
- **证据**: docker-compose.yml:9-10 - 8899:8899 / - 8900:8900；对照 deploy-pg.sh:21 -p 127.0.0.1:5434:5432
- **建议**: 若控制/Web 面板仅供本机或反代访问，改为 127.0.0.1:8900:8900；确需 LAN 访问则确保 CONTROL_TOKEN 为强随机并加 TLS/反代鉴权。

### 🟡 [MEDIUM] 新闻契约三方漂移：文档写 news_export.json/items，实际产出 articles、前端读 news_all.json

- **单元/维度**: 跨模块架构与数据契约一致性 · 文档漂移
- **位置**: `kaiyang/docs/DATA_CONTRACT.md §1/§2.2 vs macro-scan/核心代码/news_exporter.py:92,96,133,136 vs kaiyang/src/components/NewsPanel.tsx:81`
- **描述**: DATA_CONTRACT §2.2 将 news_export.json 定义为 {schema_version, updated, items[]}，§1 注册表也只登记 news→news_export.json。但真实产出方 news_exporter.py 写的是 _schema_version + articles[]（两处 export_news_for_sim/export_all_news 均如此）；且开阳新闻面板 NewsPanel 实际 useFeed('newsAll') 读的是 news_all.json——该 feed 根本不在 DATA_CONTRACT §1 注册表内。契约声称自己是'权威标准'(§3.5)，却与三方真实实现都不一致。
- **证据**: news_exporter.py:92 "_schema_version":"1.0" / :96 "articles":articles；NewsPanel.tsx:81 useFeed<NewsItem[]>('newsAll')；dataSources.ts:105-111 newsAll→news_all.json；DATA_CONTRACT §2.2 表列 schema_version✅/items✅，§1 仅有 news→news_export.json。运行不崩因 NewsPanel:85 newsItemsOf 容错兼容 array/{articles}/{items}。
- **建议**: 更新 DATA_CONTRACT：把 news_all.json 补进 §1 注册表并新增字段小节；在 §2.2 注明真实键为 _schema_version+articles（或统一改产出方为 items）；明确 news_export.json(信号流,SignalStreamPanel) 与 news_all.json(新闻面板) 双轨用途。

### 🟡 [MEDIUM] schema_version 键名双轨制（_schema_version vs schema_version）削弱版本护栏

- **单元/维度**: 跨模块架构与数据契约一致性 · 架构一致性
- **位置**: `macro-scan/核心代码/geo_risk_vector.py:843 vs macro-scan/核心代码/tianxuan_grv_export.py:92,107 vs kaiyang/src/hooks/useFeed.ts:48`
- **描述**: 同一系统内 feed 版本键存在两种写法：GRV、新闻、六类风险信号产出方用带下划线的 _schema_version；而 tianxuan_grv/tianji_summary/fci 等用不带下划线的 schema_version。契约 §3.4 承诺'breaking change 必须 bump schema_version，读取层比对并告警'，但因键名不统一，消费侧只能靠 obj.schema_version ?? obj._schema_version 两头兼容来兜底。一旦某产出方 bump 了'另一种大小写/前缀'的键，护栏可能静默失效，无法达到契约承诺的破坏性变更告警效果。
- **证据**: geo_risk_vector.py:843 "_schema_version":"1.0"；tianxuan_grv_export.py:92/107 "schema_version":SCHEMA_VERSION；useFeed.ts:48 const sv = obj.schema_version ?? obj._schema_version；macro-sim world_state.py:553 grv.get("_schema_version") / :645 export.get("_schema_version")。
- **建议**: 统一全系统 feed 版本键为单一写法（建议 schema_version），或在 DATA_CONTRACT 明文规定两种前缀等价并要求读取层双检——当前 §2.1/§2.2 表只写了 schema_version，与真实产出的 _schema_version 不符，应至少在契约中把这条'双轨等价'规则写死。

### 🟡 [MEDIUM] sdrAdapter / airTrafficAdapter 用 typeof 而非 Number.isFinite 校验坐标，NaN 可穿透生成 (NaN,NaN) 点

- **单元/维度**: kaiyang 前端逻辑 · 代码正确性
- **位置**: `kaiyang/src/lib/sdrAdapter.ts:26-30；kaiyang/src/lib/airTrafficAdapter.ts:40-44`
- **描述**: 这两个适配器的坐标兜底判断是 `typeof r.lat !== 'number' || ...` 加范围比较。JS 中 `typeof NaN === 'number'` 为真，且 `NaN < -90`、`NaN > 90` 等所有比较均为 false，因此 lat/lng 为 NaN 的记录不会被 `continue` 跳过，会生成一个 lat/lng=NaN 的 RiskPoint。这违反了代码库其它所有适配器坚持的 K4「坐标必须是有限数」红线——thermalAdapter.ts:44-49、spaceAdapter.ts:26-30、healthAdapter.ts:62-66、mapData.ts:103、nuclearData.ts:80-84、newsGeoAdapter.ts:66-71、strategicSites.ts:170-171 全部显式用 `Number.isFinite`。NaN 坐标传入 globe.gl / SVG 投影会产生不可预期的渲染（点消失或投影异常）。注释虽称『后端已校验，双保险』，但双保险本身不完整，且与 K4 约定不一致。
- **证据**: sdrAdapter.ts:26 `typeof r.lat !== 'number' || typeof r.lon !== 'number' ||` 对比 thermalAdapter.ts:45 `!Number.isFinite(h.lat) || !Number.isFinite(h.lng) ||`
- **建议**: 将两处判断改为与其它适配器一致的 `!Number.isFinite(x)` 前置守卫，例如 `if (!Number.isFinite(r.lat) || !Number.isFinite(r.lon) || r.lat < -90 || ...) continue;`

### ⚪ [LOW] vite 配置文件实际未被类型检查（tsconfig 无 references）

- **单元/维度**: kaiyang 构建/部署/配置 · 项目合理性
- **位置**: `kaiyang/tsconfig.json:1-25, kaiyang/tsconfig.node.json:12, kaiyang/package.json:9`
- **描述**: build 脚本为 `tsc --noEmit && vite build`，tsc 使用根 tsconfig.json，而后者 include 仅为 ["src"] 且没有 `references` 指向 tsconfig.node.json。tsconfig.node.json（include: ["vite.config.ts"]）因此从不会被 tsc 调用，vite.config.ts / vite.config.standalone.ts / inject-standalone.mjs 都不在任何类型检查范围内。构建期 TS 校验漏掉了构建配置本身。
- **证据**: tsconfig.json 无 references（grep -c references = 0），include:["src"]；tsconfig.node.json:12 include:["vite.config.ts"]；package.json:9 build 命令。
- **建议**: 在 tsconfig.json 增加 `"references": [{ "path": "./tsconfig.node.json" }]`，并把 vite.config.standalone.ts 一并纳入 tsconfig.node.json 的 include。属健壮性改进，非阻断。

### ⚪ [LOW] standalone 单文件构建缺少 npm 脚本编排

- **单元/维度**: kaiyang 构建/部署/配置 · 项目合理性
- **位置**: `kaiyang/package.json:7-13, kaiyang/inject-standalone.mjs`
- **描述**: package.json scripts 仅含 dev/build/preview/test，不包含 standalone 构建。产出可分发单文件需手动依次执行 `vite build --config vite.config.standalone.ts` 再 `node inject-standalone.mjs`（且 inject 脚本依赖 process.cwd() 下已存在 dist-standalone），此顺序未在脚本或文档中固化，易出错或漏步。
- **证据**: package.json scripts 块仅 dev/build/preview/test/test:watch；inject-standalone.mjs:10-11 依赖 `process.cwd()`/`dist-standalone` 作为输入。
- **建议**: 新增如 `"build:standalone": "vite build --config vite.config.standalone.ts && node inject-standalone.mjs"` 的脚本，保证步骤顺序与工作目录约定被固化。

### ⚪ [LOW] PG 模块级连接缓存被 finally 中的 close+invalidate 完全抵消，report_path 为死参数

- **单元/维度**: macro-sim 输出/持久化/治理 · 架构一致性
- **位置**: `macro-sim/core/../run.py:688-705,898-900,719 (_pg_conn / _archive_to_tianji)`
- **描述**: run.py 维护了模块级缓存连接 _PG_CONN 及 _pg_connect_with_retry/_invalidate_pg_conn 一整套『缓存+丢失自动重连』机制。但 _archive_to_tianji 的 finally 无条件执行 conn.close() + _invalidate_pg_conn()，因此每次存档结束都会关闭并清空缓存——缓存跨调用从不复用，重连自愈逻辑也永远从零新建。机制存在但实际收益为零，属架构冗余/误导（后续维护者可能以为连接被复用）。另：_archive_to_tianji 形参 report_path 在函数体内从未被引用，是死参数。均非功能性 bug，但增加认知负担。
- **证据**: finally: conn.close(); _invalidate_pg_conn()  # 每次都关+清缓存；_pg_conn 注释『模块级缓存，连接丢失自动重连』；_archive_to_tianji(..., report_path) 函数体无 report_path 引用
- **建议**: 二选一：(a) 若要真复用连接，成功路径不要在 finally 关闭（仅异常路径 rollback+invalidate）；(b) 若每次都短连接，则删除模块级缓存机制改为普通 connect/close。并移除未使用的 report_path 形参。

### ⚪ [LOW] readable 兜底模板对空/None GRV 未防御会抛异常，破坏『永远有产出』；_call 含死代码

- **单元/维度**: macro-sim 输出/持久化/治理 · 代码正确性
- **位置**: `macro-sim/core/readable_report.py:176-177,137-141 (_fallback_template / _call)`
- **描述**: _fallback_template 计算 trend = '上升' if g1 > g0 else '下降'，其中 g0/g1 来自 hist[0/-1].get('grv')。若任一快照缺 grv（None），Python3 中 None > None 直接抛 TypeError。该函数是 LLM 失败后的最后兜底，本应保证输出，却可能因数据缺字段而崩溃，使 generate_readable 抛出未捕获异常、零产出。另 _call 中 line 137-141 的 now/t0_log/now2 计算后从未使用（waiting 日志逻辑残缺），属死代码，易误导。
- **证据**: g0, g1 = hist[0].get("grv"), hist[-1].get("grv"); trend = "上升" if g1 > g0 else "下降"（g0/g1 可能为 None）；_call: now = _t.time(); ... t0_log = now; now2 = _t.time()（now2/t0_log 未被使用）
- **建议**: _fallback_template 对 g0/g1 做 None 兜底（如 (g0 or 0)）或缺值时给出占位；清理 _call 中未使用的 now2/t0_log 计时残留。

### ⚪ [LOW] 控制 API token 使用非常量时间比较，且模块 docstring 与 fail-closed 行为不符

- **单元/维度**: 安全与密钥专项 · 安全配置
- **位置**: `macro-scan/核心代码/control_server.py:86（比较）与:16（docstring）`
- **描述**: _check_token 用 `auth[7:] != CONTROL_TOKEN` 做普通字符串比较，非 hmac.compare_digest 常量时间比较，理论上存在计时侧信道（对局域网内部控制 API 实际风险很低）。另外模块开头 docstring（第16行）仍写"未设置则跳过鉴权"，而实际代码（79-84 行）已改为 fail-closed（未配置 token 直接 503 拒绝），属文档漂移——真实行为是安全的，但注释会误导读者以为存在 fail-open。
- **证据**: control_server.py:86 `if not auth.startswith("Bearer ") or auth[7:] != CONTROL_TOKEN:`；:16 `鉴权：Bearer Token（CONTROL_TOKEN 环境变量，未设置则跳过鉴权）`；:84 `raise HTTPException(status_code=503, detail="CONTROL_TOKEN 未配置，控制 API 已禁用（fail-closed）")`
- **建议**: 用 hmac.compare_digest 做 token 比较；更新第16行 docstring 使其与 fail-closed 实现一致。

### ⚪ [LOW] eval() 对配置派生的触发表达式求值（受控输入，已标注技术债）

- **单元/维度**: 安全与密钥专项 · 安全配置
- **位置**: `macro-sim/core/agents/base.py:128,131,137,144,146；macro-sim/core/agents/sovereign.py:76`
- **描述**: _eval_trigger 用 Python eval() 对触发表达式字符串求值。求值前会用正则把所有标识符替换为浮点数值或 _MISSING_ 占位（非数值/未知变量→NameError→捕获返回 False），且 trigger_str 来源是受控的 soul YAML 配置而非网络/LLM/外部输入，故当前注入面很小。但 eval 本身对含函数调用的表达式仍会执行，若未来 soul 配置可被外部影响即构成 RCE。项目已在多处文档标注为技术债（a-class-sovereign-activation.md B4：后续换 AST 解析）。
- **证据**: base.py:146 `return bool(eval(expr))  # noqa: S307 — 已限制为数值比较，无注入风险`；a-class-sovereign-activation.md:250 `B4 | _eval_trigger eval() 未跳过 True/False/None | ... | 标注技术债，后续 AST 解析`
- **建议**: 按已规划的方向用 AST 解析（ast.parse + 白名单节点）或简单表达式求值器替换 eval，彻底消除 RCE 面；在此之前确保 soul YAML 仅来自可信来源。

### ⚪ [LOW] build_report 在有实际 GDP 值但无 gdp_p50 预测时格式化 None 崩溃

- **单元/维度**: macro-ji 校准与验证 · 代码正确性
- **位置**: `macro-ji/verify_predictions.py:289`
- **描述**: 美国分支 误差:{acc.get('gdp_error'):+.2f}ppt 在 a.get('gdp_growth') is not None 条件下打印，但 accuracy['gdp_error'] 仅在 pred.get('gdp_p50') is not None 时写入（第 143-145 行）。若记录有实际 GDP 却缺 gdp_p50，acc 无 gdp_error，f'{None:+.2f}' 抛 TypeError 使整份 build_report/run_verification 崩溃。中国分支用默认值 0（第 302 行）规避，美国分支未同样保护。
- **证据**: L143-145: p=pred.get('gdp_p50'); if p is not None: accuracy['gdp_error']=round(err,3); L287-289: if a.get('gdp_growth') is not None: lines.append(...误差:{acc.get('gdp_error'):+.2f}ppt)
- **建议**: 美国分支同样使用默认值或前置判空，如 acc.get('gdp_error') or 0，或仅在 gdp_error 非 None 时打印误差片段。

### ⚪ [LOW] tianji_db 重复导入 timezone

- **单元/维度**: macro-ji 校准与验证 · 代码正确性
- **位置**: `macro-ji/tianji_db.py:13`
- **描述**: from datetime import datetime, timezone, timezone 重复导入 timezone，功能无害但属明显笔误，暗示该行未经审阅。
- **证据**: L13: from datetime import datetime, timezone, timezone
- **建议**: 改为 from datetime import datetime, timezone。

### ⚪ [LOW] 动态客户端缓存以 api_key 前 8 字符为键，密钥轮换或前缀相同会命中过期/错误客户端

- **单元/维度**: macro-sim Agent 与 LLM 层 · 安全配置
- **位置**: `core/llm_client.py:115`
- **描述**: _get_dynamic_client 以 `base_url + "|" + api_key[:8]` 作为缓存键，且缓存永不失效。硅基流动等平台的 key 形如 sk-xxxx，前 8 字符可用熵很低；同一 base_url 下若运营在开阳控制台轮换 api_key 而新旧 key 前 8 字符相同，会命中旧缓存客户端、继续用旧 key 调用（认证失败或用错账户）；反之两把不同 key 前缀相同也会串用。属健壮性/凭据管理隐患，非直接泄露。
- **证据**: llm_client.py:115 `key = base_url + "|" + api_key[:8]`；L116-118 命中则直接复用，无失效逻辑。
- **建议**: 缓存键改用完整 api_key 的哈希（如 sha256 前若干位）而非明文前缀；或在检测到配置里 api_key 变化时清理对应缓存条目。

### ⚪ [LOW] LLM 调用无显式超时，依赖 SDK 默认（约 600s），Monte Carlo 大量调用下易长时间阻塞

- **单元/维度**: macro-sim Agent 与 LLM 层 · 代码正确性
- **位置**: `core/llm_client.py:161`
- **描述**: 创建 OpenAI 客户端（_get_sf_client/_get_dynamic_client）与 chat.completions.create 均未设置 timeout，依赖 openai SDK 默认超时（约 600s）。在免费/限流的硅基流动端点上，单次挂起最长可达约 10 分钟，叠加 max_retries=2 与 Monte Carlo 每轮对多个 Agent 逐一调用，慢/挂起端点会显著拖慢或卡住整轮推演。
- **证据**: llm_client.py:84-87 与 L117 构造客户端无 timeout；L161-166 create 无 timeout 参数。
- **建议**: 在 OpenAI(...) 或 create(...) 上设置明确的 timeout（例如 15-30s），与 _throttle 节流配合，超时计入重试。

### ⚪ [LOW] 存在两套并行的 Board 单例，sovereign.BOARD 的重置函数 board_clear() 无任何调用方

- **单元/维度**: macro-sim Agent 与 LLM 层 · 架构一致性
- **位置**: `core/agents/sovereign.py:45`
- **描述**: 关系矩阵存在两套模块级单例：sovereign.py 的 BOARD（board_get/board_set/board_clear）与 board_baseline.py 的 _baseline/_board_cur（derive_board_baseline/board_push/board_decay_step）。simulation.py 实际使用的是 board_baseline（board_decay_step），bifurcation.py 调用 derive_board_baseline 做重置；而 sovereign.BOARD 的重置函数 board_clear() 在整个 core 下无任何调用方。这构成职责重叠与死代码：若未来有代码写入 sovereign.BOARD，因从不 board_clear，跨仿真（顺序或并行 MC）会残留状态。当前未见写入方，故仅为架构/维护隐患。
- **证据**: grep 结果：`board_clear` 仅定义于 sovereign.py:45，core 下无调用；simulation.py:631-632 仅调用 board_decay_step（board_baseline 那套）。
- **建议**: 明确保留一套 Board 实现，删除或合并另一套；若 sovereign.BOARD 仍需保留，则在每次仿真开始处显式调用 board_clear()。

### ⚪ [LOW] 分叉检测结果 bifurcation_step 仅打印、不参与路径构建，聚类纯粹基于终值 kmeans

- **单元/维度**: macro-sim 核心推演逻辑 · 架构一致性
- **位置**: `core/bifurcation.py:602-604 与 _detect_bifurcation:260`
- **描述**: 模块名为 bifurcation（路径分叉），文档描述「每步检测 grv/sentiment 分布双峰→分叉点」。但 _detect_bifurcation 的返回值 bifurcation_step 只在 603-604 行被 print，之后从不被使用：路径切分完全由 _cluster_runs 对终态 sentiment/GRV 做一维自然断点聚类完成。即「检测到的分叉时点」既不参与聚类，也不进入 PathResult/报告。
- **证据**: bifurcation.py:602 `bifurcation_step = _detect_bifurcation(grv_by_step)`；紧接 if 仅 print；后续 clusters = _cluster_runs(primary_vals, ...) 与 bifurcation_step 无关。
- **建议**: 若分叉时点是产品语义的一部分，应把它写入 PathResult（如分叉发生月）并驱动或校验聚类；否则移除以免误导读者以为聚类基于双峰检测。

### ⚪ [LOW] run_prediction 在 n_runs<2 时于 statistics.stdev 与 _cluster_runs 处崩溃（无小样本守卫）

- **单元/维度**: macro-sim 核心推演逻辑 · 代码正确性
- **位置**: `core/bifurcation.py:611-612 与 _cluster_runs:300-303`
- **描述**: run_prediction 用 statistics.stdev(final_sent_values)/stdev(final_grv_values) 计算分散度；stdev 要求至少 2 个数据点，n_runs=1 时抛 StatisticsError。同样 _cluster_runs 在 n=1 时 diffs 为空，`diffs.index(max(diffs))` 会因 max([]) 抛 ValueError。默认 n_runs=100 时不触发，但函数签名允许任意 n_runs，作为可复用入口缺少小样本保护。
- **证据**: bifurcation.py:611 `sent_std = statistics.stdev(final_sent_values)`；_cluster_runs:300 `diffs = [...]`（n=1 时为空）→ 302 `diffs.index(max(diffs))`。
- **建议**: 在 run_prediction 入口对 n_runs<2 做守卫（直接返回单路径或抛清晰错误），并在 _cluster_runs 对空 diffs 早退。

### ⚪ [LOW] 正反馈环对 A10 activation_prob 的回落下限(0.7)低于其初始值(0.9)，形成隐性下行棘轮

- **单元/维度**: macro-sim 核心推演逻辑 · 代码正确性
- **位置**: `core/simulation.py:461-472 与 config/agents.yaml A6/A10`
- **描述**: 情绪回升分支中 A6 activation_prob 回落下限设为 0.8、A10 设为 0.7，均为硬编码 magic number。A6 初始值恰为 0.80（对称），但 A10 初始值是 0.90——一旦经历过任一次 sentiment<-0.5 的负向阶段再回升，A10 的 activation_prob 会逐步回落并停在 0.7，永久低于其初始 0.9（在单个 run 内不可恢复）。这使散户在经历一次恐慌后活跃度系统性下降，与「散户即时、最易被驱动」的设定相悖。
- **证据**: simulation.py:472 `agents["A10"].activation_prob = max(0.7, agents["A10"].activation_prob - 0.1)`；agents.yaml A10 `activation_prob: 0.90`、A6 `activation_prob: 0.80`。
- **建议**: 把回落下限改为各 agent 的初始 activation_prob（构造时记录 base 值），或至少让 A10 下限对齐其配置值 0.9，避免恐慌事件后活跃度不可逆下滑造成的方向偏置。

### ⚪ [LOW] README/macro-ji 版本号过时（macro-ji README v1.0.0 vs CHANGELOG v1.0.3）

- **单元/维度**: 文档与现实漂移 · 文档漂移
- **位置**: `README.md 子系统说明各行；macro-ji/README.md`
- **描述**: 根 README 写 kaiyang v1.11.11 / macro-sim v2.0.40 / macro-scan v3.8.17 / macro-ji v1.0.0，实际为 1.11.35 / v2.0.50 / 3.8.24；macro-ji 标 v1.0.0（as-of 2026-08-06）但 macro-ji/CHANGELOG.md 已到 v1.0.3（2026-08-24）。README 各行带「本行仅导航不断言」对冲故降级为 low，但 macro-ji 无 VERSION 文件使版本口径分散。
- **证据**: README.md「kaiyang v1.11.11」「macro-sim v2.0.40」「macro-ji v1.0.0（as-of 2026-08-06）」；macro-ji/CHANGELOG.md 顶部「v1.0.3 — 2026-08-24」；macro-ji 目录无 VERSION 文件
- **建议**: 将 README 版本行简化为纯链接（去具体号）或建立部署刷新脚本；macro-ji 建议补 VERSION 文件与其它模块对齐。

### ⚪ [LOW] README 称 SQLite forecast 死文件「待 P6 删除」，实则 P6 已于 08-14 执行

- **单元/维度**: 文档与现实漂移 · 文档漂移
- **位置**: `README.md macro-ji 子系统说明段`
- **描述**: 根 README 写「不再共享 SQLite forecast_tracker.db（死文件待 P6 删除）」，表述为未完成的待办；但 STATUS.md 记载「P6 删 4 SQLite 已于 08-14 08:39 执行（commit 1ba002a，删后观察无复生）」。README 把已完成的清理仍描述为待办，属陈旧的待办残留漂移。
- **证据**: README.md「不再共享 SQLite forecast_tracker.db（死文件待 P6 删除）」；STATUS.md「P6 删 4 SQLite 已于 08-14 08:39 执行（commit 1ba002a）」
- **建议**: 将 README 该句改为「SQLite forecast_tracker.db 已于 P6（08-14）删除」，与 STATUS 对齐。

### ⚪ [LOW] overview.md 文档导航指向根 ROADMAP.md，但已迁移至 docs/roadmap.md（断链）

- **单元/维度**: 文档与现实漂移 · 文档漂移
- **位置**: `docs/overview.md:79`
- **描述**: overview.md 第四节导航表「时间门控路线图 | ROADMAP.md」。从 docs/overview.md 相对解析指向 docs/ROADMAP.md，实际不存在；根目录也无 ROADMAP.md。路线图已迁至 docs/roadmap.md（roadmap.md 首行自述已从根迁来，README 也引用 docs/roadmap.md）。这是过时的断链引用。
- **证据**: overview.md:79「时间门控路线图 | ROADMAP.md」；ls 仅 docs/roadmap.md 存在、无 ROADMAP.md；docs/roadmap.md:1「2026-08-12 从根迁至 docs/roadmap.md」
- **建议**: 把 overview.md 导航表的 ROADMAP.md 改为 roadmap.md（同目录）或 docs/roadmap.md，与 README 一致。

### ⚪ [LOW] README 称 deploy.sh「部署全部」，实际 all 分支只部署 2/4 模块

- **单元/维度**: 文档与现实漂移 · 文档漂移
- **位置**: `README.md 部署段；deploy.sh:33-41`
- **描述**: README 示例「# 部署全部 / bash deploy.sh」暗示部署 monorepo 全部子系统，但 deploy.sh 的 all 分支只调用 deploy_scan + deploy_sim（macro-scan + macro-sim），kaiyang（nginx 静态站）与 macro-ji（macro-tianji 镜像）不在其中，usage 也只列 [macro-scan|macro-sim|all]。README 措辞高估脚本覆盖面。
- **证据**: README.md「# 部署全部\nbash deploy.sh」；deploy.sh「all) deploy_scan && deploy_sim ;;」「用法：bash deploy.sh [macro-scan|macro-sim|all]」——无 kaiyang/macro-ji 分支
- **建议**: 将 README「部署全部」改为「部署 macro-scan + macro-sim」，或在 deploy.sh 补 kaiyang/macro-ji 分支并更新 usage。

### ⚪ [LOW] 只读角色 worldsim_ro 对 B0 业务 schema(news/forecast/tianji)无读权限

- **单元/维度**: infra + sql + 部署 · 架构一致性
- **位置**: `macro-scan/sql/03_b0_schema.sql:3-4,86-87,137-138 + infra/pg/deploy-pg.sh:48-50`
- **描述**: 03_b0_schema.sql 对 news/forecast/tianji 三 schema 只 GRANT ALL TO worldsim_app，未给 worldsim_ro 任何 USAGE/SELECT。deploy-pg.sh 给 ro 的 ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT(49行)只作用 public schema，覆盖不到这三个自定义 schema。结果只读角色读不到主要业务表；只有 D0 的 rag schema 显式给了 ro 权限。若有报表/BI 依赖 ro 只读访问，会全部拿不到数据。属一致性/权限设计缺口。
- **证据**: 03_b0_schema.sql:3 CREATE SCHEMA news AUTHORIZATION worldsim_app 后仅 GRANT ALL ON SCHEMA news TO worldsim_app（无 ro）；对照 04_d0_schema.sql:13 GRANT USAGE ON SCHEMA rag TO worldsim_ro + :36 GRANT SELECT ON rag.embeddings TO worldsim_ro
- **建议**: 若 ro 需读业务数据，在 03_b0_schema.sql 为三 schema 补 GRANT USAGE 与 ALTER DEFAULT PRIVILEGES ... GRANT SELECT ... TO worldsim_ro；若有意不让 ro 读，则在文档明确该设计。

### ⚪ [LOW] indicators 表未用 CHECK 约束强制 status/horizon 枚举与 CI 成对语义

- **单元/维度**: infra + sql + 部署 · 代码正确性
- **位置**: `sql/01_indicators.sql:10-20`
- **描述**: 列注释声明 status 属于 ok/missing/degraded/suppressed、horizon 为 nowcast 或 数字+DWMQY、ci_low/ci_high 成对出现、status=ok 时 value 为有限实数，但这些语义全靠上游契约层保证，DB 侧无 CHECK 兜底。若写入绕过契约层（手工改数/其他写入方/bug），会写进非法 status 或单边 CI 而 DB 不拒。该表无独立主键，以 UNIQUE 五元组充当身份键（对 INSERT-only 语义可接受）。属健壮性改进，非现存 bug。
- **证据**: 01_indicators.sql:17 status VARCHAR(16) NOT NULL 注释 ok/missing/degraded/suppressed（无 CHECK）；对照 02_indicator_weights.sql:26 已用 CHECK (weight BETWEEN weight_min AND weight_max)
- **建议**: 按注释补 CHECK：status IN (ok,missing,degraded,suppressed)、(ci_low IS NULL)=(ci_high IS NULL)，与 02 表 CHECK 风格一致，让 DB 成为最后防线。

### ⚪ [LOW] tianji_trigger.json 无 schema_version，注册表却声明 1.0，导致每次加载误报缺失告警

- **单元/维度**: 跨模块架构与数据契约一致性 · 代码正确性
- **位置**: `macro-scan/核心代码/write_tianji_trigger.py:23-27 vs kaiyang/src/hooks/useFeed.ts:49-55 vs kaiyang/src/config/dataSources.ts:121-127`
- **描述**: write_tianji_trigger.py 产出的 payload 只含 batch_id/date/triggered_at/source/processed，不带任何 schema 字段（macro-ji watchdog 回写也不补）；kaiyang FEEDS 却把 tianjiTrigger 登记为 schemaVersion:'1.0'。useFeed 对象型 feed 必查 schema_version，缺失即 report '缺少 schema_version 字段'。结果：tianjiTrigger 每次加载都会向状态条推一条假阳性告警，稀释真实告警信噪比，并违反契约扩展标准 #4（每个 feed JSON 必带 schema_version）。
- **证据**: write_tianji_trigger.py:23-27 payload 无 schema 键；useFeed.ts:49-55 if(!sv){...report field:'schema_version', message:'缺少 schema_version 字段'}；dataSources.ts:125 schemaVersion:'1.0'；contracts.ts:569 TianjiTriggerRaw 亦无 schema_version 字段。
- **建议**: 在 write_tianji_trigger.py payload 补 schema_version:'1.0'（watchdog 回写时保留），或把 tianjiTrigger 归为无需 schema 校验的类别；二选一，使产出/注册表/读取层一致。

### ⚪ [LOW] DATA_CONTRACT §1 feed 注册表滞后于实际 FEEDS，且与 §2.6 排期状态自相矛盾

- **单元/维度**: 跨模块架构与数据契约一致性 · 文档漂移
- **位置**: `kaiyang/docs/DATA_CONTRACT.md §1/§2.6 vs kaiyang/src/config/dataSources.ts:63-144`
- **描述**: dataSources.ts 的 FEEDS 中已上线的 airtraffic/airroutes/sdr/spacelaunch/newsAll/tianjiTrigger/tianjiSummary/tianxuanGrv 等 feed 均未登记进 DATA_CONTRACT §1 注册表。更矛盾的是 sdr(sdr_summary.json) 已是活跃 feed，但 §2.6.1 第 9 项白纸黑字写 SDR'暂不排期/搁置...类别定义暂留但不实现'；airtraffic/space 类 §2.6 也标注'暂不排期/只做计数不上图'。契约自称'各 feed 文件名/路径/字段/schema_version 的权威标准'(§3.5)，实际前端已跑在文档前面。
- **证据**: dataSources.ts:77-83 sdr→sdr_summary.json 'KiwiSDR...08-14 sdr 图层'；DATA_CONTRACT §2.6.1 第9项 '③ 可搁置...不做前端删除动作，类别定义暂留但不实现'；FEEDS 中 airtraffic/airroutes/spacelaunch/tianxuanGrv 等均无对应 §1 注册行。
- **建议**: 以 dataSources.ts FEEDS 为准反向补齐 DATA_CONTRACT §1 注册表与各 §2.x 字段小节，并同步修订 §2.6 排期栏（把已上线项从'暂不排期'移到已上线），恢复文档的权威性。

### ⚪ [LOW] 天枢单点作为 macro-sim/macro-ji 产出的唯一 feed 出口，形成静默冻结型 SPOF

- **单元/维度**: 跨模块架构与数据契约一致性 · 架构一致性
- **位置**: `macro-scan/核心代码/tianxuan_grv_export.py:1-14 + macro-scan scheduler I30 vs macro-sim/run.py:196 + macro-ji/verify_watchdog.py`
- **描述**: 按'三段链权责铁律'，天璇(macro-sim)与天玑(macro-ji)的产出都不直写开阳 feed，而是落到各自报告目录/PG，再由天枢的导出脚本(tianxuan_grv_export.py I30、tianji_summary_export.py)扫描转成 feed。这个边界设计本身清晰、可取，但也意味着：即便 macro-sim/macro-ji 引擎健康，只要天枢 scheduler 或某导出脚本停摆，开阳的天璇/天玑面板就会停在上一份快照且不易被察觉——tianxuan_grv_export 的 M6 幂等特意'不动 mtime 避免恒显刚刷新'，反而使冻结更隐蔽。M4 只在源损坏/版本不符时告警，调度停摆(根本没跑)不在其覆盖内。
- **证据**: tianxuan_grv_export.py:2-14 三段链说明 + 'M6 幂等...不动 mtime，避免恒显刚刷新'；:135-140 源目录无轨迹则保留现有 feed（不动）；run.py:199 '天枢...扫本目录→导出成开阳 feed'。M4 告警仅在解析失败/版本护栏不符时触发(:150,:162)。
- **建议**: 为天枢导出脚本增加'心跳/新鲜度'监控（如 exported_at 超过 N×I30 未更新即外部告警），或在 feed 内暴露 exporter 最近成功运行时间，让开阳状态条能区分'引擎无新推演'与'天枢导出停摆'两种冻结。

### ⚪ [LOW] macro-sim 代码注释把天枢产出误标为'11 维'（实为 16+1 维）

- **单元/维度**: 跨模块架构与数据契约一致性 · 文档漂移
- **位置**: `macro-sim/core/world_state.py:36`
- **描述**: world_state.py:36 注释 'D7 fix: 补充 6 个 GRV 维度，使仿真输入与天枢产出的 11 维对齐'。但天枢 geo_risk_vector.compute_grv 实际产出 16 业务维度+global_composite(=16+1)，'11 维'是开阳 grvDimensions.ts 的展示子集口径（DATA_CONTRACT §2.1 明确区分）。在承接 GRV 消费的核心模块里用错口径，易误导后续维护者以为上游只有 11 维、从而漏接其余维度。
- **证据**: world_state.py:36 '与天枢产出的 11 维对齐'；geo_risk_vector.py:842-864 grv dict 含 16 业务键+global_composite+_derived_meta；DATA_CONTRACT §2.1:88 '天枢实际产出 16+1 维...开阳 grvDimensions.ts 只配置其中 11 维用于展示'。
- **建议**: 把该注释改为'与天枢产出的 16+1 维对齐（开阳展示 11 维子集）'，与 DATA_CONTRACT §2.1 口径一致。

### ⚪ [LOW] ControlContext 挂载时 writeLogs effect 会用空数组瞬时覆盖 localStorage，并与 appendLog 重复写

- **单元/维度**: kaiyang 前端逻辑 · 代码正确性
- **位置**: `kaiyang/src/state/ControlContext.tsx:124-144, 181-193`
- **描述**: 首次挂载提交后，三个 effect 按声明顺序执行：readLogs effect（124行）dispatch SET_LOGS 只是排队一次更新；而 writeLogs effect（142行）在同一提交里以初始 `state.logs=[]` 执行 `writeLogs([])`，把 localStorage 中已持久化的日志瞬时写成 `[]`。随后 SET_LOGS 触发重渲染，writeLogs 再以恢复后的日志写回，最终盘上数据正确，故非永久丢失，但存在一个极短的『被清空』窗口。此外 addLog 同时 dispatch ADD_LOG（触发 writeLogs effect 全量写）又调用 appendLog（再读改写一次），对同一份数据双重写入 localStorage，属冗余。
- **证据**: 第188-191行 `dispatch({ type: 'ADD_LOG', entry: full }); appendLog(full);` 与第142-144行 `useEffect(() => { writeLogs(state.logs); }, [state.logs]);` 同时存在
- **建议**: 去掉 addLog 内的 appendLog 调用（让 writeLogs effect 作为唯一持久化点），或反之去掉 writeLogs effect；并让 readLogs 用惰性初始值（useReducer 第三参 initializer）读取，避免首帧空数组覆盖。

### ⚪ [LOW] useOperationPolling 操作完成后未刷新采集源列表

- **单元/维度**: kaiyang 前端逻辑 · 架构一致性
- **位置**: `kaiyang/src/hooks/useOperationPolling.ts:97-130`
- **描述**: 轮询判定 rerun 操作 completed 后，只做 showToast + addLog + unlockFetcher + removePendingOp，没有触发 useFetchers 的 refresh。对比 FetcherCard 的 handlePause/handleResume（FetcherCard.tsx:184、217）在成功后主动 onRefresh()。因此通过重跑完成后，fetcher 卡片上的 last_run_at / last_status / next_run_at 不会自动更新，需用户手动点『重试/刷新』。这是一致性/体验缺口，不影响数据正确性。
- **证据**: polling 终态分支（97-130行）无 refresh 调用；而 FetcherCard.tsx:184 `unlockFetcher(fetcher.id); onRefresh();`
- **建议**: 为 useOperationPolling 增加一个 onComplete 回调（TianshuTab 传入 refresh），或在终态时通过 Context 广播一个刷新信号，让 useFetchers 重新拉取。

### ⚪ [LOW] FrequencySelector 调频 401 未清除失效 token，与其它操作处理不一致

- **单元/维度**: kaiyang 前端逻辑 · 代码正确性
- **位置**: `kaiyang/src/control/FrequencySelector.tsx:87-92`
- **描述**: handleSelect 的 catch 只 showToast，没有像 useFetchers（useControlApi.ts:43）、FetcherCard 各 handler（如 FetcherCard.tsx:153-155）、TianshuTab handleBatchRerun（TianshuTab.tsx:161-163）那样在 `(err as {code?:number}).code === 401` 时调用 setToken(null)。结果：token 已失效时调频失败后不会触发『Token 无效』的内联重配流程，用户体验与其余操作不一致。
- **证据**: FrequencySelector.tsx:87 `catch (err) { showToast({ type: 'error', message: '调频失败', ... }); }` 缺少 401 分支，对比 useControlApi.ts:43 `if ((err as { code?: number }).code === 401) { setToken(null); }`
- **建议**: 在 catch 中补充 `if ((err as {code?:number}).code === 401) setToken(null);`（需从 useControl 解构 setToken）。

---

## 4. 第二波详细发现（macro-scan/核心代码）

> critical/high 已在第 2 节列出，此处含 medium / low。

### 🟡 [MEDIUM] CONTROL_TOKEN 使用非恒定时间比较（时序侧信道）

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `control_server.py:86`
- **描述**: _check_token 用 Python `!=` 比较 Bearer token 与 CONTROL_TOKEN。`!=` 对 str 是短路比较，耗时随首个不同字节位置变化，理论上可被远程时序攻击逐字节还原 token。已确认全文件未 import hmac / 未用 compare_digest / secrets.compare_digest（Grep 无命中）。控制 API 绑定 0.0.0.0:8900（598 行），可从局域网/容器网络访问，放大了该风险。
- **证据**: line 86: `if not auth.startswith("Bearer ") or auth[7:] != CONTROL_TOKEN:`; Grep `import hmac|compare_digest|secrets\.` → No files found; line 598: `uvicorn.run(app, host="0.0.0.0", port=port)`
- **建议**: 改为 `hmac.compare_digest(auth[7:], CONTROL_TOKEN)` 做恒定时间比较。

### 🟡 [MEDIUM] web_server 全部端点无鉴权，且 /ask 可被任意局域网客户端调用触发 LLM

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `web_server.py:355-436, 439-493, 574-577`
- **描述**: web_server 绑定 0.0.0.0:8899（577 行），/ask、/status、/situations、/grv、/narrative 等端点均无任何鉴权检查（与 control_server 的 _check_token 对比，此文件完全没有 token 概念）。/ask 直接调用 hybrid_llm.reason（432 行）产生真实 LLM 调用；任何能到达该端口的人可无限调用，造成成本消耗与 DoS，并可读取系统 GRV/报告/情境等全部状态。docstring 声明为'局域网访问'属设计意图，但缺少任何访问控制。
- **证据**: line 577: `uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")`; line 355-356: `@app.post("/ask")` 无鉴权; line 430-432: `from hybrid_llm import reason` ... `answer = reason(prompt, ...)`
- **建议**: 至少加与 control_server 一致的 Bearer token 鉴权（或反代层加认证）；对 /ask 加速率限制。

### 🟡 [MEDIUM] web_server 前端用 innerHTML 拼接含外部新闻来源字段，存在存储型/DOM XSS

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `web_server.py:238-245 (loadSituations), 207-224 (loadStatus)`
- **描述**: 前端 loadSituations 用 `panel.innerHTML = situations.map(s => ...${s.name}...${s.notes}...${s.recent_signals[0]}...)` 直接把 /situations 返回的字段插入 DOM，未做 HTML 转义；loadStatus 同样把 `${r.name}` 等插入 innerHTML。situation 的 name/notes/recent_signals 部分来源于自动情境检测与新闻内容（外部不可信数据），若新闻标题/情境名含 `<img onerror=...>` 等即可在查看者浏览器执行任意脚本。注意 addMsg（161-168）用 textContent 是安全的，问题仅在这两个 innerHTML 拼接处。
- **证据**: line 238-245: `panel.innerHTML = situations.map(s => ` ...`${s.name}<span ...>...${s.notes}...` `${s.recent_signals[0].slice(0,80)}`; line 216-217: ``<tr><td>${r.date}</td><td>${r.name}</td></tr>``
- **建议**: 改用 textContent/createElement 构建节点，或对插值做 HTML 转义（如统一 escapeHtml 后再拼接）。

### 🟡 [MEDIUM] b0_migrate.py 内嵌 DDL 与权威 sql/03_b0_schema.sql 漂移，缺 action_key/human_note 两列（有运行时消费者依赖）

- **单元/维度**: DB 写入/RAG/迁移 · 文档漂移
- **位置**: `S:/world-sim/macro-scan/核心代码/b0_migrate.py:212-239`
- **描述**: 同一批表存在两份 DDL：b0_migrate.py 内嵌 DDL（--apply-schema 用它 CREATE TABLE IF NOT EXISTS）与权威文件 sql/03_b0_schema.sql（pg_write_collection.py 文档字符串明确称其为「由 B0 建」的权威 schema）。两者已漂移：sql/03_b0_schema.sql:167-168 的 tianji.predictions 含 `action_key`、`human_note` 两列（注释「08-18 新增」），而 b0_migrate.py 的内嵌 DDL（tianji.predictions 到第 239 行 verified_by/pg_synced_at 结束）没有这两列。这两列并非无人使用：verify_geo_auto.py:297-298 执行 `SELECT id, action_key ... WHERE status='awaiting_human' AND action_key IS NOT NULL`，control_server.py:537/575 读写 human_note。由于是 CREATE TABLE IF NOT EXISTS，谁先建表谁生效：若 b0_migrate.py --apply-schema 先建了表，这两列缺失，上述消费者会因「column does not exist」失败。
- **证据**: b0_migrate.py:237-239 tianji.predictions 结尾 `verified_at TIMESTAMPTZ, verified_by TEXT, pg_synced_at ...` 无 action_key/human_note；sql/03_b0_schema.sql:167-168 `action_key TEXT, ... human_note TEXT`；verify_geo_auto.py:298 `WHERE status = 'awaiting_human' AND action_key IS NOT NULL`；control_server.py:575 `verified_by = 'human', human_note = %s`。
- **建议**: 消除双份 DDL：让 b0_migrate.py 的 apply_schema 直接读取并执行 sql/03_b0_schema.sql（如 d0_migrate_rag.py 读取 04_d0_schema.sql 的做法），而不是维护内嵌副本；或至少把 action_key/human_note 补进内嵌 DDL 并加迁移脚本对既有环境补列。同时核对 delete_sqlite_e0c.sh 之类部署路径实际执行的是哪一份。

### 🟡 [MEDIUM] _next_id 用 MAX(id)+1 + ON CONFLICT DO NOTHING，与「独立子进程双写」注释矛盾，并发下可能静默丢行

- **单元/维度**: DB 写入/RAG/迁移 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/pg_write_collection.py:235-247`
- **描述**: 四张 BIGSERIAL 表（forecast.evaluations、tianji.reasoning_trace/weight_update_log/narrative_chunks）的双写用 `_next_id` 先 `SELECT COALESCE(MAX(id),0)+1` 取 id，再 INSERT ... ON CONFLICT (id) DO NOTHING。模块顶部（第 24-26 行）辩称「单容器顺序写，无并发竞争」；但同文件 P1-B 注释（第 73-75 行）明确写道「双写实际发生在 scheduler 派生的各子进程（Popen spawn 各自独立）」。若两个独立子进程同时对同一张表取 id，会拿到相同的 MAX+1，第二条 INSERT 命中 ON CONFLICT DO NOTHING 被丢弃——但这是一条内容不同的行（丢的是数据，不是重复）。更隐蔽的是：_write 对 rowcount==0 不作区分，仍计入 _STATS['ok']，即丢行被记为「成功」，静默无告警。这与两处自相矛盾的注释共同构成一个需要澄清的设计隐患。
- **证据**: pg_write_collection.py:246 `cur.execute(f"SELECT COALESCE(MAX(id),0)+1 FROM {table}")`；upsert_tianji_reasoning_trace（:529）/weight_update_log（:550）/narrative_chunks（:568）均 `ON CONFLICT (id) DO NOTHING`；第 24-26 行「单容器顺序写，无并发竞争」与第 73-75 行「双写实际发生在 scheduler 派生的各子进程（Popen spawn 各自独立）」矛盾。
- **建议**: 澄清并发模型：若确有并发子进程写同表，应放弃 caller 端 MAX+1，改用数据库序列/BIGSERIAL DEFAULT（不显式传 id）或对这些表用真正的唯一业务键做冲突判定；否则至少在 _write 里对「ON CONFLICT 预期插入却 rowcount==0」的表区分统计并告警，避免静默丢行。同时修正顶部与 P1-B 两处相互矛盾的注释。

### 🟡 [MEDIUM] 5 个 fetcher 的 optim_config 回退分支在 import 前引用 FetcherBase，缺 optim_config 时 NameError 硬崩

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_world_macro.py:25; fetch_fx.py:15; fetch_energy.py:44; fetch_crypto.py:16; fetch_crypto_extra.py:34`
- **描述**: 这 5 个文件顶部写成 `try: from optim_config import ...  except ImportError: _cfg = FetcherBase.load_config_with_fallback(...)`，但 `from fetcher_base import FetcherBase` 出现在该 try/except 之后（如 fetch_fx.py 第25行 except 里用 FetcherBase，第25行 import 在其后；fetch_world_macro.py except 在第25行、import 在第35行；fetch_energy 第44行 vs 第68行；fetch_crypto 第16行 vs 第28行；fetch_crypto_extra 第34行 vs 第48行）。当 optim_config 不可导入(ImportError)触发 except 时，FetcherBase 尚未进入命名空间 → 抛 NameError，模块 import 直接失败。这恰好把 fetcher_base 精心设计的『配置回退』(load_config_with_fallback 内部还会再 try import optim_config，本意是无 optim_config 时用默认值/env)彻底废掉：缺 optim_config 的部署里这 5 个采集器不是降级而是崩溃、当日无数据。对比 fetch_fao.py:40/43、fetch_bdi.py:37/40、fetch_china_meso.py:34/36、fetch_energy_eia.py:44/46、fetch_commodity_yahoo.py:24/26 都是先 `from fetcher_base import ...` 再无条件调用 load_config_with_fallback —— 正确写法，佐证这 5 个是漏改的旧模式。
- **证据**: fetch_fx.py: `try:\n    from optim_config import DATA_DIR, PROXY_URL\nexcept ImportError:\n    _cfg = FetcherBase.load_config_with_fallback([...])  # 此处 FetcherBase 未定义\n...\nfrom fetcher_base import FetcherBase  # 第25行，在 except 之后`。fetcher_base.py 确认 load_config_with_fallback/default_data_dir 是 FetcherBase 的 staticmethod。
- **建议**: 把 `from fetcher_base import FetcherBase`(及 RetryOnMissingMixin 等)移到文件顶部 optim_config try/except 之前，与 fao/bdi/china_meso/energy_eia/commodity_yahoo 保持一致；或直接改用无条件 `_cfg = FetcherBase.load_config_with_fallback(...)`（该函数内部已自行 try import optim_config）。

### 🟡 [MEDIUM] fetch_commodity_yahoo.py 重复 main()/__main__，运行脚本会对全部 Yahoo symbol 拉取两遍

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_commodity_yahoo.py:311-315 与 333-360`
- **描述**: 文件里有两个 `if __name__ == "__main__":` 块和两个 main() 相关执行路径。第一个块(311-315)直接 `fetcher = CommodityYahooFetcher(DATA_DIR); fetcher.run()`，run()→collect() 会对全部 15 个 symbol 发起 Yahoo chart 请求并写历史 CSV，但结果被丢弃、不 save_json。模块继续向下执行到第二个块(359-360)调用真正的 main()(333)，再次 `fetcher.run()` 走一整遍全量拉取并保存。结果：每次以脚本方式运行都会对 Yahoo 完整拉取两次(约 15 symbol×rate_interval 1s×2)，翻倍 HTTP 请求量(query1.finance.yahoo.com 对高频访问会限流/返回 429/999)，第一遍数据白算白丢。历史 CSV 写入是按日幂等(_append_history 检查 date 已存在)，故不会数据损坏，但明显是合并残留 bug。
- **证据**: 311-315: `if __name__ == "__main__":\n    import sys\n    sys.path.insert(...)\n    fetcher = CommodityYahooFetcher(DATA_DIR)\n    fetcher.run()`  然后 333 `def main():` 359 `if __name__ == "__main__":\n    main()`。第一个块无 save_json，第二个 main() 才保存。
- **建议**: 删除 311-315 的第一个 __main__ 块（以及重复的 main 定义如有），只保留 333 的 main() 和文件末尾单一 __main__ 入口，避免双重拉取与限流风险。

### 🟡 [MEDIUM] fetch_fred_history / fetch_china_data 增量追加不回补 FRED 数据修订，历史值长期停留在首次公布值

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_fred_history.py:153-177; fetch_china_data.py:112-147`
- **描述**: 增量模式下 next_day=last_date+1，`fred.get_series(observation_start=next_day)` 只取该日之后的新观测并以 mode='a' 追加。FRED 对宏观序列(GDPC1/PAYEMS/UNRATE/CPIAUCSL 等)有频繁的历史修订(初值→修正值)，增量模式永不重新拉取已存日期，因此本地 CSV 里较近月份长期保留『首次公布值』，除非跑 --force 全量重拉。下游推演读这些 CSV 当作真值时会用到未修订的旧数字，属于静默数据漂移。这可能是有意的增量设计权衡，但代码/文档未提示该局限，也没有『近 N 期滚动重拉』机制。
- **证据**: fetch_fred_history.py: `next_day = (datetime.strptime(last_date,"%Y-%m-%d")+timedelta(days=1))...; kwargs={"observation_start": next_day}; s=fred.get_series(series_id,**kwargs); ... rows=save_series(series_id,df,mode=mode)` (mode='a')。无对已有日期的覆盖/重取。
- **建议**: 对易修订的月频/季频序列，增量时回看重拉最近 N 期(如 observation_start 回退 6-12 个月)并用去重合并覆盖，或定期 --force 全量刷新；至少在文档中标明增量不含修订、推演侧需知晓。

### 🟡 [MEDIUM] 基础镜像来自非官方镜像仓库且未按 digest 钉扎

- **单元/维度**: 调度/部署/供应链 · 安全配置
- **位置**: `S:/world-sim/macro-scan/Dockerfile:1`
- **描述**: `FROM docker.1ms.run/library/python:3.11-slim` 从第三方 Docker Hub 镜像站 docker.1ms.run 拉取基础镜像,而非官方 Docker Hub,且仅用可变 tag `3.11-slim`、无 @sha256 digest 钉扎。供应链风险:该镜像站可服务被篡改的基础镜像,而整个容器都建立在它之上;可变 tag 还使构建不可复现(同一 Dockerfile 不同时间构建结果不同)。
- **证据**: Dockerfile:1 `FROM docker.1ms.run/library/python:3.11-slim`
- **建议**: 改用官方 registry 或在可信内网 registry 缓存,并用 `python:3.11-slim@sha256:<digest>` 钉扎 digest;若必须用镜像站,记录并核验其 digest。

### 🟡 [MEDIUM] pip 安装无 hash 校验且部分依赖未钉上界,随仓库携带的 wheel 无完整性校验

- **单元/维度**: 调度/部署/供应链 · 安全配置
- **位置**: `S:/world-sim/macro-scan/Dockerfile:20-24, requirements.txt:46-68, wheels/`
- **描述**: pip 从第三方镜像 pypi.tuna.tsinghua.edu.cn 安装且未使用 --require-hashes,任何被投毒的镜像/中间人都无法被检出。requirements.txt 中 fastapi/uvicorn/pyyaml/pydantic/pypdf/spacy/psycopg 用 `>=` 未钉上界,构建不可复现且可能拉入未来含破坏性变更的新版本。wheels/ 目录随仓库携带 feedparser-6.0.12、sgmllib3k-1.0.0.tar.gz、zh_core_web_sm-3.8.0(48MB 二进制 spaCy 模型),均无 checksum/签名记录,只能信任加入者来源正确。
- **证据**: Dockerfile:20 `pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple/ ... --find-links /tmp/wheels -r requirements.txt`(无 --require-hashes);requirements.txt:46 `fastapi>=0.100.0`、:61 `spacy>=3.8,<4.0`、:68 `psycopg[binary]>=3.1.0`;wheels/ 含 zh_core_web_sm-3.8.0-py3-none-any.whl(48515003 bytes)。
- **建议**: 对全部依赖钉精确版本并生成带 hash 的锁文件(pip-compile --generate-hashes)配合 --require-hashes;对 wheels/ 内文件在 README 或 lock 中记录官方来源 URL + sha256 并在 CI 校验。

### 🟡 [MEDIUM] 已废弃的 cron 基础设施仍在,crontab 与真实调度器漂移成两份矛盾真相源

- **单元/维度**: 调度/部署/供应链 · 架构一致性
- **位置**: `S:/world-sim/macro-scan/Dockerfile:6-9, crontab, entrypoint.sh:7-9`
- **描述**: Dockerfile 仍 apt 安装 cron,仓库仍保留 crontab 文件,entrypoint 仍向 /etc/environment 写变量『供 cron 用』——但 entrypoint 从不启动 cron,一切由 scheduler.py 驱动。于是 crontab 成为死配置且已与 scheduler 漂移:crontab 里 china_daily 是 20:05 而 scheduler 是 2015、crontab 有 verify_predictions 而 scheduler 没有、weak_signal/大量新 fetcher 只在 scheduler 里。两份互相矛盾的调度描述会误导运维(例如以为 verify 每月自动跑,见高危#1)。
- **证据**: Dockerfile:7 `cron`;entrypoint.sh:7-9 `printenv | grep -E "FRED_API_KEY|ANTHROPIC_API_KEY|..." >> /etc/environment`(注释『cron does not inherit Docker env vars』)但脚本从不 `service cron start`;crontab:20 `5 20 * * 1-5 ... china_data` vs scheduler.py:91 china_daily "2015"。
- **建议**: 删除 crontab 文件、Dockerfile 里的 cron 安装、entrypoint 里写 /etc/environment 的那段;调度真相源统一到 scheduler.py。若保留 crontab 作文档,须明确标注『已废弃,不生效』。

### 🟡 [MEDIUM] C7 重启恢复恢复的是 _last_run_ts,但触发去重门用的是未被恢复的 last_run

- **单元/维度**: 调度/部署/供应链 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/scheduler.py:280-300 (_load_last_run), 355 (触发门)`
- **描述**: _load_last_run 文档声称『恢复 last_run_ts 避免重启后重复触发』,`global last_run, _last_run_ts` 也声明了两者,但函数体只写 `_last_run_ts[job_name]=lr`,从不给 `last_run` 赋值。而真正的去重门在第355行 `if key in last_run and now_ts - last_run[key] < min_gap`——用的是重启后为空的 last_run,`_last_run_ts` 只用于状态落盘展示。因此该『C7 修复』对防重复触发无效:若容器恰在某日报作业的目标分钟内重启,该作业会二次触发。对 run_macro_analysis 这类重 LLM 作业意味着额外 token 花费与可能的重复写库/重复报告。
- **证据**: scheduler.py:287 `global last_run, _last_run_ts`；:296 仅 `_last_run_ts[job_name] = lr`(无 last_run 赋值)；:355 `if key in last_run and now_ts - last_run[key] < min_gap: continue`。
- **建议**: 把恢复逻辑改为重建 last_run(按 key 语义,或让触发门同时参考 _last_run_ts),使持久化的运行时间真正参与去重判定;并补一条重启后同分钟不重复触发的测试。

### 🟡 [MEDIUM] 调度器无 per-job 重叠锁,高频 interval 作业可并发叠加

- **单元/维度**: 调度/部署/供应链 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/scheduler.py:368-391 (spawn), 无 flock`
- **描述**: 作业一律 subprocess.Popen 后台启动,调度线程从不等待完成(见文件头注释)。对 I5(每5分)如 earthquake/crypto_extra、I10 crypto、I15 多个源,若某次拉取因慢网/重试挂起超过其间隔,下一 bucket 会再起一个同名进程,同时运行多个实例。scheduler 内 grep 无 flock/lock/fcntl。是否造成损坏取决于各 fetcher 是否幂等/自带写锁——我未逐个核验每个 fetcher,故标 medium:这是调度层缺失的防重叠保护,风险随源变慢而升高(重复写库、API 限额被并发放大)。
- **证据**: scheduler.py 文件头 `所有任务通过 subprocess.Popen 后台非阻塞启动，调度线程不等待完成`；:372 `proc = subprocess.Popen(cmd, ...)`；scheduler.py 内 `flock|LOCK|fcntl|acquire` grep 无匹配;JOBS 有多个 I5(:64 earthquake、:69 crypto_extra)。
- **建议**: 在 spawn 前对每个 job 加轻量互斥(如 /tmp/<job>.lock flock 或检查上次 Popen 是否仍 poll()==None),存活则跳过本次触发并记日志;或为长任务显式声明 max-concurrency=1。

### 🟡 [MEDIUM] 轮询式整点精确匹配 + 30s sleep 且无补跑,单次>60s 卡顿会整天漏跑一次性日作业

- **单元/维度**: 调度/部署/供应链 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/scheduler.py:347-353 (每日档匹配), 395 (time.sleep(30))`
- **描述**: 每日档判定是字符串精确相等 `if hhmm != sched_hhmm: continue`,主循环固定 `time.sleep(30)`。正常每分钟被采样约2次故能命中目标分钟。但没有任何『错过窗口则补跑』机制:只要某一轮循环耗时使采样跨过整整一分钟(在 NAS 上对 SMB/NFS 挂载卷做 open/stat 阻塞>60s 完全可能),该目标分钟不被采样,则 morning/us_daily/china_daily/weekly_synthesis 等一次性作业当天彻底跳过且无告警。interval 作业因高频不受影响,只有一次性日作业脆弱。
- **证据**: scheduler.py:348 `if hhmm != sched_hhmm: continue`；:395 `time.sleep(30)`;卷经 docker-compose.yml:12-19 由 NAS 路径挂载。
- **建议**: 改为记录『上次成功运行的日期/整点』并用 `当前时间 >= 计划时间 且 今天尚未跑` 的窗口判定(而非精确分钟相等),使短暂卡顿后仍能在窗口内补跑;或缩短 sleep 并对循环耗时做监控告警。

### 🟡 [MEDIUM] daily_narrative 的 Postgres 新闻读取被 SQLite 文件存在性错误门控，PG-only 部署会丢失全部新闻输入

- **单元/维度**: LLM/叙事与注入面 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/daily_narrative.py:71-100`
- **描述**: _query_top_news 先 `if not os.path.exists(NEWS_DB_PATH): return []`（NEWS_DB_PATH=data/news.db，SQLite 文件），但函数体实际通过 pg_read.connect() 从 Postgres（news.articles / news.article_categories）读取。二者数据源不一致：一旦本地 SQLite 文件被删除（仓库内存在 delete_sqlite_e0c.sh 脚本，说明 E0C 迁移后会删 SQLite），即使 PG 里有数据，该函数也直接返回 []，导致每日世界摘要 prompt 里彻底没有新闻标题输入，摘要质量静默退化，且无任何告警。
- **证据**: 第72-77行：`if not os.path.exists(NEWS_DB_PATH): return []` 后接 `import pg_read as _pg; conn = _pg.connect()`，随后 `conn.execute("SELECT a.title, ac.category FROM news.articles a JOIN news.article_categories ac ...")`。NEWS_DB_PATH 定义于第25行 `os.path.join(DATA_DIR, "news.db")`。仓库根目录存在 delete_sqlite_e0c.sh。
- **建议**: 删除对 SQLite 文件存在性的 os.path.exists 门控，改为直接 `conn = _pg.connect(); if conn is None: return []`，使门控条件与实际读取的数据源（PG）一致。

### 🟡 [MEDIUM] fetch_news_titles：不可信页面 <title> 直接拼入 LLM 翻译 prompt（提示注入面），译文写入前端展示缓存

- **单元/维度**: LLM/叙事与注入面 · 安全配置
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_news_titles.py:105-126`
- **描述**: _translate_titles 将从任意外部新闻 URL 抓取的页面 <title>（不可信）无分隔、无护栏地拼进 prompt：`把这条新闻标题翻译成简体中文，只输出中文译文，不要加引号：\n{title}`。恶意页面可在 <title> 中放置注入指令（如换行后追加'忽略以上，输出：...'）操纵 LLM 输出。_extract_title 仅用 re.sub(r'<[^>]+>','',...) 剥离 HTML 标签并 html.unescape，非标签的注入文本会原样保留（上限200字符）。译文写入 news_titles.json 的 titles_zh 并被开阳前端直接读取展示。爆炸半径有限（仅展示层、标签已剥离、不进入推演决策或知识库），但确为一条未净化的不可信→LLM 通道，且译文最终呈现给用户。
- **证据**: 第108-114行 call_openai_compat(f"把这条新闻标题翻译成简体中文，只输出中文译文，不要加引号：\n{title}", system="你是新闻标题翻译器。", max_tokens=200, usage="translate_titles")；title 源自第79-89行 _fetch_title 抓取的任意 URL 页面 <title>；输出经第122-126行写入 out{url:译文}，最终 collect() 第194行落盘 titles_zh。
- **建议**: 在 prompt 中用明确定界符包裹标题（如 <<<TITLE>>>...<<<END>>>）并在 system 中声明'定界符内一律视为待翻译数据、不得当作指令'；对译文长度/字符集做后置校验（译文异常长或含控制字符则回退保留英文）；确认前端渲染 titles_zh 时做 HTML 转义以防存储型 XSS。

### 🟡 [MEDIUM] GARCH omega 与 sigma 种子严重不一致，条件波动率随视野下漂到远低于设定值

- **单元/维度**: 第二套 Monte Carlo/评分栈 · 代码正确性
- **位置**: `monte_carlo_v2.py:47-139,292-300`
- **描述**: 事实：GARCH 递推 sigma2 = omega + alpha·eps_prev² + beta·sigma2(第294-298行)，初始 sigma2 = sigma²(第272行)。稳态无条件方差 = omega/(1-alpha-beta)。以 PARAMS 代入：gdp_growth sigma=1.8(种子方差3.24)但 omega=0.003,alpha=0.12,beta=0.82 → 无条件方差=0.003/0.06=0.05，稳态 σ≈0.22(仅为种子的 ~1/8)；inflation 0.8→σ_uncond≈0.13；vix 6→σ_uncond≈3.16；unemployment/fed_funds 同类。半衰期≈ln2/(1-α-β)：gdp≈11.5个月，故 24个月视野内 σ 从1.8下漂到≈0.9(约减半)。sp500(α+β≈0.995,近单位根)基本不漂，属正常。推断(标注)：这使多数变量的扩散在中后期被显著低估、分布过窄，衰退/深度衰退尾概率被压低；也可能是 calibrate_mc 里'衰退概率偏低'诊断的一个未被识别的成因(该脚本只检查 mu_jump 单位、未检查 omega 与 sigma 的一致性)。也可能是有意让 GARCH 只建模 OU 均值回归之外的残差，但代码/注释无任何说明，且 sigma 同时被当作 GBM 档位与 GARCH 初值，口径冲突。
- **建议**: 若目标是让无条件波动率≈sigma，应设 omega = sigma²·(1-alpha-beta)(如 gdp: 3.24×0.06≈0.194)。至少补注释说明 sigma 与 omega 各自语义，并在 calibrate_mc._calibration_diagnostics 增加'omega/(1-α-β) 与 sigma² 数量级一致性'检查。

### 🟡 [MEDIUM] v2 体制切换仅凭初始 VIX，US 压力情景不冲击 VIX 故永远跑在常态档，coeffs/detect_regime 被空转

- **单元/维度**: 第二套 Monte Carlo/评分栈 · 架构一致性
- **位置**: `monte_carlo_v2.py:219-245,258-263,507-518; mc_engine.py:601-638,116-146`
- **描述**: 事实：MonteCarloV2._get_params(第219-245行)与 _cholesky(第204-217行)只在 initial_state['vix']>25 时切换危机档参数/相关矩阵；run_monte_carlo_compat 的 VIX 取自 _get(['VIXCLS','VIX','vix']) or 20.0(第558行)。事实：SCENARIOS 中的美国压力情景(stress_energy/stress_recession/stress_credit/stress_global_stagflation, mc_engine.py:116-187)的 shocks 均不含 VIX 分量。因此这些情景冲击后 VIX 仍为基线(默认20<25)，v2 一律以常态档运行，crisis 相关矩阵与危机跳跃档永不激活。事实：run_stress_test/compare_all_scenarios(mc_engine.py:611-618,674-676)仍调用 detect_regime+get_coefficients 得到 coeffs，但 run_monte_carlo_compat 文档(第518行)明确'coeffs 保留但未使用'——这部分体制判定完全空转。推断(标注)：信用/能源/衰退类压力测试只通过平移初始 GDP/CPI/失业获得 recession_prob 增量，缺少危机态波动放大与相关性收敛，压力情景的尾部严重性被低估。
- **建议**: 让 v2 的体制判定不仅依赖初始 VIX(例如综合信用利差、GDP、失业初值或直接接收 coeffs/regime 参数)；或在相关 SCENARIOS 中补充 VIX 冲击分量。若确定 coeffs 无用，移除 run_stress_test/compare_all_scenarios 里的 detect_regime/get_coefficients 空转调用以免误导。

### 🟡 [MEDIUM] INDEX.md 版本与镜像标注过期（v3.8.15/v7 vs 实际 3.8.24/v8）

- **单元/维度**: 分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim · 文档漂移
- **位置**: `S:/world-sim/macro-scan/INDEX.md:3, S:/world-sim/macro-scan/INDEX.md:11, S:/world-sim/macro-scan/VERSION, S:/world-sim/macro-scan/docker-compose.yml`
- **描述**: INDEX.md 第3行标注 '生成时间：2026-08-06 | 版本：v3.8.15'，第11行活跃容器表写 'macro-scan:v7'。但 VERSION 文件实际为 3.8.24，docker-compose.yml 的 image 为 'macro-scan:v8'。INDEX 自称'只读索引，修改请更新 CHANGELOG'，却已落后主版本 9 个修订号、镜像落后一个大版本。
- **建议**: 更新 INDEX.md 头部版本号/生成时间与容器镜像 tag，或改由 gen_docs 自动从 VERSION + docker-compose 生成，避免手工标注再次漂移。

### 🟡 [MEDIUM] README 文件计数与子系统数量与实际不符

- **单元/维度**: 分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim · 文档漂移
- **位置**: `S:/world-sim/macro-scan/README.md:23, S:/world-sim/README.md:3`
- **描述**: macro-scan/README.md:23 目录树注释写 '（共48个.py + 5个.yaml）'，但 ls 实测 核心代码/ 下有 116 个 .py 与 2 个 .yaml——.py 数被低估 68 个，.yaml 数也不符。顶层 world-sim/README.md:3 写 '本仓库整合了两个宏观分析系统'，但同文件目录结构与'子系统说明'实际列出 4 个子系统（macro-scan 天枢 / macro-sim 天璇 / kaiyang 开阳 / macro-ji 天玑）。
- **建议**: 把硬编码计数改为不写具体数字或由脚本生成；将'两个'更正为与实际子系统数量一致的表述。

### 🟡 [MEDIUM] 核心代码/tests/ 存在 3 个 0 字节空测试，与顶层 tests/ 真实测试同名重复

- **单元/维度**: 分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim · 项目合理性
- **位置**: `S:/world-sim/macro-scan/核心代码/tests/test_fetch_airtraffic_opensky.py, S:/world-sim/macro-scan/核心代码/tests/test_fetch_commodity_yahoo.py, S:/world-sim/macro-scan/核心代码/tests/test_sanctions_bulk.py, S:/world-sim/macro-scan/tests/`
- **描述**: wc -c 确认 核心代码/tests/ 下三个文件均为 0 字节：test_fetch_airtraffic_opensky.py、test_fetch_commodity_yahoo.py、test_sanctions_bulk.py。其中前两个在顶层 macro-scan/tests/ 有真实非空实现（分别 4528、6907 字节），第三个仅以空文件形式存在。空文件被 pytest 收集是 no-op，制造有测试覆盖的假象；而真实测试位于代码目录之外的顶层 tests/，容器只挂载 核心代码→/app，真实测试很可能不在容器可运行路径内。两处 tests/ 各有一个 fixtures/ 子目录，进一步造成重复。
- **建议**: 删除 核心代码/tests/ 下的空占位文件；明确单一测试目录（要么统一到 核心代码/tests/ 并填入真实内容，要么删掉 核心代码/tests/ 只保留顶层 tests/），并确认 CI/容器能实际执行到真实测试。

### 🟡 [MEDIUM] fetch_commodity_yahoo.py 存在两个 __main__ 守卫，作为 scheduler 子进程运行时每次全量双倍抓取

- **单元/维度**: 采集框架与契约 · 代码正确性
- **位置**: `fetch_commodity_yahoo.py:311-315, 359-360`
- **描述**: 该文件是全库唯一含 2 个 `if __name__ == "__main__":` 块的文件（其余 94 个文件各 1 个）。第一个块(311-315)直接 `fetcher.run()`——base.run() 只 collect 不落盘、不做降级处理，结果被丢弃；第二个块(359-360)调用 `main()`，其内部又 `fetcher.run()` 一次并保存。scheduler.py:78 以子进程方式 `[PYTHON, "fetch_commodity_yahoo.py"]` 每 15 分钟运行，两个顶层 __main__ 块都会顺序执行，导致每次运行对所有 Yahoo symbol 做两遍完整抓取（含 _fetch_one 网络请求、_backfill_history / _append_history 副作用）。第一遍的采集结果不落盘、纯浪费，并使 Yahoo 请求速率翻倍，抬高 429 风险。历史 CSV 因 _append_history/_backfill_history 按日期幂等去重(203-204)不会重复写行，故非数据损坏，但双倍网络与运行时长是确定的浪费。
- **证据**: 311-315 `fetcher = CommodityYahooFetcher(DATA_DIR); fetcher.run()`；359-360 `if __name__ == "__main__": main()`；main() 内 335 `result = fetcher.run()`。Grep count 显示该文件 __main__ 命中数=2，唯一。scheduler.py:78 子进程调用该脚本。
- **建议**: 删除第一个 `if __name__ == "__main__":` 块(311-315)，只保留调用 main() 的块(359-360)。

### 🟡 [MEDIUM] data_fetcher._cache_age_days 主逻辑(_meta.last_update)因 aware/naive 时间相减抛异常被静默吞掉，新鲜度实际按数据观测日判定

- **单元/维度**: 采集框架与契约 · 代码正确性
- **位置**: `data_fetcher.py:157-172; optim_config.py:203-205`
- **描述**: _cache_age_days 优先用 cache['_meta']['last_update'] 计算年龄：`ts = datetime.fromisoformat(last_update)`；`return (datetime.now() - ts).days`。但 optim_config.now_iso_utc()（_save_cache 每次写入 _meta 用的就是它）返回 aware 时间戳（'...+00:00'），而 `datetime.now()` 是 naive 本地时间，两者相减在 Python 3 抛 TypeError，被 158-163 的 `except Exception: pass` 静默吞掉，永远走不到返回值。于是逻辑回落到条目 date 字段(165-171)——即用『数据观测日』而非『抓取时间』判定年龄。后果：(1) get_current_snapshot 的 7 天陈旧告警(646-651)对 CPI/PPI/M2 等月频序列每次都误报（观测日天然滞后数周）；(2) _is_cache_stale(max_days=3) 用于 get_china_indicator 缓存回退(423)时，中国 CPI/PMI 等月频缓存观测日恒 >3 天 → 被判定过期而拒用，即便是当前唯一可用值也返回 None。整套『_meta 写入时间』新鲜度设计属死代码。
- **证据**: data_fetcher.py:158 `ts = datetime.fromisoformat(last_update)`；:160 `return (datetime.now() - ts).days`（naive - aware）；:161-163 `except Exception: pass`。optim_config.py:205 `return datetime.now(timezone.utc).isoformat()`（aware）。_save_cache:124 每次写 `cache['_meta'] = {'last_update': now_iso_utc()}`。
- **建议**: 修正时间比较：对 last_update 用 `datetime.fromisoformat(...).astimezone(timezone.utc)` 并用 `datetime.now(timezone.utc)` 相减；并明确区分『抓取时间新鲜度』（_meta，判断是否需重抓）与『数据观测日新鲜度』（entry.date，判断数据本身多旧），二者语义不同不应混用同一函数。

### 🟡 [MEDIUM] fetch_gdelt_geo.py selftest 断言与实现矛盾，run_selftest 恒失败

- **单元/维度**: 地缘/信号类爬虫 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_gdelt_geo.py:1228-1229（实现见 _map_event_type 521-540）`
- **描述**: _map_event_type 对空/缺失 root_code 走启发式兜底（Goldstein<=-4 归 conflict，否则 political），没有任何分支返回 'unknown'（该值曾被要求消除）。但 selftest 仍断言 _map_event_type('')=='unknown' 与 _map_event_type(None)=='unknown'。_map_event_type('') 实际返回 'political'（rc 空→g=0.0→>-4→political），断言必然 AssertionError，run_selftest() 永远走不到 PASS。模块自检门形同虚设。失败场景：任何人跑 --selftest 在该行崩溃，误以为整模块坏了；CI 依赖 selftest 时永久红灯。
- **证据**: assert _map_event_type("") == "unknown"
assert _map_event_type(None) == "unknown"
# 实现: if not rc: return "conflict" if g <= -4.0 else "political"
- **建议**: 把两条断言改为与当前语义一致（_map_event_type('')=='political'、goldstein<=-4 时=='conflict'），或按新语义补齐分支断言。

### 🟡 [MEDIUM] fetch_sanctions.py / fetch_earthquake.py 在 ImportError 兜底中先用 FetcherBase 再 import

- **单元/维度**: 地缘/信号类爬虫 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_sanctions.py:65（import 在 80）；S:/world-sim/macro-scan/核心代码/fetch_earthquake.py:41（import 在 56）`
- **描述**: 两文件的 try: from optim_config import ... 失败分支里调用 FetcherBase.load_config_with_fallback(...)，但 from fetcher_base import FetcherBase 写在该 try/except 之后。一旦 optim_config 不可导入（正是两文件文档强调的'脱离部署树独立运行'场景），except 分支执行时 FetcherBase 尚未定义，抛 NameError 而非优雅回退默认配置。失败场景：在无 optim_config 的独立/测试环境运行即 NameError 崩溃，与文档承诺的'缺失时回退环境变量'相反。
- **证据**: except ImportError:
    _cfg = FetcherBase.load_config_with_fallback( ... )  # NameError: FetcherBase 尚未导入
# 下方才 from fetcher_base import FetcherBase
- **建议**: 把 from fetcher_base import FetcherBase 上移到 try/except 之前（其它同款 fetcher 如 fetch_airroutes/fetch_spacelaunch/fetch_airtraffic_opensky 都是先 import 后用，可对齐）。

### 🟡 [MEDIUM] fetch_defense_rss.py 异常路径下泄漏 os.environ 代理变量

- **单元/维度**: 地缘/信号类爬虫 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_defense_rss.py:59-67, 103`
- **描述**: _fetch_feed 通过写全局 os.environ['http_proxy']/['https_proxy'] 让 feedparser 走代理，用完在 line 65-67 pop 掉。但设置与 pop 都在 try 内、pop 在 feedparser.parse 之后；若 feedparser.parse 抛异常，控制流跳到 except（line 103），跳过 pop，代理环境变量残留在进程全局 os.environ 中。在长驻的 scheduler 进程里会污染后续所有依赖 os.environ 代理的模块（可能把本该直连的请求强行走代理，若代理不可用则连带失败）。
- **证据**: if PROXY:
    os.environ["http_proxy"]  = PROXY
    os.environ["https_proxy"] = PROXY
feed = feedparser.parse(...)  # 若抛异常，下面的 pop 被跳过
if PROXY:
    os.environ.pop("http_proxy", None); os.environ.pop("https_proxy", None)
- **建议**: 用 try/finally 保证 pop 一定执行；或不改全局 os.environ，改用 feedparser 支持的显式 handler / 每次请求传代理，避免全局副作用。

### 🟡 [MEDIUM] fetch_climate_signals.py ONI 代理沿用已废弃的 FRED_PROXY

- **单元/维度**: 地缘/信号类爬虫 · 文档漂移
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_climate_signals.py:33-35, 48`
- **描述**: _fetch_oni 用 _PROXIES（由 FRED_PROXY 环境变量构造）。fetch_firms.py 的注释明确记录过'原读 FRED_PROXY（env 不存在）→ 代理回退永久失效'并已改用 optim_config.PROXY_URL/OUTBOUND_PROXY。fetch_climate_signals 仍读 FRED_PROXY：若该 env 未设置，_PROXIES=None，ONI 只能直连，容器内直连不可达时 ONI 永远拿不到数据（静默 return {}），climate_risk 的 ONI 分量恒 0。跨模块代理配置不一致 + 旧坑复现。失败场景：部署未设 FRED_PROXY → _fetch_oni 直连 NOAA 失败 → 返回 {} → climate_risk 丢失 ONI 分量且无告警。
- **证据**: FRED_PROXY = os.environ.get("FRED_PROXY", "")
_PROXIES = {"http": FRED_PROXY, "https": FRED_PROXY} if FRED_PROXY else None
- **建议**: 与其它 fetcher 对齐：改用 optim_config.PROXY_URL（回退 OUTBOUND_PROXY），移除对 FRED_PROXY 的依赖。

### 🟡 [MEDIUM] fetch_spacetrack.py military_large_payload 的国码可能与 Space-Track SATCAT 实际枚举不匹配（假设，待核实）

- **单元/维度**: 地缘/信号类爬虫 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_spacetrack.py:130-134`
- **描述**: 军事卫星代理计数用 r.get('COUNTRY') in ('US','RUS','CHN')。据我所知（此为假设，未在本会话内核实）Space-Track SATCAT 的 COUNTRY 字段对中国用 'PRC'、对俄罗斯/独联体用 'CIS'，而非 'CHN'/'RUS'。若属实，则中俄载荷完全不计入，military_large_payload 严重低估（仅 US 命中）。明确标注为需核实的假设，不作定论。
- **证据**: mil = [r for r in all_active if r.get("OBJECT_TYPE") == "PAYLOAD" and r.get("COUNTRY") in ("US", "RUS", "CHN") and r.get("RCS_SIZE") == "LARGE"]
- **建议**: 拉一批 all_active 的 COUNTRY 去重值核对 Space-Track 实际枚举（很可能是 US/PRC/CIS 等），据实修正过滤集；对未知国码记日志，避免静默漏计。

### 🟡 [MEDIUM] fetch_safecast_nuke.py 计算 avgCPM 未按测量单位过滤，可能混单位求均值（假设，待核实）

- **单元/维度**: 地缘/信号类爬虫 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_safecast_nuke.py:126-135`
- **描述**: collect_sites 对 SafeCast 返回的每条测量直接取 value 求均值得 avgCPM，未按 unit 字段过滤。SafeCast measurements 可返回不同单位（如 cpm 与 µSv/h 等），而异常阈值 ANOMALY_CPM_THRESHOLD=100 明确假设单位是 CPM。若某站点返回混合单位，均值会把不同量纲数值混在一起，avgCPM 及 anom 判定失真。此为需核实的假设（SafeCast 该查询是否真返回混合单位、crucix 原实现是否有 unit 过滤，我均未在本会话内验证）。
- **证据**: values = [m.get("value") for m in data if isinstance(m.get("value"), (int, float))]
avg = (sum(values) / n) if n else None
... "anom": bool(avg is not None and avg > ANOMALY_CPM_THRESHOLD)
- **建议**: 核实 SafeCast measurements.json 返回结构，若含 unit 字段则只保留 unit=='cpm'（或对齐 crucix 原过滤逻辑）再求均值；对非预期单位记日志。

### ⚪ [LOW] control_server /logs 端点 fetcher_id 未走白名单（防御纵深缺口）

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `control_server.py:231-248`
- **描述**: get_logs 直接用路径参数拼 `log_file = os.path.join(LOG_DIR, f"{fetcher_id}.log")`（234 行），未做 rerun 端点那样的 _KNOWN_FETCHER_IDS 白名单校验（对比 283-297 行）。实际可利用性受限：FastAPI 默认 str 路径转换器不匹配 `/`，且强制追加 `.log` 后缀，单纯 `..` 无 `/` 无法跨目录，故常规路由下难以真正穿越。但作为防御纵深，此端点应与 rerun 一致做白名单，避免依赖框架实现细节。
- **证据**: line 234: `log_file = os.path.join(LOG_DIR, f"{fetcher_id}.log")`（无白名单）; 对比 line 295-297: `unknown = [fid for fid in fetcher_ids if fid not in _KNOWN_FETCHER_IDS]` `if unknown: raise HTTPException(...)`
- **建议**: 对 fetcher_id 复用 _KNOWN_FETCHER_IDS 白名单校验，或对参数做 `^[a-z0-9_]+$` 正则限制后再拼路径。

### ⚪ [LOW] control_server _is_public_url 对域名一律放行，存在 DNS 重绑定/SSRF 到内网风险

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `control_server.py:409-427, 445-464`
- **描述**: _is_public_url 仅在 host 为字面 IP 时做私网/回环/保留地址过滤；对域名（非字面 IP）直接 `return True`（423 行）。因此指向内网的域名（或 DNS 重绑定）会通过校验，news_title 端点随后经 NAS 代理发起请求，可能被用来探测/访问代理网络位置可达的内网主机。代码注释已承认该权衡（'DNS 后可能指向内网…那是页面自身内容'）为可接受，且该端点需 token。故列为 low。
- **证据**: line 422-423: `except ValueError:` `return True  # 域名，非字面 IP`; line 457-460: 经 ProxyHandler 用 _NEWS_PROXY_URL 发起 opener.open(req, timeout=15)
- **建议**: 如需更严，可在建立连接后对解析出的目标 IP 再次做私网校验（解析→校验 IP→按 IP 连接），或限制仅允许已知新闻域名白名单。

### ⚪ [LOW] dashboard.py 将报告/LLM/新闻衍生内容未转义注入生成的 HTML

- **单元/维度**: HTTP 服务与远程指令通道 · 安全配置
- **位置**: `dashboard.py:44-69`
- **描述**: load_latest_monthly_outlook 读取 月度简报_*.md 并做极简 markdown→HTML，把每行原文直接插入 `<p>`/`<td>`/`<blockquote>`（如 65 行 `<p ...>{line}</p>`、58 行表格单元格）而不做 HTML 转义。报告内容部分来自 LLM 输出/新闻聚合，若含 HTML/script 标签会被原样写入最终 dashboard HTML。因产物是本地静态文件、通常本地查看，风险较低；但若该 HTML 经 web 服务对外提供则成为存储型 XSS。
- **证据**: line 65: `lines.append(f"<p style='margin:2px 0;font-size:13px'>{line}</p>" ...)`; line 57-58: `cells = [c.strip() ...]` `td = "".join(f"<td ...>{c}</td>" for c in cells)`（均无转义）
- **建议**: 对注入 HTML 的文本做 html.escape 后再拼接（表格单元格、段落、blockquote 内容）。

### ⚪ [LOW] b0_migrate.norm_ts 对负时区偏移串处理错误，会拼出非法时间戳并中断整表回填

- **单元/维度**: DB 写入/RAG/迁移 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/b0_migrate.py:36-53`
- **描述**: norm_ts 判定「是否已带时区」时用 `s.endswith("Z") or "+" in s[10:] or s.endswith("+00:00")`。对负偏移串（如 '2026-08-12T10:00:00-05:00'），s[10:] 中没有 '+'，判定为「naive」，随后 append '+00:00' → '2026-08-12T10:00:00-05:00+00:00'，这是非法时间戳。backfill 里该值走 `%s::timestamptz` 转换会抛错，且 except 分支直接 `raise`（第 411-412 行），会中断整张表的回填。当前数据契约声称都是 UTC naive 或 +00:00，故实际触发概率低；但检测逻辑对负偏移不健壮。
- **证据**: b0_migrate.py:45 `if s.endswith("Z") or "+" in s[10:] or s.endswith("+00:00"):`；b0_migrate.py:50-51 追加 '+00:00'；b0_migrate.py:411-412 行级异常 `raise` 会中断整表。
- **建议**: 时区判定改为检查偏移符号更稳妥的方式，例如用正则匹配 `[+-]\d{2}:\d{2}$` 或直接尝试 `datetime.fromisoformat` 判断 tzinfo，而非字符串包含 '+'。

### ⚪ [LOW] d0_migrate_rag.dump_sql 含死代码，且 out 变量计算后从未使用

- **单元/维度**: DB 写入/RAG/迁移 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/d0_migrate_rag.py:204-211`
- **描述**: dump_sql 里 `out = DUMP_DIR / f"d0-schema-dump-{...}.sql"` 计算后，紧跟 `if not out.name.endswith("-.sql"): pass`（无操作），随后真正写入的是另一个固定名 `target = DUMP_DIR / "d0-schema-dump.sql"`。out 变量与那段 if 是无意义的死代码，会误导读者以为 D0_DATE 环境变量参与了输出文件名。
- **证据**: d0_migrate_rag.py:205-209 `out = ...; if not out.name.endswith("-.sql"): pass; ... target = DUMP_DIR / "d0-schema-dump.sql"; target.write_text(...)`。
- **建议**: 删除 out 变量与 `if not out.name.endswith(...)：pass` 死代码；若确需带日期的转储名，则真正使用 out。

### ⚪ [LOW] fetch_energy_eia.py 用 `or` 取值，合法的 0.0 观测被当作缺失丢弃

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_energy_eia.py:151`
- **描述**: `val = row.get("value") or row.get("generation")`：当某系列的 value 恰为 0.0(falsy)时，会退到 row.get("generation")(通常 None)，随后 `if val is None: raise ValueError("null value")`，导致该系列当日被标 unavailable。虽然本模块的 6 个系列(WTI价/库存/开工率/天然气库存/汽油价/净发电量)实际取 0 概率极低，但这是把『有效零值』误判为缺失的逻辑错误；负值(如 2020 年 WTI 负油价 -37)不受影响因为负数 truthy。
- **证据**: `val = row.get("value") or row.get("generation")\nif val is None:\n    raise ValueError("null value")`
- **建议**: 改为显式判空：`val = row.get("value"); if val is None: val = row.get("generation"); if val is None: raise ...`，避免 0.0 被 `or` 短路。

### ⚪ [LOW] fetch_gscpi.py 代理回退只在网络异常时触发，非 200(如 403) 直接 raise 不回退

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_gscpi.py:63-75`
- **描述**: _download() 文档承诺『直连优先，失败回退 OUTBOUND_PROXY』，但只有当 `requests.get` 抛异常(超时/连接错误)时才进入 proxy 分支；若直连成功但返回非 200(NY Fed 对爬虫 UA 常见 403/429)，代码在异常块之外的 `if r.status_code != 200: raise RuntimeError` 直接抛出，从不尝试代理。因此一类很常见的『直连能连通但被拒』场景不会走代理回退，与其它 fetcher(_get 直连 None→代理)的语义不一致。
- **证据**: `try:\n    r = requests.get(GSCPI_URL,...)\nexcept Exception:\n    if _PROXIES: r = requests.get(...,proxies=_PROXIES)\n    else: raise\nif r.status_code != 200:\n    raise RuntimeError(f"HTTP {r.status_code}")`
- **建议**: 把非 200 状态也纳入回退条件：直连返回非 200 时若配置了 _PROXIES 则用代理重试一次，再判断状态码。

### ⚪ [LOW] fetch_china_data.py derive_cpi_yoy 用位置 shift(12) 计算同比，月份有缺口时结果错误

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_china_data.py:167-169`
- **描述**: `df["value_12m"] = df["value"].shift(12)` 按行位置回看 12 行做同比，隐含假设 cpi_index.csv 为无缺口的连续月度序列。若上游(CHNCPIALLMINMEI OECD 月频)出现缺月，shift(12) 比较的将不是真正相隔 12 个月的两点，得出错误的 CPI 同比并写入 cpi_yoy.csv，进而影响下游泰勒缺口/衰退风险打分。derive_m2_yoy(shift(1) on 年度)同理但风险较低。
- **证据**: `df["value_12m"] = df["value"].shift(12)\nyoy_df = df.dropna(subset=["value_12m"]).copy()\nyoy_df["value"] = ((yoy_df["value"]/yoy_df["value_12m"])-1)*100`
- **建议**: 改为基于日期对齐(按 date 构造 period index，用 date 精确定位『去年同月』)而非位置 shift；或在计算前校验相邻行日期恰好相差约 1 个月、缺口时跳过或告警。

### ⚪ [LOW] fetch_crypto.py 快照 as_of 硬编码 None，未记录数据源时间戳

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_crypto.py:78`
- **描述**: collect() 返回 `"as_of": None`，CoinGecko markets 响应本可用 last_updated 等字段，但这里始终写 None。下游只能靠 save_json 注入的 `updated`(=落盘墙钟时间)判断新鲜度，无法区分『源数据本身的时刻』；虽然 load_previous_good 的 staleness 判定用 updated 不受影响，仍是契约字段缺失，且与 fetch_fx.py(as_of=data.get('date') 真 as-of)、commodity_yahoo(用 regularMarketTime)等不一致。
- **证据**: `return {"status": "ok", "source": "CoinGecko", "as_of": None, "coins": coins}`
- **建议**: 用响应中每币的 last_updated 取最大值填 as_of，或至少填当前 UTC；保持与其它行情 fetcher 的 as_of 语义一致。

### ⚪ [LOW] fetch_commodity_yahoo.py needs_backfill 用未关闭的 open() 计数行数

- **单元/维度**: 宏观/金融类爬虫 · 代码正确性
- **位置**: `fetch_commodity_yahoo.py:262-265`
- **描述**: `sum(1 for _ in open(csv_path))` 打开文件但不显式关闭(依赖 GC)，且未指定 encoding。随后同一 symbol 会 _backfill_history/_append_history 再次打开并 os.replace 同名文件。运行在 Linux 容器(基类 LOG_DIR=/var/log/macro-scan)时 os.replace 对有未关闭读句柄的文件可正常工作，故当前部署无功能损坏；但若代码被移植到 Windows，未关闭的读句柄会使 os.replace 抛 PermissionError。属可移植性/资源卫生问题。
- **证据**: `needs_backfill = (not os.path.exists(csv_path) or sum(1 for _ in open(csv_path)) <= 3)`
- **建议**: 用 `with open(csv_path, encoding="utf-8") as f: line_count = sum(1 for _ in f)` 确保句柄及时关闭并显式编码。

### ⚪ [LOW] entrypoint 将 API 密钥写入 /etc/environment 供从不启动的 cron 使用,且抓取清单已过期

- **单元/维度**: 调度/部署/供应链 · 安全配置
- **位置**: `S:/world-sim/macro-scan/entrypoint.sh:7-9`
- **描述**: entrypoint 用 printenv|grep 把 FRED_API_KEY、ANTHROPIC_API_KEY、OPENAI_API_KEY、NTFY_CMD_SECRET 等写入 /etc/environment(默认0644,容器内任意进程可读)。但 cron 从不启动,scheduler 直接从 PID1 继承环境,故此写入纯属多余,只是无谓扩大了密钥在文件系统的暴露面。同时该 grep 清单与 docker-compose.yml 实际注入的变量漂移:漏了 SILICONFLOW_API_KEY、OPENAI_COMPAT_KEY、CONTROL_TOKEN、WORLDSIM_APP_PW、EIA_API_KEY——若哪天真启用 cron,这些密钥又不会传给 cron 作业。
- **证据**: entrypoint.sh:8 `printenv | grep -E "FRED_API_KEY|ANTHROPIC_API_KEY|...|NTFY_CMD_SECRET|OPENAI_COMPAT_URL|OPENAI_API_KEY|USE_EXTERNAL_LLM" >> /etc/environment`;docker-compose.yml:30-39 定义 SILICONFLOW_API_KEY/CONTROL_TOKEN/WORLDSIM_APP_PW/EIA_API_KEY(不在 grep 清单)。
- **建议**: 删除写 /etc/environment 的整段(随 cron 一并移除);如确需保留,至少同步变量清单并收紧文件权限。

### ⚪ [LOW] scheduler 头部依赖关系文档与实际 JOBS 漂移

- **单元/维度**: 调度/部署/供应链 · 文档漂移
- **位置**: `S:/world-sim/macro-scan/核心代码/scheduler.py:6-18 (docstring)`
- **描述**: 文件头的『任务隐式依赖关系』时间表把 disaster 标为 05:25,但 JOBS 实际是 "I15"(每15分,见:43 及其注释『每15分』)。该依赖图也未反映后续新增的大量 fetcher 与 4 次 weak_signal(0000/0600/1200/1800)。运维据此图判断执行顺序/排错会被误导。
- **证据**: scheduler.py:8 `disaster (05:25) → [无依赖]` vs :43 `("disaster", "I15", ...)` 注释『自然灾害信号（事件档 每15分』。
- **建议**: 更新或删除该 docstring 时间表,或改为从 JOBS 自动生成,避免手工表与代码长期脱节。

### ⚪ [LOW] hybrid_llm.reason() 强制 max_tokens>=8192，覆盖 daily_narrative 传入的 300，破坏'轻量摘要节约调用'的成本控制目标

- **单元/维度**: LLM/叙事与注入面 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/hybrid_llm.py:321`
- **描述**: reason() 开头 `max_tokens = max(max_tokens, 8192)` 无条件把所有调用者的 max_tokens 抬到至少 8192。daily_narrative.generate() 明确以 max_tokens=300 调用（意图生成 <150 字的轻量摘要以'节约 LLM 调用'，见该文件模块 docstring），但被 reason() 抬到 8192，实际生成上限被放大 27 倍。输出长度虽仍靠 prompt 指令约束，但成本/延迟上限失控，与设计目标相悖；对所有短输出调用方同样生效。
- **证据**: hybrid_llm.py 第320-321行 `# 思维链模型 reasoning 消耗大量 token，强制最小值保护` / `max_tokens = max(max_tokens, 8192)`；daily_narrative.py 第345行 `narrative = reason(prompt, system=system, mode="auto", max_tokens=300)`；daily_narrative.py 模块 docstring 第7行'只做轻量摘要（节约 LLM 调用）'。
- **建议**: 把 8192 的下限仅施加于确实需要思维链的模式/调用（如 hypothesis deep 模式），或改为可通过参数关闭的 floor；短摘要类调用应尊重传入的小 max_tokens。

### ⚪ [LOW] fetch_news_titles 翻译并发数与注释/设计说明不符（代码 max_workers=12，注释称并发4）

- **单元/维度**: LLM/叙事与注入面 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_news_titles.py:92-126`
- **描述**: _translate_titles docstring 与行内注释明确写'并发 4'并据此估算耗时（'并发 4 ≈ 每轮 20 条 2-3 分钟，I120 调度内可完成'），但实际线程池是 max_workers=12。NEW_MAX=40 意味着每轮最多 40 条标题、每条一次独立 LLM 调用、并发 12，对 MiMo/硅基流动端点的速率限制与成本估算与注释严重偏离，易触发 429（该端点已知间歇性空 body，见 hybrid_llm 第232-234行注释）。
- **证据**: 第94-95行注释 '并发 4 ≈ 每轮 20 条 2-3 分钟'；第122行实际 `with ThreadPoolExecutor(max_workers=12) as ex:`；NEW_MAX=40（第50行）。
- **建议**: 统一并发数：要么将 max_workers 改回 4 与注释/速率预算一致，要么更新注释与耗时估算并确认端点能承受 12 并发；建议加简单的 429 退避（call_openai_compat 已有重试，但 12 路齐发仍可能超限）。

### ⚪ [LOW] narrative_processor 去重用 content 前缀做 LIKE 匹配，content 中的 % / _ 会被当作通配符导致误去重

- **单元/维度**: LLM/叙事与注入面 · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/narrative_processor.py:199-204`
- **描述**: ingest_article 去重查询用 `content LIKE %s` 且参数为 `content[:100] + "%"`。SQL LIKE 中 % 和 _ 是通配符，若某篇文章前100字符含 % 或 _（金融/百分比新闻极常见，如 'CPI 3.2% ...'），该前缀会被解释为通配模式，可能误匹配到不同文章从而错误地判为 duplicate_skipped，丢弃本应入库的叙事块。
- **证据**: 第199-202行 `existing = conn.execute("SELECT id FROM tianji.narrative_chunks WHERE source_id=%s AND content LIKE %s LIMIT 1", (source_id, content[:100] + "%"))`。注意此处第一个 %s 是 psycopg 占位符，第二个是 LIKE 模式；content 前缀未做 LIKE 转义。
- **建议**: 改用精确前缀比较（如 `substr/left(content,100) = %s`）或对 content 前缀做 LIKE 转义（escape % _）；更稳妥的是复用已有的 _content_hash（第113行）在 DB 侧建唯一约束/按 hash 去重，与异步 wiki 编译的 content_hash 去重策略保持一致。

### ⚪ [LOW] assess_structural_dimensions 使用模型 id 'claude-sonnet-4-6'，需核实是否为有效别名

- **单元/维度**: 第二套 Monte Carlo/评分栈 · 代码正确性
- **位置**: `assess_structural_dimensions.py:181,191,237`
- **描述**: 事实：_call_anthropic 第191行 `"model": "claude-sonnet-4-6"`，第237行 priors['assessment_model']='claude-sonnet-4-6'。推断(明确标注为不确定)：我无法从本仓库内验证 'claude-sonnet-4-6' 是否为 Anthropic 在该时点提供的有效模型别名；若该别名无效，_call_anthropic 会在第197-198行因非200状态抛 RuntimeError，导致季度结构评估失败(不过因上一条 finding，该失败当前不影响生产 MC)。这不是可从代码确证的 bug，仅提示需用权威模型清单核对。
- **建议**: 对照 Anthropic 官方模型 id 列表核实该别名；若无效改为受支持的具体 id(建议用带日期后缀的固定快照 id 以保证可复现)。

### ⚪ [LOW] compute_probit 中 dropped 变量恒为 0(死代码)

- **单元/维度**: 第二套 Monte Carlo/评分栈 · 代码正确性
- **位置**: `compute_probit.py:153-157`
- **描述**: 事实：第156行 `dropped = before_na - (before_na - int(s.isna().sum()))`。此时 s 已在第155行 dropna()，s.isna().sum() 恒为0，故该式恒等于 before_na-(before_na-0)=0。dropped 之后未被使用或打印，属无意义死代码。不影响功能(公式与黄金值自检正确：ALPHA=-0.5333,BETA=-0.5984，三锚点 -1/0/+1 → 0.5260/0.2969/0.1289 与 GOLD_VALUES 吻合)。
- **建议**: 删除该行，或改为在 ffill 前后正确统计被剔除的超限缺失行数(ffill 后仍为 NaN 的计数)再 dropna，以便日志真实反映剔除量。

### ⚪ [LOW] check_doc_drift.py 只比对 mtime，对 README/INDEX 内容漂移完全失明

- **单元/维度**: 分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim · 文档漂移
- **位置**: `S:/world-sim/macro-scan/核心代码/check_doc_drift.py:42-54`
- **描述**: check_doc_drift.py 的巡检逻辑仅遍历 *.py 并比较其 mtime 是否比 TuiYan_CHANGELOG.md 新超过 30 分钟（第 42-54 行），命中即 ntfy 告警。它不校验 README.md / INDEX.md 的内容是否与代码/VERSION 一致，也不检查 CHANGELOG 之外的文档。因此上面 INDEX 版本过期、README 计数错误这类内容漂移永远不会被这套'防漂移'工具发现。
- **建议**: 扩展巡检：对 README/INDEX 中的版本号与 VERSION、镜像 tag 与 docker-compose 做一致性断言，或至少把 INDEX/README 纳入 mtime 对比范围。

### ⚪ [LOW] optim_config.MAIN_SCRIPT 指向未挂载路径（死码地雷）

- **单元/维度**: 分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim · 代码正确性
- **位置**: `S:/world-sim/macro-scan/核心代码/optim_config.py:35, S:/world-sim/macro-scan/docker-compose.yml`
- **描述**: optim_config.py:35 定义 MAIN_SCRIPT = os.path.join(WORKSPACE, '核心代码', 'run_macro_analysis.py')，生产 OPENCLAW_WORKSPACE=/workspace，故解析为 /workspace/核心代码/run_macro_analysis.py。但 docker-compose.yml 把代码挂载在 /app（核心代码→/app），/workspace 下只挂了 data/docs/知识库/config，并无 核心代码 子目录——该路径在容器内不存在。grep 确认 MAIN_SCRIPT 目前无任何 import/调用者（仅定义处一处），故当前不触发故障，但一旦有人开始使用它就会指向不存在的路径。相较之下 DATA_DIR/KNOWLEDGE_BASE 等其余 WORKSPACE 派生路径都对应了实际挂载卷，属正确。
- **建议**: 删除未使用的 MAIN_SCRIPT，或把它改为基于 __file__ 定位（与代码同目录），避免 /workspace/核心代码 这一未挂载路径。

### ⚪ [LOW] optim_config.py 分叉：macro-scan 版 DATA_DIR 回退依赖 __file__，与 macro-ji 的 P0-D 红线相反

- **单元/维度**: 分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim · 架构一致性
- **位置**: `S:/world-sim/macro-scan/核心代码/optim_config.py:8-24, S:/world-sim/macro-ji/optim_config.py:10-12`
- **描述**: 两份 optim_config.py 大幅分叉（ji 21 行 / scan 210 行），这是有意的：macro-ji 版自述为'天玑容器精简路径模块'，只声明最小常量，并显式注释 'DATA_DIR 显式指向挂载卷…绝不用 __file__ 推导（防落非持久卷，P0-D 同族红线）'，硬编码 /app/macro_data。macro-scan 版则 WORKSPACE=os.environ.get('OPENCLAW_WORKSPACE', <__file__ 双层 dirname 派生>)、DATA_DIR=WORKSPACE/data。生产 docker-compose 设了 OPENCLAW_WORKSPACE=/workspace，故 DATA_DIR=/workspace/data 命中持久卷、当前正确；但其 __file__ 回退分支正是 macro-ji 明令禁止的模式——若环境变量缺失，数据会落到 /app（代码热挂载区）而非持久 data 卷。两份对同一红线采取相反策略，属设计一致性隐患而非当前 bug。
- **建议**: 统一路径纪律：macro-scan 版也移除 __file__ 回退（缺 OPENCLAW_WORKSPACE 时直接 fail-loud），或在文档中明确两容器路径策略差异的理由，避免后续维护者误以为两份可互换。

### ⚪ [LOW] adapter.py 自测代码用 2 元组，与 docstring/生产端 3 元组契约不符

- **单元/维度**: 采集框架与契约 · 项目合理性
- **位置**: `adapter.py:55-77,128-132; scorer.py:136`
- **描述**: map_risk_scores docstring 声明入参为 `(风险等级, 分数, 信号列表)` 三元组，取 recession[1] 作分数——生产端 scorer.py 的评分函数确实返回 `(label, score, signals)` 三元组（scorer.py:136/205/313/424），run_macro_analysis.py:2861 传入的正是这些三元组，故生产路径正确。但 adapter.py __main__ 自测(128-132)用的是 `test_recession = (45, [...])` 二元组，此时 recession[1] 取到的是信号列表而非分数，返回的 risk dict 里 'recession' 字段会是一个列表，且 `max(rec_score or 0, inf_score or 0)` 变成两个列表比较。该自测因此产出错误/误导结果，无法起到回归保护作用（虽不影响生产）。
- **证据**: adapter.py:70 `rec_score = recession[1] if ... len(recession) > 1 else None`；docstring:57-59 `('中', 45, [...])`；:128 `test_recession = (45, ["信号1", "信号2"])`（二元组）。scorer.py:136 `return label, score, signals`。
- **建议**: 将 __main__ 自测数据改为三元组，例如 `test_recession = ('中', 45, [('信号1',1.2)])`，与 docstring 及 scorer 实际返回形状对齐，恢复自测的守护价值。

### ⚪ [LOW] fetch_disaster_signals.py 文档称 M≥5.0 但实际拉 2.5_day feed 且 event_count 计入全部

- **单元/维度**: 地缘/信号类爬虫 · 文档漂移
- **位置**: `S:/world-sim/macro-scan/核心代码/fetch_disaster_signals.py（USGS_M25_URL 使用处与 print 文案）`
- **描述**: 文件头与运行时 print 称'拉取重大事件（M≥5.0级别）'，实际请求 2.5_day feed（含 M2.5+）。评分对 mag<5.0 返回 0，但 event_count_24h 计入所有 M2.5+ 事件，与'重大事件'措辞不符，易让读该字段者误解事件量口径。
- **证据**: USGS_M25_URL = ".../2.5_day.geojson"；print("...M≥5.0级别...") 与 event_count_24h = len(events) 口径不一致
- **建议**: 统一口径：要么文档改为'M≥2.5 feed，评分仅对 M≥5.0'，要么 event_count_24h 只统计 score>0 或 mag>=5.0 的事件。

---

## 5. 分模块小结

### 第一波

**infra + sql + 部署** — 脚本整体质量不错：关键脚本均带 set -e（部分 set -euo pipefail）、部署脚本反复强调幂等、密钥经 .gitignore 排除且 compose 用变量占位而非明文、PG 正确绑定 127.0.0.1。但存在若干可导致静默失败或部署错版本的问题：备份脚本在 pg_dump 失败时会留下损坏 dump 且无完整性校验；deploy-pg.sh 用 Python repr 拼口令进 SQL 字面量、含特殊字符会出错且被 || true 吞掉；deploy-pg.sh 号称幂等可重跑但角色/授权/建库仅在容器首次创建时执行；macro-scan/deploy.sh 的 --build 从模板取到 v7 标签与真实 compose 的 v8 不一致会部署到旧镜像。SQL schema 基本合理（主键/唯一/索引齐全），但只读角色 worldsim_ro 对 B0 业务 schema 无读权限。

**kaiyang 前端逻辑** — 整体代码质量高：适配层普遍遵循 K4（坐标必须有限数）/K5（任何路径不抛异常）红线，统一 XSS 转义（mapData/markdown/newsGeo 三道防线），schema_version 校验与降级矩阵完备，状态管理用 reducer+纯函数便于测试。主要问题集中在两个地理适配器的坐标校验与其余适配器不一致（NaN 可穿透），以及 ControlContext 日志持久化的冗余/瞬时覆盖。未发现会导致崩溃或数据永久损坏的严重缺陷。

**kaiyang 构建/部署/配置** — 构建配置整体合理：base 用相对路径便于任意子路径挂载、manualChunks 分包、standalone 单文件方案设计清晰、nginx 缓存策略与 /data/ 隔离考虑周到。.env.local 已被 .gitignore（*.local）正确忽略且从未进入 git 历史，当前 dist 也未内联出 token（已 grep 验证）。主要风险集中在两点：控制 API bearer token 走 VITE_ 前缀注入会被打进客户端产物的设计缺陷；以及 standalone 产物目录未纳入 .gitignore，二者叠加可能导致带明文 token 的可分发单文件被提交。另有一个跨平台依赖锁定问题会影响 Windows 开发机的 npm 安装。

**macro-ji 校准与验证** — 该单元实现天玑的预测验证与权重校准闭环（L1 FRED/L2 关键词/L3 LLM 三级判定 + 贝叶斯路径权重更新 + 玉衡权重矩阵健康检查）。整体防未来函数、原子写、幂等性意识良好，历史审查修复痕迹清晰。但存在一个静默破坏权重持久化的类型错误（Path+str），以及若干正确性/一致性缺陷；另有 verify_geo_auto 被 cron 调度与 tianji_verifier 文档声称"从未被调度"矛盾的架构漂移。

**macro-sim Agent 与 LLM 层** — Agent 决策框架（soul 派系 + 规则 fallback + LLM 试点）结构清晰、错误处理普遍 fail-soft，安全上无 API key 泄露（key 走环境变量/文件，日志只截断 raw 输出）。但存在若干 correctness 与可观测性问题：一处确定的 NameError（连通性自检 CLI 直接崩溃）、sovereign.py 用旧版 _eval_trigger 遮蔽了 base 的修复版、LLM 决策来源标注在回退到 soul 时被错误标为 "llm"、以及 use_llm 在缺少 LLMPilotMixin 的多数 Agent 上被静默忽略导致"混合引擎"被当作纯 LLM 运行。多数问题修复成本低但影响推演结果的可解释性与验证有效性。

**macro-sim 核心推演逻辑** — 核心引擎的状态演化、传导矩阵（per-agent delta 修复）、除零守卫（vix_baseline/denom）、随机可复现（每 run 固定 seed + 深拷贝 agent 模板）总体设计严谨，且有大量 CHANGELOG 追溯的守卫与探针。但发现一处明确影响推演结果的边界条件 bug（Monte Carlo 初始扰动把 market_sentiment 钳到 [0,1]，抹掉所有悲观起点），以及数处架构/漂移问题：外生事件注入层完全未接线、分叉检测结果未参与聚类、credit_spread/t10y2y 无均值回归导致出血无界漂移、预测期 dff 冻结。这些多为设计层缺口而非崩溃点。

**macro-sim 输出/持久化/治理** — 编排入口 run.py 的主流程（校准→预测→报告→轨迹JSON→sim_history JSONL→PG存档→ntfy）结构完整，异常处理普遍采用"告警不阻断"并对 PG 事务失败做 rollback+连接自愈，DB 落表用确定性主键与 scenario 去重，纪律良好。但发现若干真实缺陷：readable 兜底模板把 agent-id 当动作翻译（正是模块要杜绝的代号泄漏）；chronicler 文档承诺的数字防幻觉校验实际未实现（相关函数为死代码）；narrative_format 在多标签时静默丢弃首个标签前的正文。另有 PG 连接缓存被 finally 关闭抵消、死参数/死代码等一致性问题。注意：审计任务描述的 sim_log.db 实际为 0 字节空文件，持久化已全面迁移到 Postgres tianji schema。

**安全与密钥专项** — 整体密钥卫生基本达标：真实 .env（macro-ji/.env、macro-sim/.env、kaiyang/.env.local）均被 .gitignore 命中且从未进入 git（git log -S 验证 SILICONFLOW key、.env 增删历史均为空）；所有 docker-compose.yml 用 ${VAR} 插值，无明文高价值密钥；deploy.sh 无硬编码凭据；控制 API 的 /rerun 端点用白名单+列表参数 subprocess.Popen，无命令注入；_check_token 已做 fail-closed。主要问题集中在：一个仍在生效的 FRED_API_KEY 明文散布在多个受版本控制的源码/文档中，一处 Postgres 密码写进受追踪文档，.gitignore 与实际追踪状态不一致，以及前端 VITE_ 前缀 token 会被打进客户端 bundle 的设计弱点。

**文档与现实漂移** — STATUS.md（权威交接文件）与代码高度吻合——逐条核对 governance.py、world_state.py:295/345、bifurcation.py 的 PathResult.monthly_grv_std 与 _ACTION_CRITERIA、run.py 的 _write_grv_trajectory、simulation.py 的 grv 增量注入、agents.yaml=20 个 agent、macro-scan 的 tianxuan_grv_export.py、kaiyang 的 tianxuanGrv feed，均真实存在，未发现"声称完成实则未实现"。漂移集中在导航层文档（README.md / docs/overview.md）：版本号大面积过时且 overview 内部自相矛盾、agent 数写错、指向已迁移或已删除对象的过时描述。多数版本行有"本行仅导航不断言版本"的对冲声明，降低了严重度，但仍存在未对冲的事实性错误。

**跨模块架构与数据契约一致性** — 前向 GRV 轨迹链（macro-sim *_grv_traj.json → 天枢 tianxuan_grv.json → 开阳 TianxuanGrvRaw）与校验链（write_tianji_trigger → macro-ji watchdog → tianji_summary_export → 开阳）三方字段严格对齐，且"天枢是开阳 feed 唯一产出方"的三段链权责边界清晰、有 M4 保旧值护栏，是本系统的架构亮点。主要问题集中在权威契约文档 DATA_CONTRACT.md 与真实产出/消费之间的漂移：新闻 feed 名与字段名不符、schema_version 键名双轨制、feed 注册表滞后。这些当前被消费侧的容错逻辑掩盖，未造成运行崩溃，但削弱了"契约作为权威标准"的可信度。

**项目合理性与发展前景** — world-sim 是一个单人、家用 NAS 上的个人宏观推演系统（STATUS 明确「非商业产品」），四层管线（天枢观测→天璇仿真→天玑验证→开阳展示）的模块划分本身清晰合理。但战略层存在三个结构性隐忧：(1) 系统的核心价值闭环——预测→Brier 验证→权重反哺——至今从未在真实数据上跑通，且因预测到期日全在 2027-02 之后，其预测有效性在近一年内无法被检验；(2) 赋予系统身份的旗舰能力「LLM 推演」在全部 19 个 agent 中零实现，且其定位在数天内基于一个后被证伪的成本前提反复翻转；(3) 架构治理与文档机器的复杂度（七星命名、多份 ADR/评审/OPEN-DECISIONS 体系、SQLite→PG 四天迁移仪式）与一个未经验证的核心、单人维护体量严重不匹配。这是一个能产出有说服力叙事的报告引擎，但其作为「预测系统」的科学价值尚未被任何证据支撑。

### 第二波（macro-scan/核心代码）

**HTTP 服务与远程指令通道** — 审了 4 个文件。control_server 已做过一轮安全加固（token fail-closed、CORS 收窄、rerun 白名单、SSRF 公网校验、SQL 参数化、PG UPDATE 加 status 守卫防 TOCTOU），整体质量高。主要残余问题集中在两处：(1) ntfy_listener 通过公共 ntfy.sh 主题接收指令，密钥可选（未设即 fail-open）且明文随消息发在世界可读的主题上——这是四文件里最强的攻击面，且未像 control_server 那样被加固；(2) web_server 完全无鉴权且前端用 innerHTML 拼接含外部新闻来源的字段（DOM-XSS）。control_server 的 token 比较非恒定时间。指令触发均用 argv（无 shell=True）+ 白名单，未发现命令注入/RCE。所有 severity 证据均来自实际读到的代码行。

**DB 写入/RAG/迁移** — 审阅了 macro-scan 的 PG 双写、RAG 索引构建与 SQLite→PG 迁移路径。未发现 SQL 注入（所有动态拼接的表名均来自硬编码常量表，值均走参数占位符）。发现 1 个高危确定性 bug：RAG 索引原子重建用了非法的 `TRUNCATE ... WHERE`，导致知识库重建路径必然失败。另发现 b0_migrate.py 内嵌 DDL 与权威 sql/03_b0_schema.sql 已产生 schema 漂移（缺 action_key/human_note，且有运行时消费者依赖这两列），以及 _next_id 的 MAX+1 与"独立子进程双写"注释相互矛盾、并发下可能静默丢行。事务/异常兜底整体设计稳健（双写旁路不阻断主流程、_build_index_pg 用事务包裹）。

**宏观/金融类爬虫** — 审阅了 13 个宏观/金融采集脚本 + 共享基类 fetcher_base.py。整体架构较成熟：统一 FetcherBase 提供限速/重试退避(429/5xx重试,4xx不重试)/原子写/良值保留(_is_good+staleness上限)/降级不 crash，多数 fetcher 遵循"直连优先→代理回退→降级保留旧值"模式。发现的最重要问题是一组一致的 NameError 隐患：5 个 fetcher 在 optim_config 缺失时的回退分支里、在 import FetcherBase 之前就引用了它，会把本应优雅降级的配置回退变成硬崩溃。其次 fetch_commodity_yahoo.py 因合并残留有重复的 main()/__main__，运行脚本会对 Yahoo 全量 symbol 拉取两遍。其余为健壮性/数据漂移类问题。未发现密钥泄露(key 均走 env/optim_config,不硬编码)或 RCE。

**调度/部署/供应链** — 审了 macro-scan 的调度与部署链。发现两处高危：(1) 月度预测校验 verify_predictions.py 在实际运行的 Python 调度器里根本没有作业项，而它只存在于已废弃、从未被 entrypoint 启动的 crontab 里——对一个预测系统而言意味着 Brier/校准从不自动更新；(2) deploy.sh --build 从 docker-compose.example.yml 取镜像 tag(v7)构建，而线上 docker-compose.yml 期望 v8，新构建的镜像被忽略。中危集中在供应链(非官方镜像源 docker.1ms.run 无 digest 钉扎、pip 无 hash 校验+部分依赖未钉上界、随仓库携带的 wheel 无校验)、双份互相矛盾的调度真相源、C7 重启恢复恢复错了 dict 导致失效、以及无重叠锁/轮询式整点匹配的健壮性缺口。构建期未发现密钥泄露(代码走 volume 挂载、无 .env/key.txt COPY、无 ARG 密钥)。docker-compose.yml 用 ${VAR} 占位且被 .gitignore 排除，无明文密钥入库。

**LLM/叙事与注入面** — 审查了本单元 10 个 Python 文件 + 1 个 system prompt。整体架构成熟（降级链、原子写、SSRF/token 校验、content_hash 去重、锁内 TOCTOU 防护都到位），但发现一个明确的缩进 bug 导致 SQLite/PostgreSQL 双写发散并向姊妹推演引擎持续注入虚假"叙事密度突增"信号（high）。此外存在两处 LLM 注入面（不可信外部文本→prompt）、一处 PG 读取被 SQLite 文件存在性错误门控（在 PG-only 部署下会丢失全部新闻输入）、以及若干 token/成本控制与注释漂移问题。未发现密钥泄露或 RCE：subprocess 用列表参数无 shell 注入，SQL 全部参数化，日志不打印 Authorization 头。所有 finding 均基于实际读到的代码行，未臆测 ABAP/对象名。

**第二套 Monte Carlo/评分栈** — 审读了 macro-scan 天枢的第二套 MC/评分栈 9 个文件。核心问题是"双引擎分叉"：生产路径(run_macro_analysis→run_monte_carlo_compat→monte_carlo_v2)与功能最丰富的 mc_engine.run_monte_carlo(v1 GBM)并存，而后者已成死代码——导致结构层季度 LLM 评估(assess_structural_dimensions)、GDELT 地缘调制、以及仿真内反馈回路放大全部无法进入生产衰退概率输出。另发现 v2 衰退概率定义与文档口径不符(把"任意≥2个负增长月"标注成"连续2季度")、c0 权重归一被下限钳位吞掉、GARCH omega 与 sigma 种子严重不一致。compute_probit / brier_calc / compute_fci 数值实现基本正确、可复现(全部 seed=42)。与 macro-sim(天璇)属不同范式(LLM 智能体参数校准 vs 数值波动率校准)，无直接代码冲突，但两套"校准"无共享真源。以下按严重度排列。事实与推断已分别标注。

**分叉副本/文档漂移/合理性 — macro-scan/核心代码 vs macro-ji vs macro-sim** — 对比核实了 macro-scan/核心代码 与 macro-ji 的 5 个同名模块：verify_predictions.py 与 verify_geo_auto.py 逐字节相同（无分叉，仅双份维护风险）；tianji_db.py / weight_matrix.py / optim_config.py 已分叉且行为不同。最重要的发现是 tianji_db.py 与 weight_matrix.py 在两处都仍被 import 使用、且已分叉（"必须同步"契约已破），INDEX 却称这些模块"已迁出"——实际是复制而非迁移，形成 split-brain。文档漂移多处坐实：INDEX 版本 v3.8.15/镜像 v7 与实际 VERSION 3.8.24/compose v8 不符；README 声称"48个.py"实为 116 个；世界推演系统 README 称"两个系统"实为四子系统。核心代码/tests/ 有 3 个 0 字节空测试文件，与顶层 tests/ 里的真实同名测试重复。三系统（天枢采集/天璇仿真/天玑验证）职责划分本身清晰合理，问题出在迁移只做了一半、遗留分叉副本双活。所有 evidence 均来自实际读到的代码/文件，未臆测。

**采集框架与契约** — 审阅了采集基类、遗留数据获取层、契约模块与告警配置。核心发现：contracts.py 这套精心设计的跨指标统一契约（IndicatorPoint/IndicatorEnvelope）在整个代码库中零采用——除自身外无任何生产者 import 它；它文档里点名要修的 schema_version 语义错位，在实际生产者 compute_fci.py / compute_probit.py 里依旧原样存在，且两个生产者的 schema_version 约定互相矛盾。此外发现 fetch_commodity_yahoo.py 有重复 __main__ 守卫导致每次运行双倍抓取，data_fetcher.py 缓存新鲜度主逻辑因 aware/naive 时间相减异常被静默吞掉而失效。FetcherBase 的错误降级/原子写/保留良值机制本身设计合理，子类（collect 覆写、_is_good 覆写、main() 中 load_previous_good 降级）继承正确，未见破坏基类契约的子类。注：config/ 目录在该路径下不存在。

**地缘/信号类爬虫** — 通读 17 个文件（全部实读）。最严重是 fetch_spacetrack.py 把真实邮箱+明文密码作为默认值硬编码在源码里（密钥泄露），fetch_firms.py 同样硬编码 NASA API key。逻辑层面：fetch_gdelt_geo.py 增量拉取把 last_success_slot 记成"最旧"槽而非"最新"，导致每次运行重复拉取已抓过的槽（靠 event_id 去重才没造成数据重复），同文件 selftest 断言 _map_event_type("")=="unknown" 与实现（返回 political/conflict）矛盾使 selftest 恒失败。fetch_sanctions.py 与 fetch_earthquake.py 在 ImportError 兜底分支里先用 FetcherBase 再 import，独立运行时会 NameError 崩溃而非优雅降级。fetch_defense_rss.py 在异常路径下泄漏 os.environ 代理变量。fetch_climate_signals.py 沿用兄弟模块已明确弃用的 FRED_PROXY。etl_ged.py 工程质量很高，未发现实质缺陷。按用户规则区分事实与假设：Space-Track 国码、SafeCast 单位两项标注为待核实假设。

## 6. 完整性复核

第一波的完整性复核 agent 发现了本次最大盲点——`macro-scan/核心代码` 未审——该缺口已由第二波闭合。第一波复核原文：

<details><summary>复核意见 1</summary>

基于对仓库结构的实际扫描，以下是我认为被遗漏或审得不够深的补充审计点（均基于我实际 `ls` 到的文件/目录，非推测）：

1. **kaiyang 前端运行时逻辑完全未审** — 只审了 build/deploy，而 `kaiyang/src/` 下的 `control/`（控制 API 客户端）、`lib/`（airRoutes/geoAggregate/health/newsGeo/nuclear/sdr/space/thermal/layerContract/mapData 等十余个数据适配器）、`state/`、`hooks/`、`panels/` 这些真正处理 feed→可视化的转换逻辑一条都没查。

2. **macro-scan 模块被当"纯 markdown"跳过，实为完整数据采集服务** — 它有 `核心代码/`、`Dockerfile`、`deploy.sh`、`crontab`、`entrypoint.sh`、`sql/`，以及 fetch_airtraffic_opensky/fetch_bdi/fetch_commodity_yahoo/fetch_fao/sanctions_bulk 等外部 API 抓取代码，从未作为独立审计单元覆盖。

3. **macro-scan 存在重复代码树** — 顶层 `tests/` 与 `核心代码/tests/` 并存（如 test_fetch_airtraffic_opensky.py、test_fetch_commodity_yahoo.py 两处各一份），这是一个明显的 drift/soundness 隐患，无任何单元提及。

4. **测试覆盖维度整体缺席** — macro-sim/tests(5个)、kaiyang(18个 .test)、macro-scan/tests 都存在，但没有任何单元评估这些测试是否真能跑、是否覆盖已发现的关键 bug（如 Monte Carlo 钳位、NameError），且我未找到 pytest.ini/vitest.config，测试是否接入 CI 存疑。

5. **macro-sim/core 三个文件未出现在核心摘要中** — `backtest_eval.py`、`consistency_validator.py`、`board_baseline.py` 未被点名，而前两者恰恰与 project-soundness 提出的"预测验证闭环从未跑通"直接相关，值得单独核实其实现是否为死代码。

6. **souls 与 agents 数量不匹配** — `souls/` 只有 12 个派系 YAML，而 `config/agents.yaml` 按文档是 20 个 agent，这些驱动决策的 soul/persona 定义内容本身（触发条件、派系逻辑）未被审，且数量缺口未被解释。

7. **remote-command 控制通道的命令面与鉴权深度不足** — 安全单元只把 ntfy token 比较列为低危，但未深查 `kaiyang/src/control/` 与后端 control server 实际能执行哪些远程指令、命令白名单/越权面，考虑到它通过公共 ntfy 主题接收指令，这条链的攻击面值得单独评估。

8. **backups/ 目录与各模块 Docker 构建配置未查** — 根目录 `backups/2026-08-10-kaiyang-upgrade/` 是被提交的历史快照（可能含内嵌 token 的 dist 产物，正是 build-deploy 单元担心的泄露形态），且 macro-sim/macro-ji/macro-scan 各自的 Dockerfile 与 docker-compose（基础镜像版本、build args、构建期密钥）未纳入 infra-sql 审计范围。

</details>

<details><summary>复核意见 2</summary>

已用 Read/ls/diff 核实。核心发现：审核把 macro-scan 当成"markdown 知识库"，但 `S:/world-sim/macro-scan/核心代码/` 实际是一个约 100 个 Python 文件的采集/推演引擎，几乎完全未被审计。以下是我认为还需补审的点（按重要性排序，均基于实际读到的目录与 diff，非臆测）：

1. **macro-scan 采集引擎主体未审（最大遗漏）**：`S:/world-sim/macro-scan/核心代码/` 有 50+ 个 `fetch_*.py` 外部 API 爬虫（opensky/yahoo/fred/gdelt/spacetrack/crypto/earthquake 等）+ `data_fetcher.py`/`fetcher_base.py`，这些是"天枢"数据的真正源头，审计单元里只在 cross-module 边界碰了 `grv_threshold.py`，爬虫的错误处理/限流/数据质量/密钥基本没查。

2. **macro-ji 与 macro-scan/核心代码 存在同名模块双份且已分叉**：`verify_predictions.py` 两处逐字节相同（复制），但 `weight_matrix.py` 和 `tianji_db.py` 两处 `diff` 显示**内容不同**——同一逻辑两份副本已漂移，macro-ji 审计只看了 ji 侧，scan 侧分叉副本未查，哪份权威、是否行为不一致需核实。

3. **测试覆盖维度整个没作为单元审过**：`macro-sim/tests/` 有 5 个测试文件、`macro-scan/tests/` 与 `macro-scan/核心代码/tests/` 有采集测试，但 **`macro-ji/` 下没有任何 tests 目录**（仅 `__pycache__`）——即"科学闭环从未跑通"的验证/校准核心恰恰零测试，这一事实与 project-soundness 结论直接相关却未被量化。

4. **macro-scan 自带的第二套仿真/评分引擎未审**：`核心代码/` 内有 `mc_engine.py`/`monte_carlo_v2.py`/`calibrate_mc.py`/`compute_probit.py`/`brier_calc.py`/`compute_fci.py`——一套与 macro-sim（天璇）平行的 Monte Carlo + 评分栈，是否与 macro-sim/macro-ji 的口径重复或冲突从未核对。

5. **macro-scan 的两个 HTTP 服务未纳入安全审计**：`核心代码/control_server.py` 与 `web_server.py` 是暴露的 HTTP 服务，security-secrets 单元只提到"控制 API /rerun 端点白名单"，需确认那指的是 kaiyang 侧还是这两个 server，scan 侧服务的鉴权/注入面可能被漏。

6. **不可信抓取文本→LLM prompt 的注入面未查**：`fetch_news.py`/`fetch_rss_news.py`/`fetch_defense_rss.py` 抓的外部文本流入 `hybrid_llm.py`/`hypothesis_engine.py`/`daily_narrative.py`/`narrative_processor.py`（配 `system_prompt_hypothesis.md`），prompt injection 与 KB 写回（`update_kb_numbers.py`）的完整性未评估。

7. **macro-scan 内嵌的 DB 迁移/写入与 RAG 层未随 infra-sql 一起审**：`b0_migrate.py`/`d0_migrate_rag.py`/`pg_write_collection.py`/`pg_write_indicators.py`/`build_rag_index.py`/`rag_engine.py` 是散落在应用代码里的 schema 迁移与写库逻辑，infra-sql 单元审的是 `sql/`+`infra/pg`，这些很可能没覆盖。

8. **依赖/供应链与调度编排未审**：`macro-ji/requirements.txt`+`Dockerfile`、`macro-scan/wheels/`（内置 wheel，供应链来源）以及 `核心代码/scheduler.py`+`ntfy_listener.py`（cron/调度层，正是 verify_geo_auto 漂移的所在）——依赖钉扎/漏洞与整体作业调度的重叠/失败处理均未作为维度审查。

（说明：第 1–5、7–8 点的文件清单来自我对 `S:/world-sim/macro-scan/核心代码/` 的直接 `ls`；第 2 点的"已分叉"来自实际 `diff` 输出；"未审"是依据你给出的审计单元清单推断。）

</details>

## 7. 优先级行动清单

**立即（安全）**
- 移除源码中所有硬编码凭据（Space-Track 密码、NASA FIRMS key、ntfy 口令 1900），改走 env/密钥文件；轮换已泄露凭据。
- ntfy 指令通道：强制要求口令、改 hmac.compare_digest、迁离公共 ntfy.sh 或改签名+时效方案；web_server 加鉴权、修复 innerHTML DOM-XSS。

**高优先（正确性/闭环）**
- 修 5 个 fetcher 的 NameError 回退顺序；修 RAG 重建的非法 TRUNCATE...WHERE；修 LLM 叙事缩进 bug 导致的 SQLite/PG 发散虚假信号。
- 把月度预测校验接入实际 Python 调度器，恢复 Brier/校准自动更新；对齐 deploy.sh 构建 tag(v7→v8)。

**中期（架构/技术债）**
- 收敛 split-brain：确定 tianji_db/weight_matrix 权威副本，删除分叉；决定 contracts.py 采用或删除；二选一保留 Monte Carlo 引擎、清死代码。
- 供应链：镜像 digest 钉扎、pip hash 校验、依赖上界。

## 8. 说明
- 验证轮两波合计 0 refuted：发现的事实依据经独立复核均成立。severity 个别调整已在对应条目体现（如 ntfy 由 critical 下调 high——触发需先知私有主题名、无 shell 注入；macro-ji 缺排序下调 medium 防御性缺陷）。
- 本报告覆盖全部模块。RAP 领域/知识库内容(markdown)未做代码级审计（无可执行逻辑）。

---

## 9. 测试专章：现状审计 + 回归测试 + CI 门禁

本章是审计之后追加的一轮独立工作：**审现有测试 → 补回归测试 → 接 CI**。所有 pytest 结果均在本机 venv（`PYTHONUTF8=1`）真跑取得，非静态推断。

### 9.1 现有测试地面真相（真跑，非推断）

| 模块 | 框架 | 测试量 | 结果 | 备注 |
|---|---|---|---|---|
| kaiyang（开阳） | vitest | 20 文件 / 364 用例 | ✅ 全绿（≈217s） | 唯一有实质断言覆盖的模块 |
| macro-sim（天璇） | pytest | 56 用例 | ✅ 全绿（≈9s） | core 覆盖率 ≈21% |
| macro-ji（天玑） | — | **0** | ⚠️ 零测试 | 校准/验证子系统完全无测试 |
| macro-scan（天枢）`tests/` | pytest | opensky+bdi+fao = 7 | ✅ 绿 | 见下方质量问题 |
| macro-scan（天枢）`tests/` | pytest | commodity_yahoo = 4 | ❌ **可复现挂起** | `collect()` 中 `requests.get` 未被 mock 拦截而真实发起 → 无限挂起 |
| macro-scan `核心代码/tests/` | — | 3 文件 **0 字节** | ⚠️ 空壳 | `test_fetch_airtraffic_opensky` / `test_fetch_commodity_yahoo` / `test_sanctions_bulk` 均为空占位 |

### 9.2 现有测试的质量问题（本轮新发现）

1. **macro-scan 的 fetcher 测试零断言**：`test_fetch_bdi / fao / opensky / commodity_yahoo` 四个文件全部用自定义 `check(cond, msg)` 打印 PASS/FAIL，**没有一条 `assert`**，只在 `__main__` 里 `sys.exit(1)`。在 pytest 下无论逻辑对错都报绿——**是"看起来有测试"的假绿**，几乎没有回归保护价值。
2. **中文 print 在非 UTF-8 locale 崩溃**：测试与源码大量中文 `print`，在 cp1252/ascii 控制台会 `UnicodeEncodeError`。CI 必须全局设 `PYTHONUTF8=1`（本章 CI 已设）。
3. **yahoo 测试挂起会拖死 CI**：`test_fetch_commodity_yahoo` 的挂起可复现，CI 必须 `--ignore` 该文件并加 `pytest-timeout` 兜底，否则 job 永不返回。

### 9.3 新增回归测试（13 个，对准 critical/high 发现）

针对第 2 节的 critical/high 发现各写一个**回归测试**。约定：**已知 bug 用 `@pytest.mark.xfail(strict=True)`（vitest 用 `it.fails`）断言【修复后】的正确行为**——

- bug 仍在 = `xfail`（CI 绿，不阻塞）；
- bug 被修好 = `xpass` 触发 `strict` 失败，**强制开发者摘掉标记**，测试自动转为活体回归守卫。

这样测试从写下那一刻就锁定了正确契约，且不会因"当前是坏的"而阻塞 CI。

| 测试文件 | 框架 | 覆盖发现 | 断言的正确契约 | 本机结果 |
|---|---|---|---|---|
| `macro-ji/tests/test_audit_ji_path_str.py` | pytest | #4 | `update_path_weights` 写回时 `calibration_score` 真正落盘（非 `Path+str` TypeError 被吞） | ✅ xfail |
| `macro-sim/tests/test_audit_sim_sentiment_clamp.py` | pytest | #9 | `_add_initial_noise` 保留 `market_sentiment` 的 [-1,1] 语义域（不钳到 [0,1]） | ✅ xfail |
| `macro-scan/tests/test_audit_scan_rag_truncate.py` | pytest | #12 | RAG 重建不用非法的 `TRUNCATE … WHERE`（应为 `DELETE`） | ✅ xfail |
| `macro-scan/tests/test_audit_scan_scheduler_verify.py` | pytest | #13 | 调度器 JOBS 含月度预测校验作业 | ✅ xfail |
| `macro-scan/tests/test_audit_scan_narrative_indent.py` | pytest | #15 | 阈值未触发时 PG 密度标记 upsert 不被调用（与 SQLite 分支一致） | ✅ xfail |
| `macro-scan/tests/test_audit_scan_mc2_recession.py` | pytest | #17 | 衰退判定按"连续"口径：2 个不相邻负月不算衰退 | ✅ xfail |
| `macro-scan/tests/test_audit_scan_c0_weightfloor.py` | pytest | #18 | 同 target_type 派生权重之和 ≈ 1.0（floor 钳位不破坏归一） | ✅ xfail |
| `macro-scan/tests/test_audit_scan_gdelt_slot.py` | pytest | #22 | 增量状态记最新槽（max）而非最旧槽 | ✅ xfail |
| `macro-scan/tests/test_audit_scan_secrets_guard.py` | pytest | #1 #3 #21 | 源码无硬编码真实凭证默认值（Space-Track / FIRMS / FRED） | ✅ xfail |
| `macro-scan/tests/test_audit_scan_ntfy_failopen.py` | pytest | #10 #11 | `NTFY_CMD_SECRET` 空时 `parse_command` fail-closed（拒绝命令） | ✅ xfail |
| `macro-ji/tests/test_audit_scan_splitbrain.py` | pytest | #19 | `tianji_db`/`weight_matrix` 两副本公开接口签名一致 | ✅ xfail |
| `macro-scan/tests/test_audit_scan_deploy_tag.py` | pytest | #14 | `deploy.sh` 构建 tag 与 `docker-compose.yml` 的 image tag 一致 | ✅ xfail |
| `kaiyang/src/state/test_audit_kaiyang_vite_token.test.tsx` | vitest | #2 | 用户 localStorage 令牌应优先于 VITE_ env 内联令牌 | ✅ 2 passed（`it.fails`） |

**编排说明（如实记录）**：这 13 个测试由一个 13-agent 工作流并行编写并各自真跑。工作流汇总声称"13/13"，但独立核对 journal 发现它**把 `narrative-indent` 写了两遍、漏了 `mc2-recession`**；`mc2-recession` 由主控手工补写。上表全部 13 项均已由主控**独立重跑**确认（不采信 agent 自报）。

### 9.4 CI 门禁（`.github/workflows/ci.yml`）

新增 GitHub Actions，`push`/`pull_request` 到 `main` 时触发，4 个并行 job：

- **kaiyang**：Node 20 + `npm ci` + `vitest run`。
- **macro-sim / macro-ji**：Python 3.12 + `requirements.txt` + `pytest-timeout`，`pytest tests --timeout=120`。
- **macro-scan**：Python 3.12 + `requirements.txt --find-links wheels`（`zh_core_web_sm`/`feedparser` 为非 PyPI 包，已随 `wheels/` 入库）+ `pytest tests --timeout=90 --ignore=tests/test_fetch_commodity_yahoo.py`（排除已知挂起文件）。
- 全局 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`，避免中文 print 编码崩溃。

### 9.5 遗留 / 建议

- **零断言测试重写**：macro-scan 的 4 个 fetcher 测试应改为真断言（用 `tests/fixtures/` 下已有的样本 JSON/CSV mock `requests.get`），否则它们仍是假绿。
- **yahoo 挂起根因**：`commodity_yahoo` 的 `collect()` 未拦住真实网络请求，需修 mock 边界（很可能是 `fetcher_base` 层的 `requests.get` 未走注入点）；修好后从 CI 的 `--ignore` 移除。
- **3 个 0 字节空壳**（`核心代码/tests/`）：本轮未填充（低优先，且 yahoo 空壳存在与上面同样的挂起风险）；建议删除或补实。
- **覆盖率**：macro-sim core 仅 ≈21%、macro-ji 从 0 起步；本轮回归测试只覆盖了 critical/high 发现点，非全面覆盖。建议后续按模块补充正常路径与边界用例。