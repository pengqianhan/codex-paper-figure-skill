# codex-paper-figure-skill 双方法优化与 PaperBananaBench 评测实施方案

状态：已完成需求 grilling，方案待实施  
制定日期：2026-07-23（Pacific/Auckland）

> 当前实施阶段（2026-07-23）：因预算限制，先只实现 SkillOpt-Lite。
> 本阶段最终盲测为 baseline 与 SkillOpt-Lite 两个冻结版本（292 x 2）；
> Meta-Harness 流程保留在本方案中，之后从同一公共脚手架单独实现。

## 1. 目标

在同一个初始 `SKILL.md` 上分别应用两套原生优化流程：

1. Meta-Harness：保留每轮多候选、完整历史、执行轨迹和 frontier/finalization 机制。
2. SkillOpt-Lite：保留单候选小步修改、validation gate、dead band、回滚和 best snapshot 机制。

第一阶段优先尊重两种方法的原始流程，不强行匹配优化预算。两个最终技能冻结后，使用完全相同的 executor、工具、测试数据、VLM-judge rubric 和统计流程，在 PaperBananaBench `diagram/test.json` 的 292 个样本上进行盲测。

第一阶段不自动把任何优化结果合并回主分支。后续可增加 matched-budget 实验。

## 2. 参考方法

- Meta-Harness 论文与实现：
  - <https://arxiv.org/abs/2603.28052>
  - <https://github.com/stanford-iris-lab/meta-harness>
  - <https://github.com/stanford-iris-lab/meta-harness/blob/main/ONBOARDING.md>
- SkillOpt-Lite：<https://github.com/EvolvingLMMs-Lab/SkillOpt-Lite>
- PaperBanana 与评分实现：
  - <https://github.com/dwzhu-pku/PaperBanana>
  - <https://github.com/dwzhu-pku/PaperBanana/blob/main/utils/eval_toolkits.py>
  - <https://github.com/dwzhu-pku/PaperBanana/blob/main/prompts/diagram_eval_prompts.py>
- draw.io Desktop：<https://github.com/jgraph/drawio-desktop/releases>

## 3. 已冻结的初始状态

| 项目 | 值 |
| --- | --- |
| 仓库 | `/Users/pengqianhan/Documents/GitHub/Opensource/codex-paper-figure-skill` |
| 初始分支 | `refine` |
| 初始提交 | `a9a4ffcdda8088194c3a7962a538b0ac1bb25e23` |
| 初始 `SKILL.md` SHA-256 | `40101c17247aa20fea9831ba5272c1bcfd844a9a2592625b809f7708e91cc7ba` |
| `ref.json` SHA-256 | `d978569bbd46c1d312cde669475b87ace868d80bfb7ffb0484464dbc6b8f5d6a` |
| `test.json` SHA-256 | `6e30fcf20fda71656e468e5d9418bbe4bf924b99234b06fcd6597113f9f37ce1` |
| Codex CLI | `0.145.0` |
| draw.io Desktop/CLI | `30.4.1` |
| draw.io CLI 路径 | `/Applications/draw.io.app/Contents/MacOS/draw.io` |
| draw.io CLI SHA-256 | `cd4701b4936f28d8b04f292a8bd7dbd6b17ab2254ac367f45b152935bc67fff5` |

在实施开始时重新验证这些值。若输入数据、初始技能或工具二进制发生变化，停止并生成新的协议版本，不静默继续。

## 4. 共同实验基线与 worktree

### 4.1 共同基线

先在当前仓库加入共享且不可由优化器修改的实验脚手架：

- 协议配置与锁文件。
- 数据清洗、分层划分和匿名化脚本。
- executor、judge 和 proposer 的角色提示。
- draw.io/XML 结构验证器和 PNG 质量检查器。
- PaperBanana outcome 汇总器。
- 运行日志 schema、统计脚本和单元测试。
- Meta-Harness 域规格 `domain_spec.md`。

验证脚手架后创建一个共同基线提交。两个 worktree 必须从该提交创建。

### 4.2 分支与持久 worktree

- Meta-Harness 分支：`codex/meta-harness-opt`
- SkillOpt-Lite 分支：`codex/skillopt-lite-opt`
- 推荐 worktree：
  - `/Users/pengqianhan/Documents/GitHub/Opensource/codex-paper-figure-skill-worktrees/meta-harness`
  - `/Users/pengqianhan/Documents/GitHub/Opensource/codex-paper-figure-skill-worktrees/skillopt-lite`

原仓库保留为 baseline/control 与统一报告工作区。

### 4.3 可变面

优化候选只能修改：

`codex-paper-figure-skill/SKILL.md`

每次候选产生后执行 allow-list diff 检查。任何候选若修改 runner、评分器、manifest、模型配置、提示模板或其他仓库文件，则候选无效，不进入评测。

方法适配器、控制脚本和日志索引可以在正式优化前加入各自分支，但正式搜索开始后必须锁定并记录 SHA-256。

## 5. 推荐仓库结构

```text
experiments/paperbanana/
├── README.md
├── protocol.yaml
├── locks/
│   └── toolchain.json
├── manifests/
│   ├── split_summary.json
│   └── checksums.json
├── prompts/
│   ├── executor.md
│   ├── meta_harness_proposer.md
│   ├── skillopt_lite_proposer.md
│   └── judges/
│       ├── faithfulness.md
│       ├── conciseness.md
│       ├── readability.md
│       └── aesthetics.md
├── schemas/
│   ├── executor_result.schema.json
│   ├── judge_result.schema.json
│   └── run_ledger.schema.json
├── meta_harness/
│   ├── domain_spec.md
│   └── controller.md
├── skillopt_lite/
│   └── controller.md
├── scripts/
│   ├── make_manifests.py
│   ├── sanitize_case.py
│   ├── validate_drawio.py
│   ├── render_drawio.py
│   ├── build_judge_jobs.py
│   ├── aggregate_scores.py
│   └── bootstrap_report.py
└── tests/
    ├── test_sanitization.py
    ├── test_split.py
    ├── test_drawio_validation.py
    ├── test_scoring.py
    └── test_protocol_lock.py
```

大型运行产物不进入 Git，统一存放在：

`/Users/pengqianhan/Downloads/PaperBananaBench/diagram/experiments/<run-id>/`

原始 `ref.json`、`test.json` 和 `images/` 不得修改。

## 6. 数据协议

### 6.1 原始数据

- `ref.json`：298 个样本。
- `test.json`：292 个样本。
- 两者没有重复的论文文件名或真值图片路径。

### 6.2 固定划分

随机种子：`20260723`

从 `ref.json` 生成：

- train：36 个样本，分为三个互不重复的 12 样本批次。
- validation：24 个固定样本，整个优化期间不变。
- unused reserve：238 个样本，第一阶段完全不访问、不评分。

按 `category`、`rounded_ratio` 和 content 长度分层。类别目标配额：

| category | train | validation |
| --- | ---: | ---: |
| agent_reasoning | 11 | 7 |
| generative_learning | 9 | 6 |
| science_applications | 6 | 4 |
| vision_perception | 10 | 7 |
| 合计 | 36 | 24 |

所有抽样只依据预先存在的元数据，不查看真值图，也不人工挑选容易案例。生成 manifest 后记录样本 ID、顺序和文件 SHA-256。

### 6.3 test 封存

在两个方法完成 finalization、最终 `SKILL.md` 写入哈希锁文件之前：

- proposer 不得访问 test manifest、test 文本、真值图或任何 test 结果。
- 不运行 baseline test。
- 不使用 test 决定是否继续优化或选择候选。

冻结后一次性运行 baseline、Meta-Harness 最终版本和 SkillOpt-Lite 最终版本。

## 7. 输入清洗与泄漏防护

executor 只能收到：

- 匿名 case ID。
- 完整清洗后的 `content`。
- 完整 `visual_intent`。
- 固定输出目录和输出 contract。

清洗器必须删除：

- 所有 Markdown/HTML 内嵌图片引用。
- `path_to_gt_image`。
- PDF 路径、原始文件名、split 和其他可映射到真值的元数据。
- 任何 `images/...` 真值路径残留。

正文、公式和 caption 周边文本不摘要、不智能截断。`content` 为空时只传 `visual_intent`，保留样本并单独标记。

生成两个隔离 manifest：

1. executor manifest：无真值路径。
2. judge manifest：包含真值路径，只供 judge 调度阶段使用。

sanitize 单元测试必须确认 executor manifest 不含 `images/`、`path_to_gt_image`、`.jpg` 真值文件名或原始论文文件路径。

## 8. Codex subagent 角色

根任务只负责编排、锁定配置、传递允许的文件和汇总结果，不亲自充当 proposer、executor 或 judge。

### 8.1 模型配置

| 角色 | 模型 | reasoning effort | 上下文策略 |
| --- | --- | --- | --- |
| Meta-Harness proposer | `gpt-5.6-sol` | `high` | 每 iteration 新建，读取文件系统历史 |
| SkillOpt-Lite proposer | `gpt-5.6-sol` | `high` | 每 round 新建，只读取允许的最新轨迹 |
| Figure executor | `gpt-5.6-sol` | `medium` | 无优化历史，固定小批次后重启 |
| VLM judge | `gpt-5.6-sol` | `high` | 单维度、匿名小批次后重启 |

所有 subagent 使用 `fork_turns="none"` 或等价的无对话继承模式。Meta proposer subagent 内部不得再委派子代理，以遵守其原始 proposer 工作约束。

Codex 并发上限为 4 个活跃 agent（包含根任务），因此最多并行 3 个 worker。具体批量大小在 smoke test 后锁定；默认 executor batch 为 4，judge batch 为 12。

### 8.2 角色隔离

- proposer 看不到 test 数据或 judge-only manifest。
- executor 看不到真值图、分支标签、历史分数、judge 输出或另一 worktree。
- judge 看不到优化方法、分支名、候选历史、成本或生成轨迹。
- Meta 与 SkillOpt proposer 不能互读对方 worktree。
- VLM judge 不能修改任何技能、runner 或产物。

## 9. 固定 figure executor contract

每个样本：

1. 读取指定的、哈希锁定的 `SKILL.md`。
2. 读取清洗后的 methodology text 与 `visual_intent`。
3. 最多调用 1 次 `image_gen` 生成构图参考。
4. 创建原生可编辑 `.drawio`。
5. 使用固定 draw.io CLI 导出 PNG。
6. 最多进行 2 次“查看 PNG → 修正 XML → 重新导出”循环。
7. 写入结构化 trace 和 status。

限制：

- 单样本最长 20 分钟。
- 只允许一次基础设施级完整重试。
- 质量差或 judge 低分不属于重试条件。
- 正式 benchmark 禁用 Browser、网页检索和外部图标下载。
- 禁止将 `image_gen` 参考图作为全画布背景或最终 `.drawio` 主体。

基础设施错误包括明确的工具超时、image generation 服务错误、draw.io CLI 崩溃或文件系统瞬时错误。第二次仍失败则样本记为失败，不进行人工救援。

每个输出目录至少包含：

```text
<case-id>/
├── figure.drawio
├── figure.png
├── reference.png
├── trace.json
├── validation.json
└── status.json
```

## 10. 可编辑性硬门槛

视觉评分前执行确定性检查：

- XML 可解析。
- `mxCell id="0"` 和 `mxCell id="1" parent="0"` 存在。
- 所有 `mxCell` ID 唯一。
- 图中存在非平凡数量的原生 vertex、edge 和 editable text。
- edge 具有合法 geometry；source/target 引用若存在则可解析。
- 不存在覆盖主体画布的单张 raster image。
- PNG 导出成功、尺寸非零、不是空白图或近乎纯色图。
- 内容 bounding box 不发生明显裁切。
- `.drawio`、PNG、trace 和 status 均存在。

具体像素与 cell-count 阈值先在仓库现有示例和 smoke 样本上校准，随后写入 `protocol.yaml` 并锁定；不得在看到 validation/test 结果后修改。

硬门槛失败的样本直接记 0，不进入质量补救流程。

## 11. PaperBanana VLM-judge

### 11.1 四个独立维度

使用 PaperBanana 官方 diagram rubric 的语义与 veto rules：

- faithfulness
- conciseness
- readability
- aesthetics

四个维度分别由独立 judge 任务判断，严格输出 JSON。judge 读取 methodology/caption、human reference 和最终 `.drawio` 导出的 PNG。

合法 outcome：

- `Human`
- `Model`
- `Both are good`
- `Both are bad`

### 11.2 overall 规则

overall 不让 judge 自由打分，由共享汇总器复现 PaperBanana 规则：

1. Tier 1：faithfulness + readability。
2. Tier 1 无法决胜时再看 Tier 2：conciseness + aesthetics。
3. overall 输出 `Model`、`Human` 或 `Tie`。

用于汇总的数值映射：

- `Model = 1.0`
- `Tie = 0.5`
- `Human = 0.0`
- 硬门槛失败或 judge error = `0.0`

该数值接口供方法各自的原生 selection/finalization 使用；不改变各方法的内部机制。

### 11.3 validation 防火墙

Train 阶段可向允许的 proposer 提供完整逐样本输入、产物、结构检查、judge outcome 与 reasoning。

Validation 阶段只向 proposer 提供：

- 聚合 overall 分数。
- 四维 outcome 计数/比例。
- 输出成功率和硬门槛通过率。
- 方法原生的 gate/frontier 状态。

不得提供 validation 样本 ID、文本、真值图、生成图、逐样本 outcome 或 reasoning。

## 12. Meta-Harness 原生流程

### 12.1 域规格

根据 Meta-Harness `ONBOARDING.md` 创建 `domain_spec.md`，明确：

- 评测单位：一个 PaperBanana methodology diagram case。
- 冻结模型、工具与 evaluator。
- 候选接口：完整有效的 `SKILL.md`。
- 唯一可变文件。
- train/validation/test 数据边界。
- 日志、候选历史和 finalization contract。

### 12.2 三个 iteration

每个 iteration：

1. proposer 读取所有历史候选、完整 train 轨迹、validation 汇总、frontier 和先前报告。
2. 提出恰好 3 个机制上不同的 `SKILL.md` 候选。
3. 每个候选必须包含可证伪 hypothesis，且不能只是参数或措辞微调。
4. 对候选执行 allow-list diff、metadata 和基本语法检查。
5. 三个候选分别在当轮同一组 12 train 样本上执行，保留完整轨迹。
6. 三个候选分别在同一组固定 24 validation 样本上执行，只公开汇总。
7. 所有候选无论好坏都永久归档。
8. 使用 Meta-Harness 自身的 history/frontier 机制更新状态。
9. 写入不超过 30 行的 iteration report，记录机制、结果和后续启示。

三轮共提出 9 个候选。后续 proposer 可以从 frontier 中任何候选继续组合或探索，不使用 SkillOpt 的 rollback 机制。

### 12.3 finalization

完成第三个 iteration 后，使用 Meta-Harness 适配器的原生 frontier/finalization 逻辑冻结最终候选。记录：

- 最终 skill SHA-256。
- 来源候选与 iteration。
- frontier 全量状态。
- validation 指标和资源消耗。

冻结后禁止继续优化。

## 13. SkillOpt-Lite 原生流程

### 13.1 Round 0

1. 在完整 24 validation 上建立 baseline score。
2. 将原始技能写入 best snapshot。
3. 用第一个 12-sample train batch 产生 round 1 的 failed/passed 轨迹。

### 13.2 三个 round

每轮：

1. snapshot 当前技能。
2. proposer 只读取当前技能和最新 train batch 的 failed/passed 轨迹。
3. 按 SkillOpt-Lite 原流程聚类失败、与成功样本对照，并应用最小补丁。
4. 每轮最多 4 处 edit，不硬编码样本内容。
5. 在完整 24 validation 上 gate。
6. 使用原生 `±0.01` dead band 与 accept/reject/rollback/best 逻辑。
7. 用 gate 后磁盘上的技能生成下一轮 train 轨迹。
8. 归档 before/after/best snapshot 和 round summary。

### 13.3 finalization

第三轮结束后恢复原生 best snapshot，记录最终 skill SHA-256、best round、完整 gate history 和资源消耗，然后冻结。

## 14. Smoke test 与阶段门

### Phase A：静态与单元测试

- 数据清洗无真值泄漏。
- 分层划分数量、互斥性和确定性正确。
- PaperBanana overall 汇总规则有测试覆盖。
- draw.io XML 验证器对仓库现有示例通过，对故意损坏样例失败。
- protocol/runner 哈希锁可检测篡改。

### Phase B：四类 smoke test

从 train 中固定选择每个 category 一个样本，仅使用 baseline skill：

- executor 能调用一次 `image_gen`。
- `.drawio` 能创建并由 draw.io CLI 30.4.1 导出。
- PNG 能被 Codex judge subagent 查看。
- 四维 judge JSON 能解析。
- trace、状态和重试语义正确。

smoke 只验证系统，不修改技能、不查看 validation/test。

### Phase C：优化

先运行 Meta-Harness 与 SkillOpt-Lite 各自的原生优化循环。发生以下任一情况则暂停：

- 共享 runner 或评分器哈希变化。
- executor manifest 出现真值路径。
- judge 获得分支身份。
- CLI 批量导出不稳定。
- 某方法越过 `SKILL.md` 可变面。

### Phase D：冻结审计

- 验证两个最终 skill 都来自共同基线。
- 验证除 `SKILL.md` 外没有候选期修改。
- 写入最终哈希和 finalized marker。
- 之后才生成 test executor jobs。

### Phase E：292-case 最终盲测

- baseline、Meta-Harness final、SkillOpt-Lite final 各运行 292 个样本。
- 三个版本使用逐字节相同的清洗输入、executor prompt、工具限制和每样本预算。
- 运行任务使用匿名 variant ID，顺序随机化并在时间上交错，降低服务漂移影响。
- 任何 test 结果不得触发技能修改或额外候选。

## 15. 最终统计协议

### 15.1 主指标

三个版本各自在 292 个 test 样本上的 mean overall score。

### 15.2 配对比较

使用相同样本上的 paired bootstrap（固定 seed，至少 10,000 次重采样）计算：

- Meta-Harness final − baseline
- SkillOpt-Lite final − baseline
- Meta-Harness final − SkillOpt-Lite final

报告均值差与 95% confidence interval。区间包含 0 时写“未检出可靠差异”，不得仅按均分高低宣布胜者。

### 15.3 次要指标

- faithfulness、conciseness、readability、aesthetics outcome 分布。
- 四个 category 的分层结果。
- XML/可编辑性通过率。
- PNG 导出成功率。
- 完整任务成功率和失败原因。
- 每样本 wall time、subagent 调用、`image_gen` 调用和重试次数。
- `SKILL.md` 长度与 diff 大小。

### 15.4 judge 一致性

预先随机抽取 10% 的 test 判断任务，由全新、同配置 judge subagent 重评。重评只估计一致性，不用于挑选更有利的 outcome。

报告：

- exact agreement。
- 分维度 agreement。
- outcome confusion matrix。
- 适用时报告 Cohen's kappa。

若方法差异小于重评波动，结论降级为不确定。

## 16. 运行产物与审计日志

建议输出目录：

```text
experiments/<run-id>/
├── protocol/
│   ├── protocol.yaml
│   ├── hashes.json
│   └── environment.json
├── manifests/
├── baseline/
├── meta-harness/
│   ├── candidates/
│   ├── train-traces/
│   ├── val-summaries/
│   ├── frontier/
│   └── final/
├── skillopt-lite/
│   ├── history/
│   ├── train-traces/
│   ├── val-summaries/
│   └── final/
├── test/
│   ├── anonymous-jobs/
│   ├── generated/
│   ├── judge-results/
│   └── repeat-judging/
└── reports/
    ├── summary.md
    ├── summary.json
    ├── per-sample.jsonl
    ├── aggregate.csv
    └── failures.csv
```

每个记录至少包含：run ID、匿名 case ID、variant ID、skill hash、runner hash、模型与 effort、开始/结束时间、工具调用数、重试、产物路径、结构检查、四维 outcome、overall 和错误信息。

API 密钥、认证 token、用户配置全文和个人环境变量不得进入日志。

## 17. 第一阶段预算说明

第一阶段刻意不匹配两种优化器的预算：

- Meta-Harness：3 iterations × 3 candidates，并为每个候选生成独立 train 和 validation 轨迹。
- SkillOpt-Lite：3 rounds × 1 candidate，按自身循环生成 train 轨迹并进行 validation gate。
- 最终测试完全一致：3 个冻结版本 × 292 cases。

因此第一阶段可以比较“原生流程最终产物”，不能据此得出单位候选、单位 token 或单位成本效率结论。

所有实际调用由 ledger 统计，不以事前估算替代。精确美元成本未知；Codex 内置 `image_gen` 的后端版本和随机 seed 也可能不公开。记录所有可获得的调用元数据，并把这一点写入最终限制。

后续 matched-budget 研究应单独预注册，可按以下任一资源对齐：

1. 候选总数。
2. train rollout 总数。
3. validation case evaluations。
4. proposer/executor 总 token。
5. 总 wall-clock 或估算成本。

不得在看到第一阶段 test 结果后选择最有利的预算定义并将其描述为预注册结论。

## 18. 交付与合并策略

交付内容：

- 两个持久 worktree 和分支。
- 两个最终 `SKILL.md` 及 SHA-256。
- Meta-Harness 的 domain spec、候选历史和 frontier。
- SkillOpt-Lite 的 round snapshots 和 gate history。
- 完整协议、manifest 哈希和工具链锁。
- 逐样本结果、汇总统计、失败索引和代表性图片。
- 一份说明方法适配点、未对齐预算和已知限制的最终报告。

不自动合并。用户查看报告和代表性产物后，再决定：

- 合并 Meta-Harness 版本。
- 合并 SkillOpt-Lite 版本。
- 保留 baseline。
- 启动 matched-budget 实验。
- 人工综合两个技能后另做全新验证。

## 19. 实施顺序

1. 创建共享协议、脚本、schemas 和单元测试。
2. 生成并检查 Meta-Harness `domain_spec.md`。
3. 运行静态测试和四类 smoke test。
4. 锁定所有共同文件并形成共同基线提交。
5. 创建两个分支与 worktree。
6. 在各 worktree 加入方法适配器并锁定。
7. 运行 Meta-Harness 原生优化。
8. 运行 SkillOpt-Lite 原生优化。
9. 完成 freeze audit。
10. 一次性运行 292-case × 3 final test。
11. 完成匿名 judge、10% 重评和统计汇总。
12. 交付双分支与报告，不自动合并。

## 20. 实施前仍需由系统处理的权限

以下路径不在当前仓库写权限内，实际执行时可能触发 Codex 审批：

- 创建仓库旁的两个持久 worktree 目录。
- 写入 `/Users/pengqianhan/Downloads/PaperBananaBench/diagram/experiments/`。
- 通过 `/Applications/draw.io.app/Contents/MacOS/draw.io` 执行导出。

发生审批时只申请完成上述已确认范围所需的最小权限，不申请宽泛的文件系统或任意命令权限。
