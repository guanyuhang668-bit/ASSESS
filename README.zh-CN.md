# UML 自动批改 Agent

基于大语言模型的 UML 图自动批改与教学实验平台。学生提交 StarUML `.mdj` 源文件 + UML 截图，后端把 `.mdj` 解析为结构化中间表示（IR），再按 YAML 评分指标做分步（CoT）打分；教师端对同一批作品做人工标注，系统输出「模型 vs 教师」一致性分析，供教学研究取数。

- **确定性部分**：`.mdj` → IR 的解析完全离线、可复现，不依赖 LLM
- **模型部分**：同一份 IR 交给多个 LLM，按 rubric 分组逐条打分 + 汇总
- **教学部分**：学生分四个实验组接受不同反馈策略，聊天与提交全程留痕

> 本仓库**只含源代码与配置**。学生数据、数据库 / 对象存储快照、`node_modules`、`.venv` 等均未入库，见文末「仓库内容说明」。

## 主要能力

- **四类 UML 图**：用例图 / 类图 / 时序图 / 泳道图，统一解析为 IR 后走同一套评分管线
- **分步打分**：按一级指标分组的 CoT 提示，输出每条二级指标的得分、理由与问题描述
- **多模型对比**：`gpt-4o` · `deepseek-v3-250324` · `gemini-3-flash-preview` · `qwen3-max`，外加不联网的 `mock` 客户端
- **教师标注 + 一致性分析**：MAE / Spearman / P-R-F1 / Bootstrap CI，可导出论文用图表
- **学生端 AI 助手**：四种反馈策略（单次反馈 / 多轮引导 / 渐进式 / 教师对照），按分组生效
- **实时进度**：WebSocket `/ws/runs/{run_id}` 推送批改任务状态
- **班级与账号管理**：xlsx 批量导入学生、按班级批量分配实验分组

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI · SQLAlchemy 2（async）· Pydantic v2 · Alembic |
| 任务队列 | ARQ（Redis） |
| 存储 | PostgreSQL 16 · Redis 7 · MinIO（对象存储） |
| LLM | OpenAI 兼容接口 / Anthropic / Mock，统一 `BaseLLMClient` |
| 评分 | mdj 解析 → IR → rubric 分组 CoT → 汇总 |
| 前端 | Vite · React 18 · TypeScript · Tailwind · TanStack Query · Zustand · Recharts |
| 分析 | pandas · numpy · scipy · pingouin |
| 工具链 | ruff（line-length 100）· pytest · ESLint |

## 目录结构

```
uml-grader/
├── backend/
│   ├── app/
│   │   ├── api/              # auth · admin · submissions · rubrics · grading · teacher
│   │   │                     # · analysis · chat · activity · files · ws
│   │   ├── core/             # config · db · security · minio_client
│   │   ├── models/           # SQLAlchemy ORM
│   │   ├── schemas/          # Pydantic v2
│   │   ├── services/
│   │   │   ├── grading/      # cot_runner · repair · rubric_loader
│   │   │   ├── llm/          # base · factory · openai_compat · anthropic_client · mock_client
│   │   │   ├── agent_strategy.py   # 学生端四种反馈策略
│   │   │   └── auto_grade.py · grading_svc.py · parser_svc.py
│   │   ├── uml_grader/       # ir.py · parsers/mdj.py · grader/schema.py
│   │   ├── workers/          # ARQ worker · enqueue
│   │   └── main.py           # FastAPI 入口（/health · /uploads · /docs）
│   ├── alembic/              # 数据库迁移
│   ├── configs/
│   │   ├── models.yaml       # LLM 池配置
│   │   ├── prompts/          # Jinja2：system · rubric_step · summary_step
│   │   └── rubrics/          # 4 份 YAML 评分指标
│   ├── scripts/              # seed · e2e_mock · batch_upload · validate_parser
│   │                         # · xlsx_to_rubrics · backfill_activity
│   │                         # · import_multi_model_students · stress_test
│   ├── Dockerfile · pyproject.toml · alembic.ini · .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/            # 17 个页面
│   │   ├── components/       # Layout
│   │   ├── lib/              # api.ts · queryClient.ts
│   │   └── store/            # auth · activity（zustand）
│   ├── vite.config.ts · tailwind.config.js · postcss.config.js
│   ├── tsconfig.json · Dockerfile · index.html · package.json
├── scripts/                  # benchmark_models · benchmark_analysis · benchmark_retry
└── docker-compose.yml
```

## 快速开始

### 方式 A：Docker Compose（一键起全栈）

```bash
cp backend/.env.example backend/.env      # 按需填 OPENAI_API_KEY / DEEPSEEK_API_KEY 等
docker compose up --build
```

启动后：前端 http://localhost:5173 · 后端 http://localhost:8000（`/docs` 仅开发环境开放）· MinIO 控制台 http://localhost:9001

Compose 会自动拉起 `postgres` / `redis` / `minio` / `backend` / `worker` / `frontend`，backend 容器启动时先执行 `scripts/seed.py` 建好管理员并导入 4 份 rubric。

### 方式 B：本地开发（不用 Docker）

```bash
# ---- 后端 ----
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

# 建表二选一：
alembic upgrade head                                  # 生产 / 正式使用
# 或在 .env 里设 AUTO_CREATE_TABLES=true，启动时自动建表（开发期）

python scripts/seed.py --admin-user you --admin-pass '<你的口令>'
arq app.workers.grading_worker.WorkerSettings &       # 批改 worker（另开一个终端）
uvicorn app.main:app --reload                         # http://localhost:8000/health

# ---- 前端 ----
cd ../frontend
npm install
npm run dev                                           # http://localhost:5173
```

前端 axios 的 `baseURL` 是相对路径 `/api`，开发环境下由 Vite 把 `/api`、`/uploads`、`/ws` 代理到 `http://localhost:8000`（可用 `VITE_API_BASE_URL` / `VITE_WS_BASE_URL` 覆盖）。

### 方式 C：离线自检（不需要数据库 / Redis / API Key）

用 `mock` LLM 客户端把「解析 + CoT 打分 + 汇总」整条链路跑通，适合改完 parser 或 prompt 后快速回归：

```bash
cd backend
python scripts/e2e_mock.py <你的.mdj 路径> --rubric configs/rubrics/use_case.yaml
python scripts/e2e_mock.py <你的.mdj 路径> --rubric configs/rubrics/class.yaml
```

输出示例：

```
[·] parsed: 7 elements, 6 relations, 1 containers
[·] rubric: use_case / v1 · 30 criteria
LLM 百分制总分 : 85.89 / 100
按指标加权     : 23.92 / 30.00  (79.7%)
```

其他脚本：

| 脚本 | 用途 |
|---|---|
| `scripts/seed.py` | 建管理员账号 + 导入 `configs/rubrics/*.yaml`（`--admin-user/--admin-pass/--skip-rubrics/--version`） |
| `scripts/validate_parser.py` | 遍历目录下所有 `.mdj` 跑 parser，输出核对表格 |
| `scripts/batch_upload.py` | 批量上传 `.mdj` 到指定班级/图类型（`--dir/--class-code/--diagram-type`，或 `--all`） |
| `scripts/xlsx_to_rubrics.py` | 把指标 xlsx 转成 4 份 YAML rubric |
| `scripts/backfill_activity.py` | 依据聊天事件回填历史使用时长 |
| `scripts/stress_test.py` | 模拟并发学生聊天，压测 |
| `scripts/import_multi_model_students.py` | 批量导入「四模型班级」学生并设为对应实验组 |

## 配置（`backend/.env`）

以 `backend/.env.example` 为准，**所有密钥只走环境变量**，不要写进代码或 `models.yaml`。

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_ENV` | `development` | 非 `development` 时关闭 `/docs`，并强制校验 `JWT_SECRET` |
| `DEBUG` | `true` | 调试开关 |
| `AUTO_CREATE_TABLES` | `false` | `true` 时启动用 SQLAlchemy 自动建表，免 alembic |
| `CORS_ORIGINS` | `["http://localhost:5173","http://localhost:3000"]` | 允许的前端来源 |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | `localhost/5432/uml_grader/.../uml_grader` | 数据库连接 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `10` | 连接池 |
| `REDIS_HOST/PORT/DB` | `localhost/6379/0` | ARQ 队列后端 |
| `MINIO_ENDPOINT` | `localhost:9000` | 对象存储；不可用时自动回退本地 `uploads/` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET` / `MINIO_SECURE` | `minioadmin` / `minioadmin` / `uml-grader` / `false` | 演示值，部署前必改 |
| `JWT_SECRET` | `dev-secret-change-me` | **生产必须改**，否则后端拒绝启动 |
| `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | `HS256` / `1440` | 令牌签名与有效期 |
| `OPENAI_API_KEY` · `ANTHROPIC_API_KEY` · `DEEPSEEK_API_KEY` · `DASHSCOPE_API_KEY` · `GEMINI_API_KEY` · `QWEN3_API_KEY` | 空 | 按 `models.yaml` 里各模型声明的 `env_var` 注入，留空则该模型不装载 |
| `LLM_CONCURRENCY_PER_MODEL` | `{"gpt4o":5,"deepseek_v3":80,"gemini_3_flash":10}` | 每模型并发上限 |
| `MULTI_MODEL_REQUEST_CONCURRENCY` | `3` | 多模型对比任务的并发 |
| `UPLOAD_IO_THREADS` | `16` | 上传落盘线程数 |

## 模型池（`backend/configs/models.yaml`）

| key | 模型 | provider | 密钥来源 |
|---|---|---|---|
| `gpt4o` | `gpt-4o` | `openai_compat` | `OPENAI_API_KEY` |
| `deepseek_v3` | `deepseek-v3-250324` | `openai_compat` | `DEEPSEEK_API_KEY` |
| `gemini_3_flash` | `gemini-3-flash-preview` | `openai_compat` | `GEMINI_API_KEY` |
| `qwen_3_max` | `qwen3-max` | `openai_compat`（DashScope 兼容模式） | `QWEN3_API_KEY` |
| （内置） | 合成输出 | `mock` | 无需密钥，不联网 |

- `provider` 支持 `openai` / `openai_compat` / `anthropic` / `mock`；换官方端点或自建 vLLM 只改 `base_url`
- 默认 `temperature: 0.0`、`seed: 42`，保证打分可复现
- 注释掉某个模型即可把它从 LLM 池里摘掉，前端下拉框随之变化

## 评分管线

| 步骤 | 位置 | 说明 |
|---|---|---|
| 1. 解析 | `app/uml_grader/parsers/mdj.py` → `app/uml_grader/ir.py` | `.mdj`（StarUML JSON）→ 元素 / 关系 / 容器的 IR，纯确定性 |
| 2. 载入指标 | `app/services/grading/rubric_loader.py` + `configs/rubrics/*.yaml` | 一级指标分组、二级指标、权重、常见错误 |
| 3. 分步打分 | `app/services/grading/cot_runner.py` + `configs/prompts/*.j2` | 按分组跑 CoT，逐条给出得分 / 理由 / issues |
| 4. 修复与汇总 | `app/services/grading/repair.py` | 修复 LLM 的 JSON 输出偏差，汇总成百分制 + 加权分 |
| 5. 异步与推送 | `app/workers/grading_worker.py` · `app/api/ws.py` | ARQ 队列执行 `run_grading_run`，WebSocket 回推进度 |

## 图类型与评分指标

| 图类型 | rubric 文件 | 二级指标数 | diagram_type |
|---|---|---|---|
| 用例图 | `configs/rubrics/use_case.yaml` | 30 | `use_case` |
| 类图 | `configs/rubrics/class.yaml` | 26 | `class` |
| 时序图 | `configs/rubrics/sequence.yaml` | 23 | `sequence` |
| 泳道图 | `configs/rubrics/swimlane.yaml` | 27 | `swimlane` |

指标 YAML 除指标本身外，还带有既往教学中统计的 `error_freq_total` / `error_freq_by_class`（各班级出错频次），用作打分时的常见错误提示。

## HTTP API 概览

前缀 `/api`，路由集中在 `backend/app/api/`：

| 路由 | 职责 |
|---|---|
| `/api/auth` | 登录、改密、当前用户 |
| `/api/admin` | 班级 / 学生管理、批量导入、实验分组分配与统计 |
| `/api/submissions` | 提交与文件管理 |
| `/api/rubrics` | 评分指标的增删改查与版本 |
| `/api/grading` | 触发批改、查询 run 与逐条结果 |
| `/api/teacher` | 教师人工标注 |
| `/api/analysis` | 一致性分析（MAE / Spearman / P-R-F1）与导出 |
| `/api/chat` | 学生端 AI 助手会话与消息 |
| `/api/activity` | 使用行为日志 |
| `/api/files` · `/uploads` | 文件下载 / 上传件静态托管 |
| `/ws/runs/{run_id}` | WebSocket：批改进度实时推送 |
| `/health` | 健康检查，返回 `{"status":"ok"}` |

## 学生端与实验分组

学生登录后进入「AI 助手」，每轮**同时上传 `.mdj` 与 UML 截图**，系统按所在分组调用对应反馈策略：

| 分组代码 | 名称 | 反馈策略 |
|---|---|---|
| `agent_a` | 单次反馈 | 提交后一次给出完整评分 + 全部问题 + 修改建议 |
| `agent_b` | 多轮引导 | 每轮只指出 1–2 个最关键问题，改完再交，循环到达标 |
| `agent_c` | 渐进式 | 先给方向不给答案，未改善再逐步深入 |
| `control` | 对照组 | 不给 AI 反馈，由教师线下批改 |

分组可通过管理员「实验分组」页按班级批量分配，也可在导入学生的 xlsx 里加「分组」列指定。

## 数据存放

上传件与聊天记录优先写入 MinIO，按学生隔离；MinIO 不可用时自动回退到本地 `backend/uploads/`（该目录已 gitignore）。

```
{MINIO_BUCKET}/
└── students/{user_id}/
    ├── mdj/{uuid}.mdj        # 每轮提交的源文件
    ├── images/{uuid}.png     # 对应截图
    └── chats/session_{id}_round_{n}.json   # 每轮问答归档
```

## 仓库内容说明

本仓库是**代码快照**，以下内容有意未包含：

| 未包含 | 原因 | 本地补齐方式 |
|---|---|---|
| `backend/.env` | 含真实密钥 | `cp backend/.env.example backend/.env` 后填自己的 key |
| `backend/.venv`、`frontend/node_modules` | 依赖体积 | `pip install -e ".[dev]"` / `npm install` |
| `backend/uploads/` | 学生上传作品 | 运行时自动创建 |
| 数据库 / MinIO / Redis 数据快照 | 教学数据，不公开 | 用 `alembic upgrade head` + `scripts/seed.py` 起空库 |
| `deployment/`（systemd / nginx 配置） | 环境相关 | 按下方「生产部署要点」自建 |
| 各类成绩表、名单、论文稿 | 个人与教学数据 | — |

## 上线前安全清单

- [ ] `JWT_SECRET` 换成足够长的随机串（非 `development` 环境仍用默认值时，`app/main.py` 会直接抛错拒绝启动）
- [ ] `POSTGRES_PASSWORD`、`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` 改掉 `docker-compose.yml` 与 `.env.example` 里的演示值
- [ ] 建管理员时显式指定口令：`python scripts/seed.py --admin-user you --admin-pass '<强口令>'`，不要沿用脚本默认值
- [ ] 学生导入的初始口令规则（学号 + 固定后缀）建议在正式收数据前调整，或要求学生首登改密
- [ ] `APP_ENV=production`（自动关闭 `/docs`、`/redoc`）
- [ ] `.env` 已在 `.gitignore` 中；提交前用 `git status` 再确认一遍没有密钥文件混入

## 开发与测试

```bash
# 后端静态检查
cd backend && ruff check .

# 后端测试
pytest

# 前端
cd frontend && npm run lint && npm run build     # build = tsc -b && vite build
```

改动 parser / prompt 后，最省事的回归方式是方式 C 的 `e2e_mock.py`；`scripts/benchmark_*.py` 用于批量跑多模型基准并出图（结果目录不入库）。

## 生产部署要点

- 前端 `npm run build` 出静态产物，交给 nginx 直接托管 `frontend/dist`，并反代 `/api`、`/uploads`、`/ws`（WebSocket 需带 `Upgrade` 头）
- 后端 `uvicorn app.main:app --host 0.0.0.0 --port 8000`，worker 用 `arq app.workers.grading_worker.WorkerSettings` 单独守护（两者都要常驻）
- 小内存机器上把 uvicorn `--workers` 调小并加 swap；多模型对比会同时占用多个 LLM 连接，注意 `MULTI_MODEL_REQUEST_CONCURRENCY`
- 数据库用 `alembic upgrade head` 迁移，投产时把 `AUTO_CREATE_TABLES` 置为 `false`
