import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listMySubmissions, type MySubmission } from "@/lib/api";
import {
  History,
  FileText,
  Image as ImageIcon,
  Trophy,
  AlertCircle,
  X,
  ZoomIn,
  Star,
  MessageSquare,
} from "lucide-react";
import { clsx } from "clsx";

const DIAGRAM_LABELS: Record<string, string> = {
  use_case: "用例图",
  class: "类图",
  sequence: "时序图",
  swimlane: "泳道图",
};

function formatTime(iso: string) {
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function StudentHistory() {
  const subsQ = useQuery({
    queryKey: ["my-submissions"],
    queryFn: listMySubmissions,
  });

  const [selectedSub, setSelectedSub] = useState<MySubmission | null>(null);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  const submissions = subsQ.data || [];

  if (selectedSub) {
    const imgUrl = selectedSub.image_filename
      ? `/api/files/${selectedSub.image_filename}`
      : null;
    return (
      <div>
        {/* 灯箱 */}
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
          onClick={() => setSelectedSub(null)}
          className="flex items-center gap-1 text-sm text-brand-600 hover:underline mb-4"
        >
          ← 返回列表
        </button>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 左：UML 图 */}
          <div className="bg-white rounded-xl border border-slate-200 p-4 sticky top-4 self-start">
            <p className="text-sm font-medium text-slate-600 mb-2 flex items-center gap-2">
              <ImageIcon size={14} className="text-slate-400" /> 我的 UML 图
            </p>
            {imgUrl ? (
              <div className="relative group">
                <img
                  src={imgUrl}
                  alt="UML 图"
                  className="w-full rounded-lg border border-slate-100 cursor-pointer hover:opacity-90 transition"
                  onClick={() => setLightboxUrl(imgUrl)}
                />
                <div
                  className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/10 transition rounded-lg cursor-pointer"
                  onClick={() => setLightboxUrl(imgUrl)}
                >
                  <ZoomIn size={32} className="text-white opacity-0 group-hover:opacity-80 drop-shadow transition" />
                </div>
              </div>
            ) : (
              <div className="py-12 text-center text-sm text-slate-400">暂无图片</div>
            )}
          </div>

          {/* 右：提交信息 + 评分详情（可滚动） */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden max-h-[calc(100vh-6rem)] overflow-y-auto">
            {/* 基本信息 */}
            <div className="p-5 border-b border-slate-100">
              <h2 className="text-lg font-semibold text-slate-800 mb-3">提交详情</h2>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-xs text-slate-400">图类型</span>
                  <p className="font-medium text-slate-700">
                    {DIAGRAM_LABELS[selectedSub.diagram_type] || selectedSub.diagram_type}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-slate-400">题目编号</span>
                  <p className="font-medium text-slate-700">{selectedSub.problem_code}</p>
                </div>
                <div>
                  <span className="text-xs text-slate-400">文件名</span>
                  <p className="font-medium text-slate-700 truncate">{selectedSub.original_filename}</p>
                </div>
                <div>
                  <span className="text-xs text-slate-400">元素 / 关系</span>
                  <p className="font-medium text-slate-700">
                    {selectedSub.element_count} / {selectedSub.relation_count}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-slate-400">提交时间</span>
                  <p className="font-medium text-slate-700">{new Date(selectedSub.created_at).toLocaleString("zh-CN")}</p>
                </div>
                <div>
                  <span className="text-xs text-slate-400">AI 评分</span>
                  <p className={clsx("font-bold text-lg", selectedSub.best_score != null
                    ? selectedSub.best_score >= 80 ? "text-green-600" : selectedSub.best_score >= 60 ? "text-amber-600" : "text-red-600"
                    : "text-slate-400"
                  )}>
                    {selectedSub.best_score != null ? selectedSub.best_score.toFixed(1) : "—"}
                  </p>
                </div>
              </div>

              {selectedSub.parse_error && (
                <div className="mt-3 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                  <AlertCircle size={16} className="mt-0.5 shrink-0" />
                  <span>解析错误: {selectedSub.parse_error}</span>
                </div>
              )}
            </div>

            {/* 题目描述 */}
            {selectedSub.problem_statement && (
              <div className="px-5 py-3 border-b border-slate-100">
                <span className="text-xs text-slate-400">题目描述</span>
                <p className="text-sm text-slate-600 mt-1">{selectedSub.problem_statement}</p>
              </div>
            )}

            {/* AI 评分反馈 */}
            {selectedSub.grading_feedback && (
              <>
                {/* 总评 */}
                {selectedSub.grading_feedback.overall_comment && (
                  <div className="px-5 py-3 border-b border-slate-100 flex items-start gap-2.5">
                    <MessageSquare size={15} className="text-slate-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-xs font-medium text-slate-500 mb-1">总评</p>
                      <p className="text-sm text-slate-700 leading-relaxed">
                        {selectedSub.grading_feedback.overall_comment}
                      </p>
                    </div>
                  </div>
                )}

                {/* 分项评分 */}
                {selectedSub.grading_feedback.criteria.length > 0 && (
                  <div className="px-5 py-3">
                    <p className="text-xs font-medium text-slate-500 mb-3 flex items-center gap-1.5">
                      <Star size={13} className="text-amber-500" /> 分项评分
                    </p>
                    <div className="space-y-3">
                      {selectedSub.grading_feedback.criteria.map((c) => {
                        const pct = c.max_score > 0 ? (c.score / c.max_score) * 100 : 0;
                        const barColor = pct >= 80 ? "bg-green-400" : pct >= 60 ? "bg-amber-400" : pct >= 40 ? "bg-orange-400" : "bg-red-400";
                        return (
                          <div key={c.code} className="bg-slate-50 rounded-lg p-3">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-mono font-medium text-brand-600">{c.code}</span>
                              <span className={clsx("text-xs font-medium",
                                pct >= 80 ? "text-green-600" : pct >= 60 ? "text-amber-600" : "text-red-600"
                              )}>
                                {c.score.toFixed(1)} / {c.max_score.toFixed(1)}
                              </span>
                            </div>
                            <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden mb-1.5">
                              <div
                                className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                                style={{ width: `${Math.min(pct, 100)}%` }}
                              />
                            </div>
                            {c.reasoning && (
                              <p className="text-xs text-slate-500 leading-relaxed">{c.reasoning}</p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}

          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4 flex items-center gap-2">
        <History size={20} /> 提交历史
      </h1>
      <p className="text-sm text-slate-500 mb-4">
        共 {submissions.length} 份提交
      </p>

      <div className="bg-white rounded-lg border border-slate-200 overflow-y-auto max-h-[calc(100vh-10rem)]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="text-xs text-slate-500 bg-slate-50 border-b">
              <th className="text-left px-4 py-3 font-medium">图类型</th>
              <th className="text-left px-4 py-3 font-medium">题目编号</th>
              <th className="text-left px-4 py-3 font-medium">文件名</th>
              <th className="text-center px-4 py-3 font-medium">元素/关系</th>
              <th className="text-center px-4 py-3 font-medium">AI 评分</th>
              <th className="text-center px-4 py-3 font-medium">提交时间</th>
              <th className="text-center px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {submissions.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                  暂无提交记录
                </td>
              </tr>
            ) : (
              submissions.map((s) => (
                <tr key={s.id} className="border-b border-slate-50 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
                      {DIAGRAM_LABELS[s.diagram_type] || s.diagram_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-700">{s.problem_code}</td>
                  <td className="px-4 py-3 text-slate-600 truncate max-w-[200px]">
                    <span className="flex items-center gap-1">
                      <FileText size={12} className="text-slate-400 shrink-0" />
                      {s.original_filename}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-slate-500">
                    {s.element_count} / {s.relation_count}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {s.parse_error ? (
                      <span className="text-xs text-red-500">解析错误</span>
                    ) : s.best_score != null ? (
                      <span className={clsx("font-medium",
                        s.best_score >= 80 ? "text-green-600" :
                        s.best_score >= 60 ? "text-amber-600" : "text-red-600"
                      )}>
                        <Trophy size={12} className="inline mr-1" />
                        {s.best_score.toFixed(1)}
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center text-xs text-slate-400">
                    {formatTime(s.created_at)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => setSelectedSub(s)}
                      className="text-xs text-brand-600 hover:underline"
                    >
                      查看详情
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
