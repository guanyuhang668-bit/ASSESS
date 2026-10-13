import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import {
  getSubmission, listRubricVersions, getRubricDetail,
  listTeacherScores, upsertTeacherScore, resultsBySubmission,
  TeacherScoreIn,
} from "@/lib/api";
import { Save, CheckCircle2, X, ZoomIn } from "lucide-react";

interface RowState {
  score: number;
  max_score: number;
  not_applicable: boolean;
  comment: string;
  issues: { element_refs: string[]; description: string; severity: string }[];
  dirty: boolean;
  saved?: boolean;
}

export default function TeacherLabel() {
  const qc = useQueryClient();
  const { submissionId } = useParams();
  const sid = Number(submissionId);

  const sub = useQuery({ queryKey: ["sub", sid], queryFn: () => getSubmission(sid) });
  const versions = useQuery({
    queryKey: ["rubric-versions", sub.data?.diagram_type],
    queryFn: () => listRubricVersions(sub.data!.diagram_type),
    enabled: !!sub.data,
  });
  const activeRubric = versions.data?.find((v) => v.is_active);
  const rubric = useQuery({
    queryKey: ["rubric-detail", activeRubric?.id],
    queryFn: () => (activeRubric ? getRubricDetail(activeRubric.id) : Promise.resolve(null)),
    enabled: !!activeRubric,
  });
  const teacher = useQuery({
    queryKey: ["teacher-scores", sid],
    queryFn: () => listTeacherScores(sid),
    enabled: !!sid,
  });
  const agentResults = useQuery({
    queryKey: ["results-by-sub", sid],
    queryFn: () => resultsBySubmission(sid),
    enabled: !!sid,
  });

  const [rows, setRows] = useState<Record<string, RowState>>({});
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  // 初始化：用已有教师分 + 默认 1.0 填充
  useEffect(() => {
    if (!rubric.data) return;
    const next: Record<string, RowState> = {};
    rubric.data.criteria.forEach((c) => {
      const existing = teacher.data?.find((t) => t.code === c.code);
      if (existing) {
        next[c.code] = {
          score: existing.score,
          max_score: existing.max_score,
          not_applicable: existing.not_applicable,
          comment: existing.comment,
          issues: (existing.issues as any[] || []).map((i) => ({
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
  }, [rubric.data, teacher.data]);

  const saveMut = useMutation({
    mutationFn: (body: TeacherScoreIn) => upsertTeacherScore(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["teacher-scores", sid] }),
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
      submission_id: sid, code,
      score: row.score, max_score: row.max_score,
      not_applicable: row.not_applicable, comment: row.comment,
      issues: row.issues,
    });
    setRows((p) => ({ ...p, [code]: { ...p[code], dirty: false, saved: true } }));
  }

  async function saveAll() {
    for (const [code, row] of Object.entries(rows)) {
      if (row.dirty) {
        await saveOne(code);
      }
    }
  }

  const agentIssuesByCode = new Map<string, { model_key: string; desc: string; refs: string[] }[]>();
  (agentResults.data || []).forEach((r) => {
    r.criterion_scores.forEach((cs) => {
      if (!agentIssuesByCode.has(cs.code)) agentIssuesByCode.set(cs.code, []);
      cs.issues.forEach((i) =>
        agentIssuesByCode.get(cs.code)!.push({
          model_key: r.model_key, desc: i.description, refs: i.element_refs,
        }),
      );
    });
  });

  if (!sub.data) return <div>加载中…</div>;
  if (!activeRubric) {
    return (
      <div className="p-4 bg-amber-50 text-amber-800 text-sm rounded">
        该图类型（{sub.data.diagram_type}）尚无激活的评分标准，请先在「评分标准」页导入并激活。
      </div>
    );
  }

  const dirtyCount = Object.values(rows).filter((r) => r.dirty).length;

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
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-semibold text-slate-800">教师标注</h1>
        <span className="text-sm text-slate-500">
          #{sid} · {sub.data.diagram_type} · {sub.data.original_filename}
        </span>
        <button
          onClick={saveAll}
          disabled={dirtyCount === 0 || saveMut.isPending}
          className="ml-auto px-3 py-1.5 bg-brand-600 text-white rounded text-sm hover:bg-brand-700 disabled:opacity-60 flex items-center gap-1"
        >
          <Save size={14} /> 保存全部 ({dirtyCount})
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左：学生 UML 图片 */}
        <div className="bg-white rounded-lg border border-slate-200 p-4 sticky top-4 self-start max-h-[calc(100vh-6rem)] overflow-auto">
          <div className="text-sm font-medium mb-2">学生 UML 图</div>
          {sub.data.image_filename ? (
            <div className="relative group">
              <img
                src={`/api/files/${sub.data.image_filename}`}
                alt="学生 UML 图"
                className="w-full rounded border border-slate-100 cursor-pointer hover:opacity-90 transition"
                onClick={() => setLightboxUrl(`/api/files/${sub.data!.image_filename}`)}
              />
              <div
                className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/10 transition rounded cursor-pointer"
                onClick={() => setLightboxUrl(`/api/files/${sub.data!.image_filename}`)}
              >
                <ZoomIn size={32} className="text-white opacity-0 group-hover:opacity-80 drop-shadow transition" />
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-400 py-8 text-center">暂无图片</div>
          )}
        </div>

        {/* 右：指标打分 */}
        <div className="space-y-2 max-h-[calc(100vh-6rem)] overflow-y-auto pr-1">
          {rubric.data?.criteria.map((c) => {
            const row = rows[c.code];
            if (!row) return null;
            const agentIssues = agentIssuesByCode.get(c.code) || [];
            return (
              <div key={c.code} className={`bg-white border rounded p-3 ${
                row.saved ? "border-green-200" : row.dirty ? "border-amber-300" : "border-slate-200"
              }`}>
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-mono text-xs text-brand-600 shrink-0">{c.code}</span>
                  <span className="font-medium flex-1">{c.name}</span>
                  {row.saved && <CheckCircle2 size={14} className="text-green-600" />}
                  {row.dirty && <span className="text-xs text-amber-600">未保存</span>}
                </div>
                {c.description && (
                  <div className="text-xs text-slate-500 mt-1">{c.description}</div>
                )}

                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="number" step="0.05" min={0} max={row.max_score}
                    value={row.score}
                    onChange={(e) => update(c.code, { score: Math.max(0, Math.min(row.max_score, Number(e.target.value) || 0)) })}
                    className="w-20 px-2 py-1 border border-slate-300 rounded text-sm"
                  />
                  <span className="text-xs text-slate-500">/ {row.max_score}</span>
                  <label className="text-xs text-slate-500 flex items-center gap-1 ml-2">
                    <input
                      type="checkbox" checked={row.not_applicable}
                      onChange={(e) => update(c.code, { not_applicable: e.target.checked })}
                    />
                    不适用
                  </label>
                  <button onClick={() => saveOne(c.code)}
                    className="ml-auto text-xs text-brand-600 hover:underline disabled:opacity-40"
                    disabled={!row.dirty}>
                    保存
                  </button>
                </div>

                <textarea
                  value={row.comment}
                  onChange={(e) => update(c.code, { comment: e.target.value })}
                  placeholder="评语（可选）"
                  className="w-full mt-2 px-2 py-1 border border-slate-200 rounded text-xs"
                  rows={2}
                />

                {/* Agent 提供的候选缺陷，一键采纳 */}
                {agentIssues.length > 0 && (
                  <div className="mt-2">
                    <div className="text-xs text-slate-400 mb-1">Agent 提出的缺陷（点击采纳）</div>
                    <ul className="space-y-1">
                      {agentIssues.map((ai, i) => (
                        <li key={i}
                          onClick={() => update(c.code, {
                            issues: [...row.issues, {
                              element_refs: ai.refs, description: ai.desc, severity: "minor",
                            }],
                          })}
                          className="text-xs bg-slate-50 px-2 py-1 rounded cursor-pointer hover:bg-brand-50">
                          {ai.desc}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 已采纳的教师缺陷 */}
                {row.issues.length > 0 && (
                  <div className="mt-2">
                    <div className="text-xs text-slate-600 mb-1">已记录的缺陷</div>
                    <ul className="space-y-1">
                      {row.issues.map((i, idx) => (
                        <li key={idx} className="text-xs bg-red-50 text-red-700 px-2 py-1 rounded flex items-start gap-2">
                          <span className="flex-1">
                            {i.description}
                          </span>
                          <button onClick={() => update(c.code, {
                            issues: row.issues.filter((_, j) => j !== idx),
                          })} className="text-red-500">✕</button>
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
    </div>
  );
}
