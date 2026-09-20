# repoready 设计文档

- 日期:2026-09-20
- 状态:已批准,待实现
- 参赛定位:第八届全球校园人工智能算法精英大赛(2026),算法主题赛,赛项「AI+开源」,申报方向二「AI 开发工具与开源协作」

## 1. 一句话

不生成文档,而是验证文档:把一个开源项目声明的安装与使用步骤,在隔离环境里真实执行一遍,输出每一步能否跑通、失败在哪、为什么失败、怎么修。

## 2. 背景与问题

开源项目的 README 会腐坏。依赖版本漂移、系统库缺失、CI 里实际执行的命令与文档描述脱节,
后果由两端承担:

- 新手照着文档做到第二步就卡住,然后放弃贡献。
- 维护者本地环境早已装好依赖,收到"装不上"的 issue 时无从复现。

现有工具集中在「生成文档」这一侧,让 README 变多;没有人系统性地「验证文档」,让 README 变得可信。
这是本项目的立足点。

## 3. 目标与非目标

### 3.1 目标

1. 给定仓库与 commit,自动产出**经过真实执行**的上手指南,每步附执行证据。
2. 失败时给出**可定位、可分类、可执行**的结论,而不是一句"安装失败"。
3. 全部结论可复现:锁定 commit、限定资源、固定环境,任何人重跑得到一致结论。
4. 批量评测能力:横向对比"照官方 README 做"与"照本工具产出做"的差异。

### 3.2 非目标(明确不做)

- 不做 Web 服务、不做前端框架。
- 不自动向第三方仓库提交 PR。
- 不追求多语言全覆盖:首期只支持 Python 生态,Node 视进度决定。
- 不做多轮自主修复 agent:失败样本如实记录,不代替人修项目。
- 不自研容器运行时。

## 4. 目标用户与场景

**贡献者**:想给某开源项目提 PR,先把环境跑通。

```text
repoready check https://github.com/psf/requests --ref v2.32.0
```

**维护者**:周期性检查文档是否还能用,或收到"装不上"报告时快速定位。

**研究者/评审**:需要一批仓库的可复现实验数据。

```text
repoready bench --suite suites/python-basic.json
```

## 5. 系统架构

三层,单向数据流:探测层产出候选步骤,执行层产出逐步结果,报告层渲染结论。

### 5.1 探测层(probe)

职责:把仓库变成一串**有序、带出处**的候选步骤。

1. **项目识别**:扫描工作区,识别语言与包管理器。
   首期识别信号:`pyproject.toml`、`requirements*.txt`、`setup.py`、`setup.cfg`、
   `poetry.lock`、`Pipfile`、`environment.yml`、`tox.ini`、`Makefile`、`.python-version`。
2. **步骤抽取**,来源优先级由高到低:
   - CI 配置:`.github/workflows/*.yml`、`.gitlab-ci.yml`、`azure-pipelines.yml`。
     排在首位的原因是这些命令**正在被真实执行**,可信度高于文档描述。
   - 文档:README、CONTRIBUTING、`docs/` 下的代码块。
   - 推断:根据项目文件得出的默认命令,例如 `pip install -e .`、`pytest`。
3. **出处标注**:每条步骤记录来源类型、文件路径、行号。这是"可追溯"的基础,
   也是报告中"这条命令是谁说的"这一栏的数据来源。

探测层只做静态分析,不执行任何仓库代码。

### 5.2 执行层(runner)

职责:在隔离环境中按顺序执行步骤,记录证据。

**后端可插拔**,统一接口 `run(step, workdir, limits) -> StepResult`:

- `docker`:首选。固定基础镜像、CPU/内存/超时上限、工作目录挂载、网络开关。
- `local`:降级。无 Docker 时用子进程 + 独立虚拟环境执行。
  隔离性弱,遇到需要系统级依赖的项目会失败,这一点在报告中如实标注。

后端选择顺序:显式参数 > 自动探测(Docker 可用则用 Docker)> 降级到 local。

**连接 Docker 时必须尊重 `DOCKER_HOST` 环境变量**,并区分三类连接失败:
Docker 未安装、守护进程未运行、权限不足。三者对应不同的修复建议,
不能笼统归为"工具坏了"。

**步骤状态机**:

```text
pending ──> running ──> passed
                    └─> failed
                    └─> blocked
       └─> skipped   (前置步骤失败,未执行)
```

`failed` 与 `blocked` 必须分开,这是统计口径的基石:

- `failed`:命令真的返回了非零退出码,是项目或文档的问题。
- `blocked`:环境不具备执行条件(缺密钥、需 GPU、需外部服务),
  是评测环境的问题。两者混在一起,"可跑通率"就失去意义。

**证据捕获**:每条步骤记录命令原文、退出码、耗时、工作目录、语言运行时版本,
以及 stdout/stderr 的首尾片段(中间截断,保留锚点)。日志完整落盘,报告中只引用片段。

**资源与安全**:容器默认限制 CPU、内存与单步超时;默认不把宿主机敏感路径挂进容器;
网络默认开启但可按套件关闭;所有写操作发生在临时工作目录内。

### 5.3 报告层(report)

同一份数据,三种呈现:

- `run.json`:权威数据源,每条步骤一条记录,含完整证据与出处。
- `report.md`:人类可读,按步骤列出结论、失败分类与修复建议。
- `report.html`:静态页面,无需服务器,双击即开;支持展开原始日志。
  演示视频与答辩主要依赖这一份。

报告层不重新判断任何结论,只做渲染。所有判断在执行层已完成并写入 `run.json`。

## 6. 数据模型

核心记录(字段名即 JSON 键):

```text
RunRecord
  schema_version : str
  repo_url       : str
  commit         : str            # 解析后的完整 SHA
  backend        : "docker" | "local"
  image          : str | null
  started_at     : str            # ISO 8601
  finished_at    : str
  environment    : dict           # OS、Python 版本、Docker 版本等快照
  steps          : [StepRecord]

StepRecord
  id            : int
  command       : str
  status        : "passed" | "failed" | "blocked" | "skipped"
  exit_code     : int | null
  duration_ms   : int
  source        : SourceRef
  stdout_head   : str
  stdout_tail   : str
  stderr_head   : str
  stderr_tail   : str
  attribution   : Attribution | null

SourceRef
  kind : "ci" | "readme" | "inferred"
  path : str
  line : int | null

Attribution
  category    : str
  evidence    : [str]        # 逐条必须能在本步骤输出中原文找到
  suggestion  : str
  generated_by: "rules" | "llm"
```

字段一旦发布即视为对外接口:报告、评测脚本与第三方复现都依赖它。
未知状态一律用 `null`,不用空字符串或 `"unknown"` 混淆。

## 7. 失败归因

### 7.1 分类

固定七类,便于统计与对比:

| 分类 | 含义 |
| --- | --- |
| `missing_system_dep` | 缺系统级依赖(如 `libGL`、`gcc`、`python3-dev`) |
| `version_conflict` | 依赖解析冲突或版本不满足 |
| `network_required` | 需要下载大文件或访问外部服务 |
| `credential_required` | 需要密钥、令牌或私有仓库权限 |
| `hardware_required` | 需要 GPU 或其他特定硬件 |
| `doc_drift` | 文档描述的命令已过时或已重命名 |
| `unknown` | 证据不足,无法归类 |

### 7.2 两阶段归因

1. **规则阶段**:基于退出码与日志模式匹配,覆盖常见情况。纯本地、可离线、结果稳定。
2. **LLM 阶段(可选)**:规则无法归类时调用大模型给出分类与建议。

### 7.3 防幻觉硬约束

LLM 归因结果必须满足全部条件才被采纳:

1. `category` 属于上述七类之一。
2. `evidence` 中每一条,都能在**该步骤自身的输出**中原样找到
   (比对前统一空白与换行,不做模糊匹配)。
3. `suggestion` 非空且长度在合理区间内。

任一条件不满足,该归因结果整体降级为 `unknown`,并在报告中标注"证据不足"。

这条约束是可演示的:同一段日志,让模型编造引用会被自动拦下。
它是整个技术叙事的支点——**模型可以说,但必须有据**。

### 7.4 无 LLM 也能跑

没有 API key 时,规则阶段独立完成全部流程,报告正常生成,`generated_by` 记为 `rules`。
评委复现时不会因为缺密钥而卡住。

## 8. 评测集与度量

### 8.1 评测集

20 个真实公开仓库,分三层:

| 层次 | 特征 | 数量 |
| --- | --- | --- |
| 简单 | 纯 Python,无系统依赖 | 8 |
| 中等 | 有 C 扩展或系统依赖 | 7 |
| 复杂 | 多语言、或需要外部服务 | 5 |

每条记录锁定 `commit` SHA。名单与 SHA 一并提交进仓库,保证任何人可复现同一批实验。

### 8.2 四个指标

1. **指南可跑通率**(核心):按工具产出的步骤重跑,全流程通过的仓库比例。
2. **失败定位准确率**:与人工标注的 ground truth 对比,定位到正确失败步骤的比例。
3. **对照提升**:同一批仓库,"直接照官方 README 执行"与"照本工具产出执行"的可跑通率之差。
4. **成本**:平均耗时、平均步骤数。

全部指标由 `repoready bench` 一键产出,不接受手工拼凑的数字。

## 9. CLI 接口

```text
repoready check <repo> [--ref REF] [--out DIR] [--backend docker|local]
                       [--timeout SEC] [--no-network]
repoready bench --suite FILE [--out DIR] [--jobs N]
repoready report <run-dir> [--format json|md|html]
repoready doctor
```

`doctor` 检查运行环境:Python 版本、Docker 可用性与权限、`DOCKER_HOST` 设置,
并给出针对性修复建议。它同时也是演示视频的开场素材——先展示环境检查,
再展示真实执行。

所有命令遵循同一约定:退出码 0 表示流程成功,非 0 表示工具自身出错;
**被检查项目的失败不导致非零退出码**,结果体现在 `run.json` 的 `steps` 中。
这条区分对批量评测至关重要。

## 10. 技术选型

**标准库优先,首期零第三方运行时依赖。**

| 关注点 | 选择 | 理由 |
| --- | --- | --- |
| 语言 | Python 3.10+ | 环境普遍可用 |
| CLI | `argparse` | 标准库,避免引入 CLI 框架 |
| 数据模型 | `dataclasses` + 显式校验 | 不依赖 pydantic,校验逻辑显式可读 |
| 模板 | `string.Template` | 不依赖 jinja2,报告模板简单 |
| 配置 | JSON | 不依赖 PyYAML |
| HTTP(LLM) | `urllib.request` | 不依赖 requests |
| 容器调用 | `subprocess` 调用 docker CLI | 少一层依赖,且天然尊重 `DOCKER_HOST` |
| 测试 | `unittest` | 标准库,`python -m unittest` 直接跑 |

这个选择与作品主题一致:**一个专治"装不上、跑不起来"的工具,自己必须 `git clone` 之后就能跑。**
每减少一个依赖,评委复现时就少一个失败点。真正需要时才考虑以 extras 形式引入。

## 11. 目录结构

```text
repoready/
  docs/superpowers/specs/     设计文档
  src/repoready/
    __main__.py               python -m repoready 入口
    cli.py                    argparse 命令定义
    probe/                    探测层:识别、抽取、数据模型
    runner/                   执行层:后端协议、docker、local、执行器
    attribution/              归因:规则、LLM、证据校验
    report/                   报告:json、markdown、html
  suites/                     评测集定义(JSON);每个文件含仓库清单与锁定的 commit
  tests/                      unittest 测试
  reports/                    生成的报告输出目录
  scripts/                    辅助脚本
```

## 12. 测试策略

- **单元测试**(unittest):探测层解析、日志裁剪、状态机迁移、归因证据校验。
  这些全是纯函数逻辑,不依赖网络与 Docker。
- **集成测试**:用 `local` 后端对构造的小型样本仓库跑完整流程,不依赖 Docker。
- **Docker 后端测试**:标记为可选,需要本机 Docker;缺失时跳过而非失败。
- **证据校验测试**是重点:构造"日志里不存在该行"的归因结果,断言它被降级为 `unknown`。

## 13. 风险与应对

| 风险 | 应对 |
| --- | --- |
| 容器内执行陌生仓库代码 | 资源上限、单步超时、不挂载宿主机敏感路径、工作目录隔离 |
| 评测仓库被删除或改版 | 锁定 commit SHA,清单入库;关键镜像预先拉取 |
| 拉取镜像受网络影响 | 支持指定镜像与超时;评测时记录镜像摘要 |
| 时间紧(18 天) | 先打通纵向切片:一个仓库从探测到 HTML 报告端到端,再横向扩规模 |
| Docker 在评委机器不可用 | `local` 降级后端 + `doctor` 明确诊断 |
| LLM 输出不可控 | 证据校验硬约束 + 规则阶段兜底 |

## 14. 合规与开源

- 许可证:MIT。
- `THIRD_PARTY_NOTICES.md`:逐个列出使用的第三方资源、版本、许可证与使用方式。
- 评测集内所有仓库均为公开项目,仅做只读克隆与本地执行,不修改、不转发其代码。
- 容器内执行产生的网络访问与资源消耗在文档中说明。
- 参赛作品为本届大赛期间原创,原创性声明随技术报告提交。

## 15. 里程碑

| 日期 | 目标 |
| --- | --- |
| 09-20 | 设计定稿、仓库初始化 |
| 09-21 | 项目骨架、CI、`doctor` 命令可用 |
| 09-27 | 执行引擎 MVP:对一个真实仓库产出完整报告 |
| 10-01 | 评测集扩至 20 个仓库,产出第一版统计 |
| 10-04 | 报告层完善、技术报告初稿、合规披露文件 |
| 10-06 | 演示视频、技术报告定稿 |
| 10-07 | 形式审查自查并提交 |
| 10-08 | 缓冲 |

外部节点:10-10 前完成校赛(河南赛区),10-15 20:00 官方报名与作品提交截止。

## 16. 待定事项

1. 河南赛区「算法创新赛—AI+软件创新」赛题是否接受本类作品,需向赛区组委会确认。
2. 同一份作品同时投报 AI+开源 主题赛与河南赛区创新赛是否被允许,需确认。
3. 官方附件《AIC·AI+开源竞赛规则及作品提交要求》《技术报告参考大纲》尚未取得,
   取得后需据其校准技术报告结构与评分重心。
