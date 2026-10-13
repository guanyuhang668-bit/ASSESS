# ASSESS: A structured-feedback tool for rubric-grounded UML diagram assessment

**ASSESS：面向评分量表的 UML 图结构化评测与反馈工具**

[English](#english) · [中文](#中文) · 完整中文文档：[README.zh-CN.md](README.zh-CN.md)

---

## English

ASSESS is an open-source classroom tool for formative assessment of UML modeling assignments. It imports StarUML project files and converts them into a structured representation of diagram elements, relationship types and endpoints, behavioral events, and containers. This representation — not a diagram screenshot — is evaluated against the rubric defined for the submitted diagram type, and the result is returned as an overall score, indicator-level scores, localized descriptions of detected problems, and revision suggestions.

The same rubric-grounded assessment can be presented in three ways: one-shot complete feedback, multi-round guided feedback, and progressive feedback, which let instructors control how much diagnostic detail is disclosed to students after each submission. In a course deployment with 127 students, the staged modes were associated with higher mean improvement rates than one-shot complete feedback; progressive feedback showed the highest observed mean improvement rate (61.9%) and positive-improvement coverage (100.0%, n = 32). Scenario-dependent modeling judgments can remain ambiguous, so instructor review stays part of the workflow.

**Scope**

- Diagram types: use-case, class, sequence, and swimlane diagrams.
- Input: StarUML project files (`.mdj`); the diagram image is stored alongside each submission for reference.
- Rubric: diagram-specific primary indicators, each expanded into fine-grained secondary criteria that state concrete modeling requirements; the same indicator set also aggregates into broader modeling dimensions such as element identification, relationship configuration, and notation expression.
- Outputs: total score, indicator-level scores, localized defects, revision suggestions, and ability profiles that help instructors spot recurring difficulties.

**Requirements**

- Local development: Python 3.10+ and Node.js.
- Docker Compose stack: Python 3.11, Node.js 20, PostgreSQL 16, Redis 7, and MinIO.
- A DeepSeek-V3-compatible (or other OpenAI-compatible) LLM service. A built-in `mock` client runs the whole pipeline offline, with no API key and no network.

**Quick start (Docker Compose)**

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
cp backend/.env.example backend/.env    # fill in your own LLM API keys
docker compose up --build
```

Frontend http://localhost:5173 · backend health http://localhost:8000/health · MinIO console http://localhost:9001.
On startup the backend seeds an administrator account and imports the four rubrics from `backend/configs/rubrics/`.

Offline self-check of the parse → rubric scoring → summary pipeline (no database, Redis, or API key required):

```bash
cd backend
python scripts/e2e_mock.py <your.mdj> --rubric configs/rubrics/use_case.yaml
```

**License**

Released under the MIT License (see [LICENSE](LICENSE)).

**Citation**

If you use ASSESS in academic work, please cite: *ASSESS: A structured-feedback tool for rubric-grounded UML diagram assessment*, Binju Huang, Yuhang Guan, Junhao Wang.

---

## 中文

ASSESS 是一款开源课堂工具，用于 UML 建模作业的形成性评价。它导入 StarUML 工程文件，把其中的图元、关系类型与端点、行为事件（消息、活动等）以及容器（生命线、泳道、图级分组）转换为结构化表示；评测针对的是这份结构化表示，而不是截图，并按照提交图类型对应的评分量表（rubric）打分，最终给出总分、指标级得分、缺陷定位描述与修改建议。

同一套"指标—证据—反馈"的评测结果可以按三种方式呈现：单次完整反馈、多轮引导反馈与渐进式反馈，教师据此控制每次提交后向学生披露多少诊断信息。在 127 名学生的课程部署中，分阶段反馈的平均提升率高于单次完整反馈；其中渐进式反馈观察到的平均提升率最高（61.9%），正提升覆盖率 100.0%（n = 32）。依赖题目情境的建模判断仍可能出现歧义，因此教师复核是流程的一部分。

**范围**

- 图类型：用例图、类图、时序图、泳道图。
- 输入：StarUML 工程文件（`.mdj`），每轮同时保存 UML 截图作为对照。
- 评分指标：按图类型组织的一级指标，向下展开为描述具体建模要求的细粒度二级指标；同一套指标还可汇总为更粗的建模能力维度（元素识别、关系配置、表示法表达）。
- 输出：总分、指标级得分、缺陷定位、修改建议，以及供教师发现共性困难的能力画像。

**运行要求**

- 本地开发：Python 3.10+ 与 Node.js。
- Docker Compose 整套环境：Python 3.11、Node.js 20、PostgreSQL 16、Redis 7、MinIO。
- 需可用的 DeepSeek-V3 兼容（或其他 OpenAI 兼容）LLM 服务；内置 `mock` 客户端可在无密钥、无网络的情况下跑通全链路。

**快速开始（Docker Compose）**

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
cp backend/.env.example backend/.env    # 填入自己的 LLM API Key
docker compose up --build
```

前端 http://localhost:5173 · 后端健康检查 http://localhost:8000/health · MinIO 控制台 http://localhost:9001。
后端启动时会自动建立管理员账号，并导入 `backend/configs/rubrics/` 下的四份评分指标。

离线自检（不需要数据库、Redis 与 API Key），用于跑通"解析 → 按指标打分 → 汇总"链路：

```bash
cd backend
python scripts/e2e_mock.py <你的.mdj 路径> --rubric configs/rubrics/use_case.yaml
```

**许可**

本项目以 MIT 许可证发布（见 [LICENSE](LICENSE)）。

**引用**

如在学术工作中使用 ASSESS，请引用：*ASSESS: A structured-feedback tool for rubric-grounded UML diagram assessment*，作者 Binju Huang、Yuhang Guan、Junhao Wang。

---

## 仓库说明 / Repository note

- 本页是仓库首页的中英对照简要说明；完整中文技术文档（目录结构、配置项、HTTP API、评分管线、生产部署要点、上线前安全清单）见 [README.zh-CN.md](README.zh-CN.md)。
- This page is the bilingual overview shown on the repository home page. The full technical documentation (in Chinese) — directory layout, configuration, HTTP API, grading pipeline, deployment notes, and a pre-release security checklist — is in [README.zh-CN.md](README.zh-CN.md).
