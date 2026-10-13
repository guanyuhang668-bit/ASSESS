import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  getSubmission, resultsBySubmission, listTeacherScores,
} from "@/lib/api";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, Legend,
} from "recharts";

export default function ResultCompare() {
  const { submissionId } = useParams();
  const sid = Number(submissionId);

  const sub = useQuery({ queryKey: ["sub", sid], queryFn: () => getSubmission(sid) });
  const results = useQuery({
    queryKey: ["results-by-sub", sid],
    queryFn: () => resultsBySubmission(sid),
  });
  const tscores = useQuery({
    queryKey: ["teacher-scores", sid],
    queryFn: () => listTeacherScores(sid),
  });

  const [expandedModel, setExpandedModel] = useState<string | null>(null);

  // 聚合指标分数（按 code 汇总 agent 各模型 + 教师）
  const codes = Array.from(
    new Set(
      (results.data || []).flatMap((r) => r.criterion_scores.map((cs) => cs.code)),
    ),
  ).sort();

  const radarData = codes.map((code) => {
    const row: Record<string, number | string> = { code };
    (results.data || []).forEach((r) => {
      const cs = r.criterion_scores.find((c) => c.code === code);
      row[r.model_key] = cs ? (cs.score / (cs.max_score || 1)) * 100 : 0;
    });
    const ts = (tscores.data || []).find((t) => t.code === code);
    if (ts) row["教师"] = (ts.score / (ts.max_score || 1)) * 100;
    return row;
  });

  const modelColors = ["#4f46e5", "#059669", "#dc2626", "#d97706", "#0284c7"];

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-semibold text-slate-800">结果对比</h1>
        <span className="text-sm text-slate-500">#{sid}</span>
        {sub.data && (
          <span className="text-sm text-slate-500">
            · {sub.data.diagram_type} · {sub.data.original_filename}
          </span>
        )}
        <Link to={`/teacher/${sid}`} className="ml-auto text-sm text-brand-600 hover:underline">
          进入教师标注 →
        </Link>
      </div>

      {/* 雷达图 */}
      <div className="bg-white rounded-lg border border-slate-200 p-4 mb-4">
        <div className="text-sm font-medium mb-2">各指标得分雷达</div>
        {codes.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-400">暂无评分结果</div>
        ) : (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="code" />
                <PolarRadiusAxis domain={[0, 100]} />
                <Tooltip />
                <Legend />
                {(results.data || []).map((r, i) => (
                  <Radar
                    key={r.model_key}
                    name={r.model_key}
                    dataKey={r.model_key}
                    stroke={modelColors[i % modelColors.length]}
                    fill={modelColors[i % modelColors.length]}
                    fillOpacity={0.15}
                  />
                ))}
                {tscores.data && tscores.data.length > 0 && (
                  <Radar name="教师" dataKey="教师" stroke="#0f172a" fill="#0f172a" fillOpacity={0.2} />
                )}
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* 总分 & 简评 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-4">
        {(results.data || []).map((r) => (
          <div key={r.id} className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold">{r.model_key}</div>
              <div className="ml-auto text-2xl font-bold text-brand-600">
                {r.normalized_score.toFixed(1)}
              </div>
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {r.prompt_tokens + r.completion_tokens} tokens · {r.elapsed_seconds.toFixed(1)}s · {r.status}
            </div>
            <div className="mt-2 text-sm text-slate-700 whitespace-pre-wrap line-clamp-4">
              {r.overall_comment || <span className="text-slate-400">无评语</span>}
            </div>
            <button
              onClick={() => setExpandedModel(expandedModel === r.model_key ? null : r.model_key)}
              className="mt-2 text-xs text-brand-600 hover:underline"
            >
              {expandedModel === r.model_key ? "收起" : "展开全部指标 ▸"}
            </button>
          </div>
        ))}
      </div>

      {/* 展开的指标详情 */}
      {expandedModel && (
        <div className="bg-white rounded-lg border border-slate-200">
          <div className="px-4 py-3 border-b text-sm font-medium">
            {expandedModel} 各指标详情
          </div>
          <div className="p-4 space-y-2 text-sm max-h-[600px] overflow-auto">
            {(results.data || [])
              .find((r) => r.model_key === expandedModel)
              ?.criterion_scores.map((cs) => (
                <div key={cs.id} className="border border-slate-100 rounded p-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-brand-600">{cs.code}</span>
                    <span className="font-medium">
                      {cs.score.toFixed(2)} / {cs.max_score.toFixed(2)}
                    </span>
                    {cs.not_applicable && (
                      <span className="text-xs text-slate-400">(不适用)</span>
                    )}
                  </div>
                  {cs.reasoning && (
                    <div className="text-xs text-slate-500 mt-1">{cs.reasoning}</div>
                  )}
                  {cs.issues.length > 0 && (
                    <ul className="mt-1 space-y-1">
                      {cs.issues.map((i) => (
                        <li key={i.id} className="text-xs text-red-700 bg-red-50 rounded px-2 py-1">
                          <span className="font-mono text-[10px] text-red-500">
                            [{i.severity}]
                          </span>{" "}
                          {i.description}
                          {i.element_refs.length > 0 && (
                            <span className="font-mono text-[10px] text-slate-400 ml-1">
                              ({i.element_refs.join(", ")})
                            </span>
                          )}
                          {i.suggestion && (
                            <div className="text-slate-500 mt-0.5">↳ {i.suggestion}</div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}

      {/* IR 文本（折叠） */}
      <details className="mt-4 bg-white rounded-lg border border-slate-200 p-4">
        <summary className="text-sm font-medium cursor-pointer">IR 文本（LLM 看到的输入）</summary>
        <pre className="text-xs bg-slate-50 p-3 rounded mt-2 overflow-auto max-h-80 font-mono">
          {sub.data?.ir_textual || "(尚未解析)"}
        </pre>
      </details>
    </div>
  );
}
