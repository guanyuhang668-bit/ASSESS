import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { runSummary } from "@/lib/api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid,
} from "recharts";

function fmt(n: number | null, digits = 2) {
  return n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(digits);
}

export default function Analysis() {
  const { runId } = useParams();
  const id = Number(runId);
  const q = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => runSummary(id),
    enabled: !!id,
  });

  if (q.isLoading) return <div>加载中…</div>;
  if (q.isError) return <div className="text-red-600">加载失败</div>;

  const summary = q.data!;

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-semibold text-slate-800">一致性分析</h1>
        <span className="text-sm text-slate-500">Run #{summary.run_id}</span>
        <span className="text-sm text-slate-500">
          · 已标注作品数：{summary.n_teacher_labelled}
        </span>
      </div>

      {summary.n_teacher_labelled === 0 && (
        <div className="p-4 bg-amber-50 text-amber-800 text-sm rounded mb-4">
          尚无教师评分数据。请先在"教师标注"页为至少一份作品打分，才能计算 MAE / F1 等指标。
        </div>
      )}

      <div className="bg-white rounded-lg border border-slate-200 p-4 mb-4">
        <div className="text-sm font-medium mb-3">模型 vs 教师</div>
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500">
            <tr className="border-b border-slate-200">
              <th className="text-left px-3 py-2">模型</th>
              <th className="text-right px-3 py-2">已评</th>
              <th className="text-right px-3 py-2">MAE (%)</th>
              <th className="text-right px-3 py-2">Spearman ρ</th>
              <th className="text-right px-3 py-2">Precision</th>
              <th className="text-right px-3 py-2">Recall</th>
              <th className="text-right px-3 py-2">F1</th>
              <th className="text-right px-3 py-2">avg Tokens</th>
              <th className="text-right px-3 py-2">avg s</th>
            </tr>
          </thead>
          <tbody>
            {summary.rows.map((r) => (
              <tr key={r.model_key} className="border-b border-slate-100">
                <td className="px-3 py-2 font-mono">{r.model_key}</td>
                <td className="px-3 py-2 text-right">{r.submissions_graded}</td>
                <td className="px-3 py-2 text-right">{fmt(r.mae_vs_teacher, 1)}</td>
                <td className="px-3 py-2 text-right">{fmt(r.rho_vs_teacher, 3)}</td>
                <td className="px-3 py-2 text-right">{fmt(r.precision, 3)}</td>
                <td className="px-3 py-2 text-right">{fmt(r.recall, 3)}</td>
                <td className="px-3 py-2 text-right font-semibold">{fmt(r.f1, 3)}</td>
                <td className="px-3 py-2 text-right text-slate-500">{Math.round(r.avg_tokens)}</td>
                <td className="px-3 py-2 text-right text-slate-500">{r.avg_seconds.toFixed(1)}</td>
              </tr>
            ))}
            {!summary.rows.length && (
              <tr><td colSpan={9} className="p-6 text-center text-slate-400 text-xs">暂无数据</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {summary.rows.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="text-sm font-medium mb-3">F1 对比</div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary.rows}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="model_key" />
                  <YAxis domain={[0, 1]} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="precision" fill="#6366f1" name="Precision" />
                  <Bar dataKey="recall" fill="#10b981" name="Recall" />
                  <Bar dataKey="f1" fill="#f59e0b" name="F1" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <div className="text-sm font-medium mb-3">MAE（% 差距，越低越接近教师）</div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary.rows}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="model_key" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="mae_vs_teacher" fill="#dc2626" name="MAE (%)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
