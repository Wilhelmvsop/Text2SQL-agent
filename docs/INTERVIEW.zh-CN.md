# Text2SQL Agent：面试讲解与简历证据

本文对应当前仓库的实际实现。离线流程与数据库测试已运行；真实模型 API
返回 HTTP 401，尚无真实 LLM 准确率。默认 hashing 是词法向量基线，不能说成
已经验证的深度语义检索模型。sentence-transformers 与 API embedding 是可替换
适配器，目前未运行对应模型评估。

## 1. 30 秒 Recruiter-Level 介绍

我做了一个把自然语言问题转换成数据库查询的模块化系统。它先检索相关数据库结构，
再通过带有示例和结构约束的 Prompt 生成 SQL，最后用 SQL 解析器和数据库 EXPLAIN
进行校验，失败时把错误反馈给模型修正。模型没有直接执行数据库操作的权限。
项目还包含只读执行保护、全过程日志、离线测试和 25 道题的结果评估框架。
它结合了我的数据库背景，以及 LLM 应用中的检索、Prompt 和工作流工程能力。

若被问到效果：目前已经验证了离线流程与安全边界，真实模型评估还未完成，
我没有把 Fake 模型的流程测试成绩写成 LLM 准确率。

## 2. 约 2 分钟 Technical Interview 介绍

这个项目的目标是让 Text-to-SQL 的每个阶段都能被单独测试和解释。我没有把它写成
一次 LLM 调用，也没有让 Agent 框架隐藏流程，而是实现了三个明确阶段。

第一阶段是 schema retrieval。系统通过 SQLite introspection 读取表、列、主外键，
把每张表转换成文本，通过 EmbeddingProvider 得到向量，归一化后用点积计算 cosine，
选出 Top-K 表。默认是无需模型下载的 hashing 基线；相同接口可以切换到
sentence-transformers 或 embedding API。这个选择让我能把检索机制与模型质量分开测试。

第二阶段是 SQL generation。Few-shot Store 独立存储问题、所需表和参考 SQL。
先过滤掉依赖未检索表的示例，再检索相似问题。Prompt 包含问题、选中 schema、
可用外键关系、示例和 SQLite 方言，并约束模型只能使用这些表列、显式写 JOIN、
只输出只读 SQL。LLMProvider 可替换，Fake Provider 用于无付费依赖的测试。

第三阶段是 validation 和 correction。Regex 只处理已知输出包装，sqlglot 处理 AST，
检查单语句、只读结构和表范围，SQLite EXPLAIN 负责真实数据库的编译和名称解析。
普通错误会与上一轮 SQL 一起反馈给模型；危险 SQL 立即拒绝，修正次数有限。
通过校验后仍要进入独立 SafeExecutor，重新校验并使用只读连接、authorizer、函数
白名单和执行预算，避免把 Prompt 当成安全边界。

评估上我比较实际查询结果，处理重复行、排序、NULL、浮点误差与截断，分别统计
首次通过、最终校验通过、修正恢复和结果准确率。我实际遇到了 schema 漏检导致
正确 SQL 无法执行的问题，因此保留失败报告，而不是不断调 Prompt 掩盖检索瓶颈。
目前实跑的是 oracle replay；真实 API 认证失败，所以我没有宣称真实模型准确率。

## 3. 5～10 分钟 Architecture 讲解路线

建议按以下顺序打开代码，并使用 README 的 Mermaid 图。重点讲数据流和边界，
不要逐行念代码。正常节奏约 8 分钟，可根据追问扩展到 10 分钟。

### 0:00～0:45：问题与核心约束

先说明输入是自然语言，输出是有列名和行数据的结构化结果，不只是 SQL 字符串。
关键约束有两个：模型看到有限 schema；模型没有数据库执行工具。

输入例子：2025 年消费额最高的五位客户，排除退款订单。
这要求识别 customers、orders、order_items，理解历史 unit_price，按日期过滤并聚合。
如果把 products.price 当成成交价格，SQL 可能可执行但业务答案错误。

### 0:45～1:45：数据库与数据语义

打开 `text2sql/db/seed.py` 与 `text2sql/db/schema.py`。
介绍七张表及外键路径，说明每笔订单有多条明细，也可能有多笔付款。
直接把两张一对多子表连起来会出现乘法式扩张。这不是模型返回 syntax error 的问题，
而是数据库基数与聚合语义问题。

说明数据不是全随机无约束：有固定 seed、跨年日期、退款状态、无订单客户、无销量商品、
历史价格和对账差额。这使 JOIN、NOT EXISTS、CTE、日期和聚合测试都有可解释数据。

### 1:45～3:00：Schema 与 Few-shot 检索

打开 `text2sql/retrieval/schema_index.py`。把文本向量记作 v_i，查询向量记作 q：

```text
score(q, v_i) = dot(q, v_i) / (norm(q) * norm(v_i))
```

代码提前归一化，因此检索时是一次矩阵向量乘法。零向量分数为零；维度改变、NaN
等异常会被检查。当前规模无需 FAISS，逐表打分成本 O(Nd)，完整排序 O(N log N)。

再打开 `fewshot.py`。解释“先 schema 兼容过滤，再按问题相似度排名”，避免示例把
未提供的表引入 Prompt。少于三个兼容示例时就少给，不为凑数泄漏额外 schema。

坦诚默认 hashing 不理解同义词，Top-K 也可能漏桥接表。报告中两题漏了 order_items，
这是下一阶段更换 neural embeddings 或加入 FK 图扩展的动机，不是已经实现的成果。

### 3:00～4:00：Prompt 与 Provider 边界

打开 `generation/prompts.py`、`generation/llm.py`。
解释 system message 中的稳定规则，user JSON 中的问题/schema/examples 数据，
以及 correction 中的 previous_sql/error。JSON 便于边界清晰和调试，但不是防注入证明。

解释 Provider Protocol：核心流程不依赖具体模型 SDK，HTTP adapter 提取 SQL 文本与 usage，
Fake adapter 按脚本返回，用于覆盖失败和重试路径。不能用 Fake 的结果证明 LLM 推理能力。

### 4:00～5:45：三层校验与执行边界

打开 `validation/safety.py`、`validation/validator.py`、`db/connection.py`。

Regex 识别完整 code fence 或有限的前缀，不随意截掉后缀。Parser 识别真正的 SQL AST，
而不是对整个字符串简单搜索 DELETE，避免把字符串值和注释误判成写操作。
遍历 scope 区分 CTE 名和真实表，拒绝多语句、越界表、非只读节点和隐式 JOIN。

随后 EXPLAIN 让 SQLite 编译 SQL，可以得到 unknown column 或 ambiguous column 等错误。
强调 SQLite 的 GROUP BY 比某些数据库宽松，错误 JOIN 也可能正常编译，因此 EXPLAIN
只是一层验证。即使 EXPLAIN 成功，无限递归聚合仍可能在运行时耗尽预算，项目对此有测试。

最后介绍 mode=ro、query_only、authorizer、函数 allowlist、进度回调和行数上限。
最有价值的实现细节是 COUNT(*)：SQLite 的 authorizer 可能把数据库名传成 None，
我通过整合测试发现误拒绝，只为白名单表的空列计数读增加了精确兼容分支。

### 5:45～6:45：有限状态机和 Trace

打开 `agent/correction.py` 与 `agent/pipeline.py`。
用“初次生成未知列 → EXPLAIN 失败 → 带错误重试 → 校验通过 → 受限执行”讲解状态迁移。
`max_retries=3` 明确是首次之后三次修正；危险语句不进入修正；执行错误独立返回。

每一轮有 Attempt，记录 raw output、normalized SQL、validation stage、error、Prompt 长度、
latency 和 usage。最终结果保留所有 attempts，JSONL 按 trace_id 串起证据。
这能区分检索漏表、模型名称错误、Provider 失败和执行超预算。

### 6:45～8:00：评估与实验结论

打开 `evaluation/evaluator.py` 与 `reports/oracle-retrieval.json`。
解释 execution-based comparison 的重复行、列数、排序、NULL 和浮点误差处理。
结果截断必须失败；别名不同不必失败；同一 seed 上碰巧相同并不等于语义等价。

分母需要明确：修正恢复率用首次校验失败的查询作为分母，首次/最终通过率用全部问题。
没有模型输出的 API 错误不应伪装成一次 SQL 校验失败。

展示 Full Schema 与 Top-K 的消融：两组禁用 few-shot，检索组首次 Prompt 更短，
但有两道漏检失败。说明这只有七张表、单次实验、Fake 生成，不能外推真实模型加速或准确率。
最后说明真实 LLM 评估等待有效服务配置，这体现的是实验诚实和工程可追溯性。

## 4. 最可能的 10 个技术问题与参考答案

### 1. 七张表为什么要检索？直接全量输入不更简单吗？

对七张表，全 schema 是合理基线。检索模块是为了验证随 schema 增大时的上下文控制能力，
不是证明七张表必须检索。当前消融只证明这个 fixture 上 Prompt 字符减少，同时存在漏检
代价。下一步应该扩展无关表规模，并使用真实模型比较准确率、tokens 和延迟。

### 2. 你的 Embedding 是真正的语义 Embedding 吗？

默认不是神经语义模型，是确定性 hashing 词法特征。它让项目无下载可运行，也便于测试
cosine 排序。sentence-transformers 和 API adapter 已实现，但没有对应实测成绩。
我会分别评估 encoder 对 schema recall 的影响，而不把统一接口等同于统一检索质量。

### 3. Top-K 漏掉 JOIN 桥接表怎么办？

当前版本会让表范围校验失败并保留错误；单纯修正 SQL 无法保证补足缺失知识。
改进方案是把检索种子表映射到外键图，按最短连接路径补桥接表，同时限制额外表数和
Prompt token 预算。另一个方案是针对 scope error 触发一次受控扩展检索，不能让模型
自由访问全库。这些是未来设计，当前没有声称实现。

### 4. Regex 能防止危险 SQL 吗？

不能单独保证。Regex 只用于输出清理，token 和 AST 检查识别语句结构、嵌套写操作、
多个 statement、CTE scope 等。安全执行还需要数据库强制只读与 authorizer。
字符串中的 'DROP' 不代表 DROP 语句，注释和方言又让纯正则方案更脆弱。

### 5. EXPLAIN 会执行 SQL 吗？能发现所有错误吗？

这里使用 SQLite EXPLAIN，不是 EXPLAIN ANALYZE。它编译并输出虚拟机程序，不运行目标
SELECT，可以暴露语法和名称解析错误。它不能验证业务需求，不会可靠识别错误 JOIN 或
宽松 GROUP BY，也不能证明运行成本可接受。因此执行阶段仍有预算，结果层仍有评估。
换 PostgreSQL 时也不能把 EXPLAIN ANALYZE 当成无执行的 dry run。

### 6. Prompt Injection 绕过只读要求怎么办？

Prompt 约束不是可信边界。模型即使输出 DROP，AST 会拒绝；即使绕过 Agent 调执行器，
执行器仍会重新验证；数据库连接还会限制写入和函数。表 allowlist 来自已检索上下文。
这控制的是 SQL 能力与 schema scope，不等于用户权限体系。生产中的多租户授权必须
由另一个可信层提供，不能让自然语言问题决定权限。

### 7. self-correction 为什么不无限重试？错误会让模型越修越偏吗？

重试有费用与延迟，也可能反复返回同一个错误。当前最多初次加三次修正，每轮提供原问题、
同一 schema、上一轮 SQL 与错误，并重新通过所有校验。危险操作直接停止。
静态上下文能约束范围，但不能自动修复检索漏表或业务歧义。需要进一步区分可修正错误、
可扩展上下文错误和应该向用户澄清的歧义，而不是机械重试。

### 8. Execution Accuracy 为什么比 SQL Exact Match 好？有什么漏洞？

等价 SQL 的别名、JOIN 次序、CTE 或子查询写法可以不同，Exact Match 会误报。
执行比较直接验证这个数据实例上的答案，但空结果、偶然相等、重复行丢失、排序忽略和
结果截断都可能产生假阳性。当前显式处理重复、排序和截断，seed 避免参考查询全空；
进一步需要多 seed、对抗数据、业务语义审查和外部 benchmark。

### 9. 为什么不用 LangChain、FAISS 或 SQLAlchemy？

当前需求是可解释的有限工作流，Python 状态机已经足够。表级向量少，NumPy 精确检索
便于检查，FAISS 的索引构建和调参收益不明显。原生 sqlite3 直接暴露 authorizer 与
progress handler。不是这些工具不好，而是现在的规模和接口不需要它们。
如果改为百万级列/文档向量或多数据库服务，再根据测量引入对应组件。

### 10. 你怎么证明这个项目不是 Fake 演示包装出来的？

我把不同证据分开：Fake 只证明调用顺序与错误路径；真实 SQLite 验证编译、授权、预算和
结果；benchmark 的参考 SQL 在 fixture 上真实执行；Provider 的 HTTP 解析有 Mock 测试；
真实服务探测返回 401，因此该部分明确未验证。仓库提供可以运行真实模型的入口，但不
把实现 adapter 当成已经获得模型成绩。我会展示失败 trace，而不是只展示一个成功截图。

## 5. 根据当前实现优化 Resume Bullet

推荐当前版本，不附模型成绩：

> Built a modular three-stage text-to-SQL pipeline with cosine-based schema retrieval,
> schema-grounded dynamic few-shot prompting, and bounded SQL self-correction;
> implemented regex normalization, AST safety checks, SQLite EXPLAIN validation,
> read-only execution, and a 25-question execution-based evaluation harness.

如果简历空间有限：

> Engineered a three-stage text-to-SQL pipeline with embedding-based schema retrieval,
> dynamic few-shot prompting, and bounded SQL repair, guarded by AST validation,
> SQLite EXPLAIN, and read-only execution.

这里的 embedding-based 是向量表示与相似度检索，不暗示已测过 neural embedding。
实际讨论时主动解释 hashing baseline 和可替换 encoder。

原始描述中的 “using regex and EXPLAIN dry-run parsing” 建议改为
“regex normalization, AST safety checks, and SQLite EXPLAIN validation”，
准确区分三者职责。暂时不要写 “achieved 92% execution accuracy”：仓库里的 92% 是 oracle
replay 的流程结果，不能证明真实 LLM 的能力。

## 6. 每个技术 Claim 的代码对应关系

以下相对链接从本文件跳转到实际代码：

| Claim | 代码证据 | 面试展示点 |
|---|---|---|
| Three-stage pipeline | [pipeline.py](../text2sql/agent/pipeline.py) | run 的阶段与结构化结果 |
| Schema introspection | [connection.py](../text2sql/db/connection.py)、[schema.py](../text2sql/db/schema.py) | PK/FK/列类型与关系文本 |
| Embedding similarity | [embeddings.py](../text2sql/retrieval/embeddings.py)、[schema_index.py](../text2sql/retrieval/schema_index.py) | Provider、归一化与 cosine |
| Dynamic few-shot | [fewshot.py](../text2sql/retrieval/fewshot.py) | schema 子集过滤与排名 |
| Schema-grounded prompting | [prompts.py](../text2sql/generation/prompts.py) | schema/FK/dialect/examples/error 的数据流 |
| Pluggable LLM | [llm.py](../text2sql/generation/llm.py) | Protocol、Fake、HTTP adapter；认证限制如实说明 |
| Regex normalization | [safety.py](../text2sql/validation/safety.py) | 完整 wrapper 清理，不截取危险后缀 |
| AST checks | [safety.py](../text2sql/validation/safety.py) | 单查询、scope、JOIN、只读节点 |
| EXPLAIN validation | [validator.py](../text2sql/validation/validator.py)、[connection.py](../text2sql/db/connection.py) | 编译错误类型与 authorizer |
| Self-correction | [correction.py](../text2sql/agent/correction.py) | 上一轮 SQL/error 与有限重试 |
| Safe execution | [executor.py](../text2sql/db/executor.py)、[connection.py](../text2sql/db/connection.py) | 重校验、只读、预算和截断 |
| Tracing | [observability.py](../text2sql/observability.py) | JSONL 与 trace_id |
| Evaluation harness | [evaluator.py](../text2sql/evaluation/evaluator.py)、[benchmark.json](../text2sql/assets/benchmark.json) | bag 比较、指标分母与可复现结果 |

## 7. 最值得强调的三个 Technical Challenges

**挑战一：有限上下文与关系完整性的冲突。** 检索必须减少无关表，但 SQL 的 JOIN 路径
可能需要语义上不显眼的桥接表。Few-shot 还可能把未检索表带入 Prompt。
当前用 schema 子集过滤避免示例越界，用 scope 校验阻止盲目执行，并通过 schema recall
定位两道漏检失败。下一步是带预算的 FK 图扩展与 neural encoder 对照实验。

**挑战二：把数据库执行能力从模型中隔离。** 仅仅写“只生成 SELECT”远远不够，
SELECT 也可能调用危险函数或消耗大量资源。项目叠加 parser、EXPLAIN、只读 URI、
authorizer 与执行预算，分别处理语法、授权和运行成本。COUNT(*) authorizer 的兼容修复
和递归查询预算测试，是很适合展示的真实工程细节。

**挑战三：区分可执行性、答案正确性和评估有效性。** EXPLAIN 通过不代表业务正确，
结果相同也可能是数据巧合。项目把四类指标分开，比较带重复和排序语义的实际结果，
保存所有失败和运行配置，并将 oracle 与模型评估明确隔离。付款 fan-out、历史价格和
退款过滤能体现数据库系统知识如何帮助 LLM 应用工程。

## 建议现场演示顺序

```bash
python -m unittest discover -v
python -m text2sql.cli --demo
python -m text2sql.cli --evaluate --smoke --output reports/local-interview.json
```

先说明 Fake 模式，再演示错误修正。打开一条失败 trace 和一条成功 trace，而不是只展示
SQL 输出。若后续配置真实模型，再运行不带 `--smoke` 的评估，保留模型版本、数据库哈希
和逐题输出后更新简历。
