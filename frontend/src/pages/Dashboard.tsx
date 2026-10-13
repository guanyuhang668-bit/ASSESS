import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listClasses, listModels, listSubmissions } from "@/lib/api";
import type { GradingStatusItem } from "@/lib/api";
import { FileText, Search, ChevronLeft, ChevronRight } from "lucide-react";

const DIAGRAM_TYPES = [
  { value: "", label: "全部类型" },
  { value: "use_case", label: "用例图" },
  { value: "class", label: "类图" },
  { value: "sequence", label: "时序图" },
  { value: "swimlane", label: "泳道图" },
];

const DIAGRAM_CN: Record<string, string> = {
  use_case: "用例图", class: "类图", sequence: "时序图", swimlane: "泳道图",
};

function StatusBadge({ status, score }: { status: string; score: number }) {
  if (status === "success")
    return <span className="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 font-medium">{score.toFixed(1)}</span>;
  if (status === "running")
    return <span className="px-1.5 py-0.5 rounded text-xs bg-blue-100 text-blue-700 animate-pulse">批改中</span>;
  if (status === "failed")
    return <span className="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700">失败</span>;
  return <span className="px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-500">等待中</span>;
}

function GradingSummary({ items }: { items: GradingStatusItem[] }) {
  if (!items || items.length === 0) return <span className="text-xs text-slate-400">未批改</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((g) => (
        <div key={g.model_key} className="flex items-center gap-1" title={g.model_key}>
          <span className="text-xs text-slate-500">{g.model_key}:</span>
          <StatusBadge status={g.status} score={g.score} />
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const [diagramType, setDiagramType] = useState("");
  const [classId, setClassId] = useState<number | undefined>();
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const classes = useQuery({ queryKey: ["classes"], queryFn: listClasses });
  const models = useQuery({ queryKey: ["models"], queryFn: listModels });
  const subs = useQuery({
    queryKey: ["subs", diagramType, classId, page],
    queryFn: () => listSubmissions({
      diagram_type: diagramType || undefined,
      class_id: classId,
      page,
      page_size: pageSize,
    }),
    refetchInterval: 5000,
  });

  const totalPages = subs.data ? Math.ceil(subs.data.meta.total / pageSize) : 0;

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4">学生作品列表</h1>

      {/* 筛选条 */}
      <div className="bg-white rounded-lg border border-slate-200 p-3 mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Search size={14} className="text-slate-400" />
          <select
            value={diagramType}
            onChange={(e) => { setDiagramType(e.target.value); setPage(1); }}
            className="px-2 py-1.5 rounded border border-slate-300 text-sm"
          >
            {DIAGRAM_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <select
          value={classId ?? ""}
          onChange={(e) => { setClassId(e.target.value ? Number(e.target.value) : undefined); setPage(1); }}
          className="px-2 py-1.5 rounded border border-slate-300 text-sm"
        >
          <option value="">全部班级</option>
          {classes.data?.map((c) => (
            <option key={c.id} value={c.id}>{c.code} {c.name}</option>
          ))}
        </select>
        <div className="ml-auto text-xs text-slate-500">
          共 {subs.data?.meta.total ?? 0} 份作品 · {models.data?.length ?? 0} 个模型
        </div>
      </div>

      {/* 列表 */}
      <div className="bg-white rounded-lg border border-slate-200 overflow-y-auto max-h-[calc(100vh-10rem)]">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 bg-slate-50 sticky top-0 z-10">
            <tr>
              <th className="text-left px-4 py-2">学号</th>
              <th className="text-left px-4 py-2">姓名</th>
              <th className="text-left px-4 py-2">图类型</th>
              <th className="text-left px-4 py-2">题目</th>
              <th className="text-right px-4 py-2">元素/关系</th>
              <th className="text-left px-4 py-2">批改结果</th>
              <th className="text-left px-4 py-2">提交时间</th>
              <th className="text-left px-4 py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {subs.data?.items.map((s) => (
              <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-2 font-mono text-xs">{s.student_code || `#${s.student_id}`}</td>
                <td className="px-4 py-2">{s.student_name || "—"}</td>
                <td className="px-4 py-2">
                  <span className="px-1.5 py-0.5 bg-slate-100 rounded text-xs">
                    {DIAGRAM_CN[s.diagram_type] || s.diagram_type}
                  </span>
                </td>
                <td className="px-4 py-2 truncate max-w-[120px]">{s.problem_code || "—"}</td>
                <td className="px-4 py-2 text-right text-xs text-slate-500">
                  {s.parse_error
                    ? <span className="text-red-500" title={s.parse_error}>解析错误</span>
                    : `${s.element_count}e / ${s.relation_count}r`}
                </td>
                <td className="px-4 py-2">
                  <GradingSummary items={s.grading_status} />
                </td>
                <td className="px-4 py-2 text-xs text-slate-400">
                  {s.created_at?.slice(0, 16).replace("T", " ")}
                </td>
                <td className="px-4 py-2 space-x-2">
                  <Link to={`/compare/${s.id}`} className="text-brand-600 hover:underline text-xs">对比</Link>
                  <Link to={`/teacher/${s.id}`} className="text-slate-600 hover:underline text-xs">打分</Link>
                </td>
              </tr>
            ))}
            {(!subs.data?.items.length) && (
              <tr><td colSpan={8} className="text-center py-12 text-slate-400">
                <FileText size={24} className="mx-auto mb-2 opacity-40" />
                暂无数据，等待学生提交作品
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-4 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="px-2 py-1 rounded border border-slate-300 disabled:opacity-40 hover:bg-slate-100"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="text-slate-600">{page} / {totalPages}</span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            className="px-2 py-1 rounded border border-slate-300 disabled:opacity-40 hover:bg-slate-100"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
