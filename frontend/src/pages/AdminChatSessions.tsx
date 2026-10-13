import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  adminListChatSessions,
  adminGetChatSession,
  downloadUmlArtifacts,
  listClasses,
  listChatTeacherScores,
  upsertChatTeacherScore,
  listRubricVersions,
  getRubricDetail,
  type AdminChatSession,
  type AdminChatSessionDetail,
  type ChatTeacherScoreIn,
} from "@/lib/api";
import {
  MessageSquare,
  ChevronLeft,
  FileText,
  Image as ImageIcon,
  Trophy,
  User,
  Clock,
  Save,
  CheckCircle2,
  ClipboardCheck,
  X,
  ZoomIn,
  Download,
  Loader2,
} from "lucide-react";
import { clsx } from "clsx";

const GROUP_LABELS: Record<string, string> = {
  agent_a: "Agent A",
  agent_b: "Agent B",
  agent_c: "Agent C",
  control: "对照组",
  multi_model_a: "四模型A",
};

const GROUP_COLORS: Record<string, string> = {
  agent_a: "bg-blue-100 text-blue-700",
  agent_b: "bg-purple-100 text-purple-700",
  agent_c: "bg-amber-100 text-amber-700",
  control: "bg-slate-100 text-slate-700",
  multi_model_a: "bg-emerald-100 text-emerald-700",
};

const DIAGRAM_LABELS: Record<string, string> = {
  use_case: "用例图",
  class: "类图",
  sequence: "时序图",
  swimlane: "泳道图",
};

function formatTime(ts: string) {
  return new Date(ts).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---- 逐条评分行状态 ----
interface RowState {
  score: number;
  max_score: number;
  not_applicable: boolean;
  comment: string;
  issues: { element_refs: string[]; description: string; severity: string }[];
  dirty: boolean;
  saved?: boolean;
}

// ---- 评分面板组件 ----
function ScoringPanel({ sessionId, diagramType }: { sessionId: number; diagramType: string }) {
  const qc = useQueryClient();

  const versionsQ = useQuery({
    queryKey: ["rubric-versions", diagramType],
    queryFn: () => listRubricVersions(diagramType),
  });
  const activeRubric = versionsQ.data?.find((v) => v.is_active);

  const rubricQ = useQuery({
    queryKey: ["rubric-detail", activeRubric?.id],
    queryFn: () => (activeRubric ? getRubricDetail(activeRubric.id) : Promise.resolve(null)),
    enabled: !!activeRubric,
  });

  const teacherQ = useQuery({
    queryKey: ["chat-teacher-scores", sessionId],
    queryFn: () => listChatTeacherScores(sessionId),
  });

  const [rows, setRows] = useState<Record<string, RowState>>({});

  useEffect(() => {
    if (!rubricQ.data) return;
    const next: Record<string, RowState> = {};
    rubricQ.data.criteria.forEach((c) => {
      const existing = teacherQ.data?.find((t) => t.code === c.code);
      if (existing) {
        next[c.code] = {
          score: existing.score,
          max_score: existing.max_score,
          not_applicable: existing.not_applicable,
          comment: existing.comment,
          issues: (existing.issues || []).map((i) => ({
            element_refs: i.element_refs, description: i.description, severity: i.severity,
          })),
          dirty: false, saved: true,
        };
      } else {
        next[c.code] = {
          score: c.max_score, max_score: c.max_score,
          not_applicable: false, comment: "", issues: [],
          dirty: false,
        };
      }
    });
    setRows(next);
  }, [rubricQ.data, teacherQ.data]);

  const saveMut = useMutation({
    mutationFn: (body: ChatTeacherScoreIn) => upsertChatTeacherScore(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chat-teacher-scores", sessionId] }),
  });

  function update(code: string, patch: Partial<RowState>) {
    setRows((prev) => ({
      ...prev, [code]: { ...prev[code], ...patch, dirty: true, saved: false },
    }));
  }

  async function saveOne(code: string) {
    const row = rows[code];
    if (!row) return;
    await saveMut.mutateAsync({
      session_id: sessionId, code,
      score: row.score, max_score: row.max_score,
      not_applicable: row.not_applicable, comment: row.comment,
      issues: row.issues,
    });
    setRows((p) => ({ ...p, [code]: { ...p[code], dirty: false, saved: true } }));
  }

  async function saveAll() {
    for (const [code, row] of Object.entries(rows)) {
      if (row.dirty) await saveOne(code);
    }
  }

  if (!activeRubric) {
    return (
      <div className="p-4 bg-amber-50 text-amber-800 text-sm rounded">
        该图类型（{DIAGRAM_LABELS[diagramType] || diagramType}）尚无激活的评分标准，请先在「评分标准」页导入并激活。
      </div>
    );
  }

  if (!rubricQ.data) return <div className="text-sm text-slate-400">加载评分标准中…</div>;

  const dirtyCount = Object.values(rows).filter((r) => r.dirty).length;
  const totalScore = Object.values(rows).reduce((s, r) => s + (r.not_applicable ? 0 : r.score), 0);
  const totalMax = Object.values(rows).reduce((s, r) => s + (r.not_applicable ? 0 : r.max_score), 0);

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-1">
          <ClipboardCheck size={16} /> 教师评分
        </h2>
        <span className="text-xs text-slate-500">
          {totalScore.toFixed(2)} / {totalMax.toFixed(2)}
        </span>
        <button
          onClick={saveAll}
          disabled={dirtyCount === 0 || saveMut.isPending}
          className="ml-auto px-3 py-1 bg-brand-600 text-white rounded text-xs hover:bg-brand-700 disabled:opacity-60 flex items-center gap-1"
        >
          <Save size={12} /> 保存全部 ({dirtyCount})
        </button>
      </div>

      <div className="space-y-2 max-h-[calc(100vh-16rem)] overflow-y-auto pr-1">
        {rubricQ.data.criteria.map((c) => {
          const row = rows[c.code];
          if (!row) return null;
          return (
            <div key={c.code} className={clsx(
              "bg-white border rounded p-3",
              row.saved ? "border-green-200" : row.dirty ? "border-amber-300" : "border-slate-200",
            )}>
              <div className="flex items-center gap-2 text-sm">
                <span className="font-mono text-xs text-brand-600 shrink-0">{c.code}</span>
                <span className="font-medium flex-1 text-xs">{c.name}</span>
                {row.saved && <CheckCircle2 size={12} className="text-green-600" />}
                {row.dirty && <span className="text-[10px] text-amber-600">未保存</span>}
              </div>
              {c.description && (
                <div className="text-[11px] text-slate-500 mt-1">{c.description}</div>
              )}

              <div className="flex items-center gap-2 mt-2">
                <input
                  type="number" step="0.05" min={0} max={row.max_score}
                  value={row.score}
                  onChange={(e) => update(c.code, { score: Math.max(0, Math.min(row.max_score, Number(e.target.value) || 0)) })}
                  className="w-16 px-2 py-1 border border-slate-300 rounded text-xs"
                />
                <span className="text-[11px] text-slate-500">/ {row.max_score}</span>
                <label className="text-[11px] text-slate-500 flex items-center gap-1 ml-1">
                  <input
                    type="checkbox" checked={row.not_applicable}
                    onChange={(e) => update(c.code, { not_applicable: e.target.checked })}
                  />
                  N/A
                </label>
                <button onClick={() => saveOne(c.code)}
                  className="ml-auto text-[11px] text-brand-600 hover:underline disabled:opacity-40"
                  disabled={!row.dirty}>
                  保存
                </button>
              </div>

              <textarea
                value={row.comment}
                onChange={(e) => update(c.code, { comment: e.target.value })}
                placeholder="评语（可选）"
                className="w-full mt-2 px-2 py-1 border border-slate-200 rounded text-[11px]"
                rows={1}
              />

              {row.issues.length > 0 && (
                <div className="mt-1">
                  <div className="text-[10px] text-slate-600 mb-1">已记录缺陷</div>
                  <ul className="space-y-1">
                    {row.issues.map((i, idx) => (
                      <li key={idx} className="text-[11px] bg-red-50 text-red-700 px-2 py-0.5 rounded flex items-start gap-1">
                        <span className="flex-1">{i.description}</span>
                        <button onClick={() => update(c.code, {
                          issues: row.issues.filter((_, j) => j !== idx),
                        })} className="text-red-500 shrink-0">✕</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---- 主页面 ----
export default function AdminChatSessions() {
  const [searchParams] = useSearchParams();
  const initialUserId = searchParams.get("user_id")
    ? Number(searchParams.get("user_id"))
    : undefined;
  const initialGroup = searchParams.get("group") || "";

  const [filterGroup, setFilterGroup] = useState(initialGroup);
  const [filterSessionGroup, setFilterSessionGroup] = useState("");
  const [filterClassId, setFilterClassId] = useState<number | undefined>();
  const [filterDiagramType, setFilterDiagramType] = useState("");
  const [filterUserId] = useState<number | undefined>(initialUserId);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);

  const classesQ = useQuery({
    queryKey: ["classes"],
    queryFn: listClasses,
  });

  const sessionsQ = useQuery({
    queryKey: ["admin-chat-sessions", filterGroup, filterSessionGroup, filterClassId, filterDiagramType, filterUserId],
    queryFn: () =>
      adminListChatSessions({
        experiment_group: filterGroup || undefined,
        session_group: filterSessionGroup || undefined,
        class_id: filterClassId,
        diagram_type: filterDiagramType || undefined,
        user_id: filterUserId,
      }),
  });

  const detailQ = useQuery({
    queryKey: ["admin-chat-session", selectedSessionId],
    queryFn: () => adminGetChatSession(selectedSessionId!),
    enabled: selectedSessionId != null,
  });

  const sessions = sessionsQ.data || [];
  const detail = detailQ.data;

  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const exportMut = useMutation({
    mutationFn: () => downloadUmlArtifacts({
      experiment_group: filterGroup || undefined,
      session_group: filterSessionGroup || undefined,
      class_id: filterClassId,
      diagram_type: filterDiagramType || undefined,
      user_id: filterUserId,
    }),
    onError: () => alert("导出失败，请稍后重试或联系管理员查看后端日志。"),
  });

  if (selectedSessionId && detail) {
    return (
      <div>
        {/* 图片灯箱 */}
        {lightboxUrl && (
          <div
            className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
            onClick={() => setLightboxUrl(null)}
          >
            <button
              onClick={() => setLightboxUrl(null)}
              className="absolute top-4 right-4 text-white hover:text-slate-300 transition"
            >
              <X size={28} />
            </button>
            <img
              src={lightboxUrl}
              alt="enlarged"
              className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}
        <button
          onClick={() => setSelectedSessionId(null)}
          className="flex items-center gap-1 text-sm text-brand-600 hover:underline mb-4"
        >
          <ChevronLeft size={16} /> 返回列表
        </button>

        {/* 会话信息头 */}
        <div className="bg-white rounded-lg border border-slate-200 p-4 mb-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="flex items-center gap-1 font-medium text-slate-700">
              <User size={14} /> {detail.display_name} ({detail.username})
            </span>
            <span
              className={clsx(
                "px-2 py-0.5 rounded-full text-xs font-medium",
                GROUP_COLORS[detail.experiment_group] || "bg-slate-100 text-slate-600"
              )}
            >
              {GROUP_LABELS[detail.experiment_group] || detail.experiment_group}
            </span>
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
              {DIAGRAM_LABELS[detail.diagram_type] || detail.diagram_type}
            </span>
            {detail.latest_score != null && (
              <span className="flex items-center gap-1 text-xs font-medium text-green-600">
                <Trophy size={12} /> AI评分: {detail.latest_score}分
              </span>
            )}
            <span className="text-xs text-slate-400">
              第{detail.round_number}轮 · {detail.status === "active" ? "进行中" : detail.status}
            </span>
          </div>
          {detail.problem_statement && (
            <div className="mt-2 text-xs text-slate-500">
              题目：{detail.problem_statement}
            </div>
          )}
        </div>

        {/* 左右分栏：聊天记录 + 评分 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 左：消息列表 */}
          <div className="space-y-3 max-h-[calc(100vh-16rem)] overflow-y-auto pr-1">
            {detail.messages.map((msg) => (
              <div
                key={msg.id}
                className={clsx(
                  "rounded-lg p-3 text-sm",
                  msg.role === "user"
                    ? "bg-brand-50 border border-brand-100 ml-6"
                    : "bg-white border border-slate-200 mr-6"
                )}
              >
                <div className="flex items-center gap-2 mb-1.5 text-xs text-slate-500">
                  <span className="font-medium">
                    {msg.role === "user" ? "🧑‍🎓 学生" : "🤖 AI 助手"}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock size={10} /> {formatTime(msg.created_at)}
                  </span>
                  {msg.score_snapshot != null && (
                    <span className="flex items-center gap-1 text-green-600 font-medium">
                      <Trophy size={10} /> {msg.score_snapshot}分
                    </span>
                  )}
                </div>

                <div className="flex gap-2 mb-1.5">
                  {msg.mdj_filename && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 rounded text-xs text-slate-600">
                      <FileText size={10} /> {msg.mdj_filename}
                    </span>
                  )}
                  {msg.image_filename && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 rounded text-xs text-slate-600">
                      <ImageIcon size={10} /> {msg.image_filename}
                    </span>
                  )}
                </div>

                {msg.image_url && (
                  <div className="mb-1.5 relative group inline-block">
                    <img
                      src={msg.image_url}
                      alt="uploaded"
                      className="max-w-full max-h-48 rounded border border-slate-200 cursor-pointer hover:opacity-90 transition"
                      onClick={() => setLightboxUrl(msg.image_url)}
                    />
                    <div
                      className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/10 transition rounded cursor-pointer"
                      onClick={() => setLightboxUrl(msg.image_url)}
                    >
                      <ZoomIn size={24} className="text-white opacity-0 group-hover:opacity-80 drop-shadow transition" />
                    </div>
                  </div>
                )}

                <div className="text-slate-700 whitespace-pre-wrap break-words text-xs">
                  {msg.content}
                </div>
              </div>
            ))}
          </div>

          {/* 右：逐条评分 */}
          <ScoringPanel sessionId={detail.id} diagramType={detail.diagram_type} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4">
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <MessageSquare size={20} /> 聊天记录
        </h1>
        <button
          onClick={() => exportMut.mutate()}
          disabled={exportMut.isPending}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60"
        >
          {exportMut.isPending ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
          按当前筛选导出 UML 作品与评分
        </button>
      </div>

      {/* 筛选 */}
      <div className="flex flex-wrap gap-3 mb-4 items-center">
        <select
          value={filterClassId ?? ""}
          onChange={(e) => setFilterClassId(e.target.value ? Number(e.target.value) : undefined)}
          className="px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 outline-none"
        >
          <option value="">全部班级</option>
          {(classesQ.data || []).map((c) => (
            <option key={c.id} value={c.id}>{c.code} {c.name}</option>
          ))}
        </select>
        <select
          value={filterGroup}
          onChange={(e) => setFilterGroup(e.target.value)}
          className="px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 outline-none"
        >
          <option value="">全部分组</option>
          <option value="agent_a">Agent A</option>
          <option value="agent_b">Agent B</option>
          <option value="agent_c">Agent C</option>
          <option value="control">对照组</option>
          <option value="multi_model_a">四模型A</option>
        </select>
        <select
          value={filterSessionGroup}
          onChange={(e) => setFilterSessionGroup(e.target.value)}
          className="px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 outline-none"
        >
          <option value="">全部本次分组</option>
          <option value="agent_a">Agent A</option>
          <option value="agent_b">Agent B</option>
          <option value="agent_c">Agent C</option>
          <option value="control">对照组</option>
          <option value="multi_model_a">四模型A</option>
        </select>
        <select
          value={filterDiagramType}
          onChange={(e) => setFilterDiagramType(e.target.value)}
          className="px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 outline-none"
        >
          <option value="">全部图类型</option>
          <option value="use_case">用例图</option>
          <option value="class">类图</option>
          <option value="sequence">时序图</option>
          <option value="swimlane">泳道图</option>
        </select>
        {filterUserId && (
          <span className="text-sm text-slate-500">
            筛选用户 ID: {filterUserId}
          </span>
        )}
        <span className="text-sm text-slate-400">
          共 {sessions.length} 个会话
        </span>
      </div>

      {/* 会话列表 */}
      <div className="bg-white rounded-lg border border-slate-200 overflow-y-auto max-h-[calc(100vh-10rem)]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="text-xs text-slate-500 bg-slate-50 border-b">
              <th className="text-left px-4 py-3 font-medium">学生</th>
              <th className="text-left px-4 py-3 font-medium">分组</th>
              <th className="text-left px-4 py-3 font-medium">图类型</th>
              <th className="text-center px-4 py-3 font-medium">轮次</th>
              <th className="text-center px-4 py-3 font-medium">AI评分</th>
              <th className="text-center px-4 py-3 font-medium">教师评阅</th>
              <th className="text-center px-4 py-3 font-medium">状态</th>
              <th className="text-center px-4 py-3 font-medium">时间</th>
              <th className="text-center px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {sessions.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-slate-400">
                  暂无聊天记录
                </td>
              </tr>
            ) : (
              sessions.map((s) => (
                <tr
                  key={s.id}
                  className="border-b border-slate-50 hover:bg-slate-50"
                >
                  <td className="px-4 py-3">
                    <div className="text-slate-700 font-medium">
                      {s.display_name}
                    </div>
                    <div className="text-xs text-slate-400">{s.username}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        "px-2 py-0.5 rounded-full text-xs font-medium",
                        GROUP_COLORS[s.experiment_group] ||
                        "bg-slate-100 text-slate-600"
                      )}
                    >
                      {GROUP_LABELS[s.experiment_group] ||
                        s.experiment_group ||
                        "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {DIAGRAM_LABELS[s.diagram_type] || s.diagram_type}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600">
                    {s.round_number}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {s.latest_score != null ? (
                      <span
                        className={clsx(
                          "font-medium",
                          s.latest_score >= 80
                            ? "text-green-600"
                            : s.latest_score >= 60
                              ? "text-amber-600"
                              : "text-red-600"
                        )}
                      >
                        {s.latest_score}
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {s.teacher_scored_count > 0 ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                        已评 {s.teacher_scored_count} 条
                      </span>
                    ) : (
                      <span className="text-xs text-slate-300">未评阅</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {s.passed ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">
                        通过
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                        {s.status}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center text-xs text-slate-400">
                    {formatTime(s.updated_at)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => setSelectedSessionId(s.id)}
                      className="text-xs text-brand-600 hover:underline"
                    >
                      查看评阅
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
