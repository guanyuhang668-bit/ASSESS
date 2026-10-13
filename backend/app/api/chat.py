"""学生端聊天 API（Part 2 对话式交互）。

支持：
- 发送文字消息
- 上传 .mdj 文件（解析 + 评分）
- 上传图片（仅存储到 MinIO，不解析）
- 按实验分组调用不同 Agent 策略
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import get_settings
from ..core.db import get_session, get_sessionmaker
from ..core.minio_client import get_minio_url, upload_file_to_minio
from ..core.security import get_current_user
from ..models.chat import ChatCriterionScore, ChatMessage, ChatSession
from ..models.chat import ChatModelCriterionScore, ChatModelResult
from ..models.chat_teacher_score import ChatTeacherScore
from ..models.class_ import SchoolClass
from ..models.user import AppUser
from ..schemas.chat import (
    ChatMessageOut,
    ChatModelCriterionScoreOut,
    ChatModelResultOut,
    ChatSessionDetailOut,
    ChatSessionOut,
    SendMessageOut,
)
from ..models.rubric import RubricVersion
from ..services.agent_strategy import (
    AgentResponse,
    build_rubric_prompt_text,
    extract_criterion_scores,
    run_agent_a,
    run_agent_a_structured,
    run_agent_b,
    run_agent_c,
)
from ..services.grading.rubric_loader import load_rubric_from_db
from ..services.llm.factory import get_llm_pool
from ..services.parser_svc import parse_submission, pick_diagram

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_MDJ_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

VALID_GROUPS = {"agent_a", "agent_b", "agent_c", "control"}
MULTI_MODEL_GROUP = "multi_model_a"
MULTI_MODEL_KEYS = ["gpt4o", "deepseek_v3", "gemini_3_flash", "qwen_3_max"]
_settings = get_settings()
MULTI_MODEL_REQUEST_SEM = asyncio.Semaphore(_settings.multi_model_request_concurrency)
UPLOAD_IO_EXECUTOR = ThreadPoolExecutor(max_workers=_settings.upload_io_threads)


async def _upload_file_async(data: bytes, **kwargs) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        UPLOAD_IO_EXECUTOR,
        lambda: upload_file_to_minio(data, **kwargs),
    )


def _effective_group(user: AppUser) -> str | None:
    """当次实验使用的 agent 分组，优先 session_group，回退到 experiment_group。"""
    return user.session_group or user.experiment_group


def _require_student(user: AppUser):
    if user.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "此接口仅限学生使用")
    if not _effective_group(user):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你的账号尚未分配实验分组，请联系管理员")
    return user


def _msg_to_out(msg: ChatMessage) -> ChatMessageOut:
    """Convert ORM ChatMessage to ChatMessageOut, generating image URL if needed."""
    d = ChatMessageOut(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        mdj_filename=msg.mdj_filename,
        image_filename=msg.image_filename,
        image_url=None,
        score_snapshot=msg.score_snapshot,
        model_results=[],
        created_at=msg.created_at,
    )
    if msg.image_object_key:
        try:
            d.image_url = get_minio_url(msg.image_object_key)
        except Exception:
            d.image_url = None
    if "model_results" not in sa_inspect(msg).unloaded:
        d.model_results = [
            ChatModelResultOut(
                id=r.id,
                model_key=r.model_key,
                status=r.status,
                total_score=r.total_score,
                max_total_score=r.max_total_score,
                normalized_score=r.normalized_score,
                overall_comment=r.overall_comment,
                raw_response=r.raw_response,
                error=r.error,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                elapsed_seconds=r.elapsed_seconds,
                criterion_scores=[
                    ChatModelCriterionScoreOut(
                        id=c.id,
                        code=c.code,
                        score=c.score,
                        max_score=c.max_score,
                        not_applicable=c.not_applicable,
                        has_issue=c.has_issue,
                        brief=c.brief,
                        reasoning=c.reasoning,
                    )
                    for c in (
                        r.criterion_scores
                        if "criterion_scores" not in sa_inspect(r).unloaded
                        else []
                    )
                ],
            )
            for r in msg.model_results
        ]
    return d


def _is_valid_group(group: str | None) -> bool:
    return group in VALID_GROUPS or group == MULTI_MODEL_GROUP


def _clean_markdown_for_students(text: str) -> str:
    import re
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"^[\-\*]\s+", "", line)
        line = re.sub(r"^([✅⚠️❌])", r"\1", line)
        cleaned.append(line)
    return "\n".join(cleaned)


def _format_multi_model_summary(results: list[dict]) -> str:
    ok = [r for r in results if r.get("status") == "success"]
    if not ok:
        return "四模型评估暂时失败，请稍后重新提交或联系教师。"
    lines = ["四模型评估已完成，请查看下方四个模型的独立反馈卡片。", ""]
    for r in results:
        if r.get("status") == "success":
            score = r.get("normalized_score")
            score_text = f"{score:.0f}/100" if isinstance(score, (int, float)) else "—"
            lines.append(f"{r['model_key']}：{score_text}")
        else:
            lines.append(f"{r['model_key']}：调用失败")
    values = [r.get("normalized_score") for r in ok if isinstance(r.get("normalized_score"), (int, float))]
    if values:
        lines.append("")
        lines.append(f"平均分：{sum(values) / len(values):.1f}/100")
    return "\n".join(lines)


async def _run_one_model_agent_a(
    model_key: str,
    client,
    ir_textual: str,
    diagram_type: str,
    problem_statement: str,
    history: list[dict[str, str]],
    rubric_text: str,
    rubric_criteria,
) -> dict:
    try:
        resp = await run_agent_a_structured(
            client=client,
            ir_textual=ir_textual,
            diagram_type=diagram_type,
            problem_statement=problem_statement,
            history=history,
            rubric_text=rubric_text,
            rubric_criteria=rubric_criteria,
        )
        return {
            "model_key": model_key,
            "status": "success",
            "content": _clean_markdown_for_students(resp.content),
            "raw_response": resp.raw_response or resp.content,
            "score": resp.score,
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
            "elapsed_seconds": 0.0,
            "criteria": resp.criteria or [],
            "error": "",
        }
    except Exception as e:
        logger.warning("multi model %s failed: %s", model_key, e)
        return {
            "model_key": model_key,
            "status": "failed",
            "content": "",
            "raw_response": "",
            "score": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "elapsed_seconds": 0.0,
            "criteria": [],
            "error": str(e)[:2000],
        }


# ---------- 会话列表 ----------

@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
):
    """获取当前学生的所有聊天会话。"""
    _require_student(current_user)
    rows = (await session.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )).scalars().all()
    return list(rows)


# ---------- 会话详情（含消息列表） ----------

def _match_criterion_code(pattern: str, code: str) -> bool:
    """根据前缀/完整编号匹配指标编码。

    - 对于 "UC1.4" 这类完整二级指标，要求完全相等
    - 对于 "UC1" 这类一级指标，匹配自身或其子项（UC1、UC1.1、UC1.2 ...）
    """

    if not pattern:
        return False
    pattern = pattern.strip()
    code = (code or "").strip()
    if not code:
        return False
    if "." in pattern:
        # 二级指标：精确匹配
        return code == pattern
    # 一级指标：自身或子项
    return code == pattern or code.startswith(pattern + ".")


ABILITY_DIMENSION_CODES: dict[str, list[str]] = {
    # 1. 需求语义理解：当前未绑定具体编码，如后续有明确映射可在此补充
    "需求语义理解": [],
    # 2. 建模元素识别
    "建模元素识别": ["UC1", "UC2", "CC1", "SC1", "SW1", "SW2"],
    # 3. 关系语义表达
    "关系语义表达": ["UC3", "UC4", "UC5", "CC4", "SC2", "SW3", "SW4"],
    # 4. 动态流程逻辑
    "动态流程逻辑": ["SC3", "SC4", "SW3", "SW5", "SW7"],
    # 5. UML规范表达
    "UML规范表达": ["UC7", "CC6", "SC6", "SW8"],
    # 6. 抽象粒度控制
    "抽象粒度控制": ["UC1.4", "UC2.4", "CC1.4", "CC5", "SW1.4", "SW2.3"],
    # 7. 命名语义清晰
    "命名语义清晰": [
        "UC1.3", "UC2.3",
        "CC1.3", "CC2.3", "CC3.3",
        "SC1.2", "SC2.2",
        "SW1.3", "SW2.2",
    ],
    # 8. 结构完整闭环
    "结构完整闭环": [
        "UC1.1", "UC2.1",
        "CC1.1", "CC2.1", "CC3.1",
        "SC2.1", "SC3.3",
        "SW2.1", "SW7.3",
    ],
}


def _calculate_ability_profile_from_scores(scores: list[ChatCriterionScore]) -> dict[str, float | None]:
    """根据单次 agent 结构化评分结果聚合出 8 个能力维度得分（0-100）。"""

    from collections import defaultdict

    buckets: dict[str, list[float]] = defaultdict(list)
    for sc in scores:
        if sc.not_applicable:
            continue
        if sc.max_score <= 0:
            continue
        try:
            pct = float(sc.score) / float(sc.max_score) * 100.0
        except Exception:
            continue
        code = sc.code or ""
        for dim, patterns in ABILITY_DIMENSION_CODES.items():
            for p in patterns:
                if _match_criterion_code(p, code):
                    buckets[dim].append(pct)
                    break

    result: dict[str, float | None] = {}
    for dim, patterns in ABILITY_DIMENSION_CODES.items():
        vals = buckets.get(dim) or []
        if not vals:
            # 未匹配到任何指标时返回 None，由前端显示“暂无数据”
            result[dim] = None
        else:
            avg = sum(vals) / len(vals)
            result[dim] = round(max(0.0, min(100.0, avg)), 1)
    return result


async def _maybe_build_ability_profile(
    db: AsyncSession,
    cs: ChatSession,
    current_user: AppUser,
) -> dict[str, float | None] | None:
    """仅对 24 级软件工程 C 组（Agent C 渐进式）学生计算能力画像。

    - 只针对当前登录学生自己的会话
    - 只针对有效实验分组为 agent_c 的情况
    - 班级 code 以 "124" 开头视为 24 级软件工程班（12401~12404）
    - 若未找到结构化指标评分，则返回 None
    """

    # 必须是学生本人且为 Agent C 组
    if _effective_group(current_user) != "agent_c":
        return None
    if cs.user_id != current_user.id:
        return None

    # 班级信息（用于近似判断 24 级软件工程）
    cls: SchoolClass | None = None
    if current_user.class_id:
        cls = await db.get(SchoolClass, current_user.class_id)
    if not cls or not cls.code or not cls.code.startswith("124"):
        # 非 24 级软件工程班，不计算画像
        return None

    # 仅使用最新一条带有结构化指标评分的 assistant 消息
    target_msg: ChatMessage | None = None
    for m in reversed(cs.messages):
        if m.role == "assistant" and m.criterion_scores:
            target_msg = m
            break
    if not target_msg:
        return None

    return _calculate_ability_profile_from_scores(list(target_msg.criterion_scores))


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailOut)
async def get_session_detail(
    session_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
):
    """获取单个会话的详情及所有消息。"""
    _require_student(current_user)
    cs = await session.get(
        ChatSession,
        session_id,
        options=[
            selectinload(ChatSession.messages)
            .selectinload(ChatMessage.model_results)
            .selectinload(ChatModelResult.criterion_scores),
            selectinload(ChatSession.messages)
            .selectinload(ChatMessage.criterion_scores),
        ],
    )
    if cs is None or cs.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

    out = ChatSessionDetailOut.model_validate(cs)
    out.messages = [_msg_to_out(m) for m in cs.messages]

    # 仅对 24 级软件工程 C 组 / Agent C 学生返回 UML 建模能力画像
    ability_profile = await _maybe_build_ability_profile(session, cs, current_user)
    if ability_profile is not None:
        out.ability_profile = ability_profile

    return out


# ---------- 发送消息（核心） ----------

@router.post("/send", response_model=SendMessageOut)
async def send_message(
    content: str = Form(""),
    diagram_type: str = Form("use_case"),
    problem_code: str = Form(""),
    problem_statement: str = Form(""),
    session_id: int | None = Form(None, description="已有会话 ID，为空则新建"),
    mdj_file: UploadFile | None = File(None, description=".mdj 文件"),
    image: UploadFile | None = File(None, description="UML 图截图"),
    db: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
):
    """发送消息到 Agent，获取反馈。

    - 可以同时发送文字 + mdj + 图片
    - mdj 文件会被解析并用于评分
    - 图片仅存储到 MinIO
    - 对照组学生不可使用此接口
    """
    _require_student(current_user)
    group = _effective_group(current_user)

    if group == "control":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "你所在的组别（对照组）由教师提供反馈，不使用 Agent 系统",
        )

    if not _is_valid_group(group):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知分组: {group}")

    if diagram_type not in ("use_case", "class", "sequence", "swimlane"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的图类型: {diagram_type}")

    # ---- 强制要求：每轮必须同时上传 mdj 文件和图片 ----
    if not (mdj_file and mdj_file.filename):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "请上传 .mdj 文件（每次提交必须包含 mdj 文件和 UML 图片）",
        )
    if not (image and image.filename):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "请上传 UML 图截图（每次提交必须包含 mdj 文件和 UML 图片）",
        )

    # ---- 限制题目描述长度，避免超出数据库 VARCHAR(4000) 上限 ----
    problem_statement_db = (problem_statement or "").strip()
    if len(problem_statement_db) > 3900:
        problem_statement_db = problem_statement_db[:3900]

    # ---- 处理文件上传 ----
    mdj_object_key = None
    mdj_filename = None
    mdj_raw_data = None

    if mdj_file and mdj_file.filename:
        from pathlib import Path
        ext = Path(mdj_file.filename).suffix.lower()
        if ext != ".mdj":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅支持 .mdj 文件")
        raw_bytes = await mdj_file.read()
        if len(raw_bytes) > MAX_MDJ_SIZE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件过大，上限 10MB")
        try:
            mdj_raw_data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"无效的 mdj 文件: {e}")

        mdj_object_key = await _upload_file_async(
            raw_bytes,
            original_filename=mdj_file.filename,
            prefix=f"students/{current_user.id}/mdj",
            content_type="application/json",
        )
        mdj_filename = mdj_file.filename

    image_object_key = None
    image_filename = None

    if image and image.filename:
        from pathlib import Path
        ext = Path(image.filename).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"不支持的图片格式: {ext}")
        img_bytes = await image.read()
        if len(img_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "图片过大，上限 10MB")

        ct = f"image/{ext.lstrip('.')}"
        if ext == ".jpg":
            ct = "image/jpeg"
        image_object_key = await _upload_file_async(
            img_bytes,
            original_filename=image.filename,
            prefix=f"students/{current_user.id}/images",
            content_type=ct,
        )
        image_filename = image.filename

    # ---- 获取或创建会话 ----
    cs: ChatSession | None = None
    if session_id:
        cs = await db.get(ChatSession, session_id)
        if cs is None or cs.user_id != current_user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")
        # Agent B/C 允许重新提交（重新激活已结束的会话）
        if cs.status != "active":
            if group in ("agent_b", "agent_c", MULTI_MODEL_GROUP):
                cs.status = "active"
                cs.passed = False
            else:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "该会话已结束")
    else:
        cs = ChatSession(
            user_id=current_user.id,
            experiment_group=group,
            diagram_type=diagram_type,
            problem_code=problem_code,
            problem_statement=problem_statement_db,
            status="active",
            round_number=0,
        )
        db.add(cs)
        await db.flush()

    # ---- 解析 mdj (如有) ----
    prev_ir_textual = cs.latest_ir_textual  # 上一轮的 IR，用于对比变化
    ir_textual = cs.latest_ir_textual
    if mdj_raw_data:
        try:
            diagrams = parse_submission(mdj_raw_data)
            picked = pick_diagram(diagrams, cs.diagram_type)
            if picked is None:
                available = [d.diagram_type for d in diagrams] if diagrams else []
                type_labels = {
                    "use_case": "用例图", "class": "类图",
                    "sequence": "时序图", "swimlane": "泳道图",
                }
                expected = type_labels.get(cs.diagram_type, cs.diagram_type)
                found = ", ".join(type_labels.get(t, t) for t in available) if available else "无"
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"mdj 文件中未找到「{expected}」，文件中包含的图类型: {found}。"
                    f"请确认上传的文件与当前会话的图类型（{expected}）匹配。",
                )
            cs.latest_mdj_key = mdj_object_key or ""
            cs.latest_ir_data = picked.model_dump()
            cs.latest_ir_textual = picked.to_textual()
            ir_textual = cs.latest_ir_textual
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"mdj 解析失败: {e}")

    if not ir_textual and not content.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "请上传 .mdj 文件或输入消息内容",
        )

    # ---- 保存用户消息 ----
    display_content = content.strip()
    if mdj_filename and not display_content:
        display_content = f"[上传文件] {mdj_filename}"
    if image_filename and not display_content:
        display_content = f"[上传图片] {image_filename}"
    if not display_content:
        display_content = "[提交作业]"

    user_msg = ChatMessage(
        session_id=cs.id,
        role="user",
        content=display_content,
        mdj_object_key=mdj_object_key,
        mdj_filename=mdj_filename,
        image_object_key=image_object_key,
        image_filename=image_filename,
    )
    db.add(user_msg)
    await db.flush()

    # ---- 检测 IR 是否发生变化 ----
    ir_changed = True
    if cs.round_number > 0 and prev_ir_textual and ir_textual:
        # 对比本轮 IR 与上一轮 IR，判断学生是否真正做了修改
        ir_changed = ir_textual.strip() != prev_ir_textual.strip()

    # ---- 加载评分指标 ----
    rubric_text = ""
    _rubric_criteria = None  # 供后续结构化评分提取
    try:
        _rv = (await db.execute(
            select(RubricVersion).where(
                RubricVersion.diagram_type == cs.diagram_type,
                RubricVersion.is_active.is_(True),
            )
        )).scalar_one_or_none()
        if _rv:
            _rubric_def = await load_rubric_from_db(db, _rv.id)
            rubric_text = build_rubric_prompt_text(_rubric_def.criteria)
            _rubric_criteria = _rubric_def.criteria
    except Exception as e:
        logger.warning("Failed to load rubric for chat: %s", e)

    # ---- 调用 Agent ----
    _llm_client = None  # 供后续结构化评分提取
    multi_model_results: list[dict] = []
    if not ir_textual:
        # 无 IR 时仅保存消息，Agent 提示请先上传 mdj
        assistant_content = (
            "请先上传你的 .mdj 文件（StarUML 格式），我才能对你的 UML 图进行评估和反馈。\n"
            "你也可以同时上传 UML 图截图供参考。"
        )
        agent_resp = AgentResponse(content=assistant_content, score=None, passed=False)
    else:
        # 构建历史消息
        history_msgs = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == cs.id, ChatMessage.id < user_msg.id)
            .order_by(ChatMessage.id)
        )
        history = [
            {"role": m.role, "content": m.content}
            for m in history_msgs.scalars().all()
            if m.role in ("user", "assistant")
        ]

        pool = await get_llm_pool()
        if group == MULTI_MODEL_GROUP:
            missing = [k for k in MULTI_MODEL_KEYS if k not in pool]
            if missing:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    f"四模型配置不完整，缺少: {', '.join(missing)}",
                )
            async with MULTI_MODEL_REQUEST_SEM:
                multi_model_results = await asyncio.gather(*[
                    _run_one_model_agent_a(
                        model_key=k,
                        client=pool[k],
                        ir_textual=ir_textual,
                        diagram_type=cs.diagram_type,
                        problem_statement=cs.problem_statement,
                        history=history,
                        rubric_text=rubric_text,
                        rubric_criteria=_rubric_criteria,
                    )
                    for k in MULTI_MODEL_KEYS
                ])
            scores = [
                r["score"] for r in multi_model_results
                if r.get("status") == "success" and isinstance(r.get("score"), (int, float))
            ]
            avg_score = sum(scores) / len(scores) if scores else None
            agent_resp = AgentResponse(
                content=_format_multi_model_summary([
                    {**r, "normalized_score": r.get("score")}
                    for r in multi_model_results
                ]),
                score=avg_score,
                passed=avg_score is not None and avg_score >= 80,
                prompt_tokens=sum(int(r.get("prompt_tokens") or 0) for r in multi_model_results),
                completion_tokens=sum(int(r.get("completion_tokens") or 0) for r in multi_model_results),
            )
        elif "deepseek_v3" not in pool:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "DeepSeek V3 模型不可用，请联系管理员",
            )
        else:
            client = pool["deepseek_v3"]
            _llm_client = client

            if group == "agent_a":
                agent_resp = await run_agent_a(
                    client=client,
                    ir_textual=ir_textual,
                    diagram_type=cs.diagram_type,
                    problem_statement=cs.problem_statement,
                    history=history,
                    rubric_text=rubric_text,
                )
            elif group == "agent_b":
                agent_resp = await run_agent_b(
                    client=client,
                    ir_textual=ir_textual,
                    diagram_type=cs.diagram_type,
                    problem_statement=cs.problem_statement,
                    history=history,
                    round_number=cs.round_number,
                    ir_changed=ir_changed,
                    prev_score=cs.latest_score,
                    rubric_text=rubric_text,
                )
            elif group == "agent_c":
                agent_resp = await run_agent_c(
                    client=client,
                    ir_textual=ir_textual,
                    diagram_type=cs.diagram_type,
                    problem_statement=cs.problem_statement,
                    history=history,
                    round_number=cs.round_number,
                    prev_score=cs.latest_score,
                    ir_changed=ir_changed,
                    rubric_text=rubric_text,
                )
            else:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知分组: {group}")

    # ---- 清理 Markdown 符号（面向学生友好） ----
    def clean_markdown_for_students(text: str) -> str:
        """去除 Markdown 格式符号，保留评分格式。"""
        import re
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            # 去除标题标记（###, ##, #）
            line = re.sub(r"^#{1,6}\s+", "", line)
            # 去除粗体标记 **text**
            line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
            # 去除列表项标记（-  或 * ）
            line = re.sub(r"^[\-\*]\s+", "", line)
            # 去除行首的 ✅、⚠️ 等特殊符号前的多余空格
            line = re.sub(r"^([✅⚠️❌])", r"\1", line)
            cleaned.append(line)
        return "\n".join(cleaned)

    cleaned_content = _clean_markdown_for_students(agent_resp.content)

    # ---- 保存 Agent 回复 ----
    assistant_msg = ChatMessage(
        session_id=cs.id,
        role="assistant",
        content=cleaned_content,  # 保存清理后的内容
        score_snapshot=agent_resp.score,
        prompt_tokens=agent_resp.prompt_tokens,
        completion_tokens=agent_resp.completion_tokens,
    )
    db.add(assistant_msg)
    await db.flush()  # 获取 assistant_msg.id 供后续关联

    if multi_model_results:
        for item in multi_model_results:
            mr = ChatModelResult(
                session_id=cs.id,
                message_id=assistant_msg.id,
                model_key=item["model_key"],
                status=item["status"],
                total_score=item.get("score"),
                normalized_score=item.get("score"),
                overall_comment=item.get("content") or "",
                raw_response=item.get("raw_response") or "",
                error=item.get("error") or "",
                prompt_tokens=int(item.get("prompt_tokens") or 0),
                completion_tokens=int(item.get("completion_tokens") or 0),
                elapsed_seconds=float(item.get("elapsed_seconds") or 0.0),
            )
            db.add(mr)
            await db.flush()
            for score in item.get("criteria") or []:
                db.add(ChatModelCriterionScore(
                    model_result_id=mr.id,
                    code=score["code"],
                    score=score["score"],
                    not_applicable=score.get("not_applicable", False),
                    has_issue=score.get("has_issue", False),
                    brief=score.get("brief", ""),
                    reasoning=score.get("reasoning", score.get("brief", "")),
                ))

    # ---- 提取结构化指标评分（后台异步执行，不阻塞学生响应） ----
    if _llm_client and _rubric_criteria and ir_textual and not multi_model_results:
        _bg_session_id = cs.id
        _bg_message_id = assistant_msg.id
        _bg_feedback = agent_resp.content
        _bg_ir = ir_textual
        _bg_client = _llm_client
        _bg_criteria = _rubric_criteria

        async def _bg_extract_scores():
            """后台提取结构化评分并写入数据库。"""
            try:
                scores = await extract_criterion_scores(
                    client=_bg_client,
                    agent_feedback=_bg_feedback,
                    ir_textual=_bg_ir,
                    rubric_criteria=_bg_criteria,
                )
                if not scores:
                    return
                maker = get_sessionmaker()
                async with maker() as bg_db:
                    for item in scores:
                        bg_db.add(ChatCriterionScore(
                            session_id=_bg_session_id,
                            message_id=_bg_message_id,
                            code=item["code"],
                            score=item["score"],
                            not_applicable=item.get("not_applicable", False),
                            has_issue=item.get("has_issue", False),
                            brief=item.get("brief", ""),
                        ))
                    await bg_db.commit()
                logger.info(
                    "BG: saved %d criterion scores for session=%d msg=%d",
                    len(scores), _bg_session_id, _bg_message_id,
                )
            except Exception as e:
                logger.warning("BG: extract_criterion_scores failed: %s", e)

        asyncio.create_task(_bg_extract_scores())

    # ---- 将聊天记录同步存入 MinIO (students/{user_id}/chats/) ----
    try:
        chat_record = json.dumps({
            "session_id": cs.id,
            "round": cs.round_number,
            "diagram_type": cs.diagram_type,
            "user_message": display_content,
            "assistant_message": agent_resp.content,
            "score": agent_resp.score,
            "mdj_key": mdj_object_key,
            "image_key": image_object_key,
            "timestamp": str(cs.updated_at or ""),
        }, ensure_ascii=False).encode("utf-8")
        await _upload_file_async(
            chat_record,
            original_filename=f"session_{cs.id}_round_{cs.round_number}.json",
            prefix=f"students/{current_user.id}/chats",
            content_type="application/json",
        )
    except Exception as e:
        logger.warning("Failed to save chat record to MinIO: %s", e)

    # 更新会话状态
    cs.round_number += 1
    if agent_resp.score is not None:
        cs.latest_score = agent_resp.score
    if agent_resp.passed:
        cs.passed = True
        cs.status = "completed"

    # Agent A 模式：一次反馈后结束（但学生仍可重新提交）
    if group == "agent_a" and ir_textual and cs.round_number >= 1:
        # Agent A 不结束会话，允许重新提交但不再给反馈标记
        pass

    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)
    await db.refresh(cs)
    if multi_model_results:
        loaded_assistant = (await db.execute(
            select(ChatMessage)
            .where(ChatMessage.id == assistant_msg.id)
            .options(
                selectinload(ChatMessage.model_results)
                .selectinload(ChatModelResult.criterion_scores),
            )
        )).scalar_one_or_none()
        if loaded_assistant is not None:
            assistant_msg = loaded_assistant

    return SendMessageOut(
        user_message=_msg_to_out(user_msg),
        assistant_message=_msg_to_out(assistant_msg),
        session=ChatSessionOut.model_validate(cs),
    )


# ---------- 获取图片预签名 URL ----------

@router.get("/image-url")
async def get_image_url(
    object_key: str,
    current_user: AppUser = Depends(get_current_user),
):
    """获取 MinIO 图片的预签名访问 URL。"""
    try:
        url = get_minio_url(object_key)
        return {"url": url}
    except Exception as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"获取图片 URL 失败: {e}")


# ---------- 学生查看教师评分 ----------

@router.get("/sessions/{session_id}/scores")
async def student_list_teacher_scores(
    session_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
):
    """学生查看自己某个聊天会话的教师逐条评分。"""
    _require_student(current_user)
    cs = await db.get(ChatSession, session_id)
    if cs is None or cs.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

    stmt = (
        select(ChatTeacherScore)
        .where(ChatTeacherScore.session_id == session_id)
        .options(selectinload(ChatTeacherScore.issues))
        .order_by(ChatTeacherScore.code)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "code": r.code,
            "score": r.score,
            "max_score": r.max_score,
            "not_applicable": r.not_applicable,
            "comment": r.comment,
            "issues": [
                {
                    "id": i.id,
                    "element_refs": i.element_refs,
                    "description": i.description,
                    "severity": i.severity,
                }
                for i in r.issues
            ],
        }
        for r in rows
    ]
