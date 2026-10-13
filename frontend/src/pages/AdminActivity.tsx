import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  downloadAdminActivityXlsx,
  getAdminActivity,
  getAdminUserActivity,
  listClasses,
  type AdminActivityItem,
} from "@/lib/api";
import {
  BarChart3,
  Clock,
  Download,
  Eye,
  Loader2,
  MessageSquare,
  Search,
  Users,
} from "lucide-react";
import { clsx } from "clsx";

const UNASSIGNED_CLASS = "__unassigned__";

const GROUP_LABELS: Record<string, string> = {
  agent_a: "Agent A",
  agent_b: "Agent B",
  agent_c: "Agent C",
  control: "对照组",
  multi_model_a: "四模型A",
};

const DIAGRAM_LABELS: Record<string, string> = {
  use_case: "用例图",
  class: "类图",
  sequence: "时序图",
  swimlane: "泳道图",
};

function seconds(value: number | null | undefined) {
  return Math.max(0, Math.floor(value || 0));
}

function formatDuration(value: number | null | undefined) {
  const total = seconds(value);
  if (total === 0) return "0分钟";

  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);

  if (days > 0) return `${days}天 ${hours}小时`;
  if (hours > 0) return `${hours}小时${minutes}分`;
  return `${Math.max(1, minutes)}分钟`;
}

function formatHours(value: number | null | undefined) {
  return `${(seconds(value) / 3600).toFixed(2)} h`;
}

function groupLabel(group: string | null | undefined) {
  if (!group) return "未分配";
  return GROUP_LABELS[group] || group;
}

export default function AdminActivity() {
  const [selectedClass, setSelectedClass] = useState("");
  const [search, setSearch] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  const classesQ = useQuery({
    queryKey: ["classes"],
    queryFn: listClasses,
  });

  useEffect(() => {
    if (selectedClass || !classesQ.data || classesQ.data.length === 0) return;
    setSelectedClass(classesQ.data[0].code);
  }, [classesQ.data, selectedClass]);

  useEffect(() => {
    setSelectedUserId(null);
  }, [selectedClass, search]);

  const activityQ = useQuery({
    queryKey: ["admin-activity", selectedClass, search],
    queryFn: () =>
      getAdminActivity({
        class_code: selectedClass || undefined,
        search: search.trim() || undefined,
      }),
    enabled: !!selectedClass,
  });

  const detailQ = useQuery({
    queryKey: ["admin-activity-detail", selectedUserId],
    queryFn: () => getAdminUserActivity(selectedUserId as number),
    enabled: selectedUserId != null,
  });

  const rows = activityQ.data || [];

  const classLabel = useMemo(() => {
    if (selectedClass === UNASSIGNED_CLASS) return "未分班";
    const cls = (classesQ.data || []).find((c) => c.code === selectedClass);
    return cls ? cls.name || cls.code : "请选择班级";
  }, [classesQ.data, selectedClass]);

  const totals = useMemo(() => {
    const totalSeconds = rows.reduce((sum, row) => sum + seconds(row.total_seconds), 0);
    const activeStudents = rows.filter((row) => seconds(row.total_seconds) > 0).length;
    const avgSeconds = rows.length > 0 ? Math.round(totalSeconds / rows.length) : 0;
    return { totalSeconds, activeStudents, avgSeconds };
  }, [rows]);

  const selectedSummary = useMemo(
    () => rows.find((item) => item.user_id === selectedUserId) || null,
    [rows, selectedUserId],
  );

  const selectedDetail = detailQ.data || selectedSummary;

  async function handleExport() {
    if (!selectedClass) return;
    setExporting(true);
    try {
      await downloadAdminActivityXlsx({
        class_code: selectedClass,
        search: search.trim() || undefined,
      });
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4 flex items-center gap-2">
        <Clock size={20} /> 使用时长
      </h1>

      <div className="bg-white rounded-lg border border-slate-200 p-4 mb-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-slate-500 mb-1">班级</label>
            <select
              value={selectedClass}
              onChange={(e) => setSelectedClass(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm min-w-[180px] focus:ring-2 focus:ring-brand-500 outline-none"
            >
              <option value="" disabled>
                请选择班级
              </option>
              {(classesQ.data || []).map((c) => (
                <option key={c.id} value={c.code}>
                  {c.name || c.code}
                </option>
              ))}
              <option value={UNASSIGNED_CLASS}>未分班</option>
            </select>
          </div>

          <div className="flex-1 min-w-[220px]">
            <label className="block text-xs text-slate-500 mb-1">搜索</label>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="学号或姓名"
                className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
              />
            </div>
          </div>

          <button
            onClick={handleExport}
            disabled={!selectedClass || exporting || activityQ.isLoading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 text-white text-sm hover:bg-brand-700 disabled:opacity-60"
          >
            {exporting ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
            导出 xlsx
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
            <Users size={14} /> 当前班级
          </div>
          <div className="text-xl font-semibold text-slate-800 truncate">{classLabel}</div>
          <div className="text-xs text-slate-400 mt-1">{selectedClass || "-"}</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
            <Users size={14} /> 学生数
          </div>
          <div className="text-2xl font-semibold text-slate-800">{rows.length}</div>
          <div className="text-xs text-slate-400 mt-1">{totals.activeStudents} 人有使用记录</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
            <BarChart3 size={14} /> 总时长
          </div>
          <div className="text-2xl font-semibold text-slate-800">
            {formatHours(totals.totalSeconds)}
          </div>
          <div className="text-xs text-slate-400 mt-1">{formatDuration(totals.totalSeconds)}</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
            <Clock size={14} /> 人均时长
          </div>
          <div className="text-2xl font-semibold text-slate-800">
            {formatHours(totals.avgSeconds)}
          </div>
          <div className="text-xs text-slate-400 mt-1">{formatDuration(totals.avgSeconds)}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-4 items-start">
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 bg-slate-50 flex items-center gap-3">
            <div className="font-semibold text-slate-800 flex items-center gap-2">
              <Users size={16} className="text-slate-500" /> {classLabel}
            </div>
            <div className="text-xs text-slate-500">{rows.length} 人</div>
          </div>

          {activityQ.isLoading ? (
            <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
              <Loader2 size={16} className="animate-spin" /> 加载中…
            </div>
          ) : rows.length === 0 ? (
            <div className="p-8 text-center text-slate-400">无匹配学生</div>
          ) : (
            <div className="overflow-x-auto max-h-[calc(100vh-19rem)]">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white z-10">
                  <tr className="text-xs text-slate-500 border-b border-slate-200 bg-slate-50">
                    <th className="text-left px-4 py-2.5 font-medium">学号</th>
                    <th className="text-left px-4 py-2.5 font-medium">姓名</th>
                    <th className="text-right px-4 py-2.5 font-medium">使用时长</th>
                    <th className="text-center px-4 py-2.5 font-medium">会话</th>
                    <th className="text-center px-4 py-2.5 font-medium">分组</th>
                    <th className="text-center px-4 py-2.5 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.user_id}
                      className={clsx(
                        "border-b border-slate-50 hover:bg-slate-50 transition-colors",
                        row.user_id === selectedUserId && "bg-brand-50/60",
                      )}
                    >
                      <td className="px-4 py-2 font-mono text-xs text-slate-700">
                        {row.username}
                      </td>
                      <td className="px-4 py-2 text-slate-800">{row.display_name}</td>
                      <td className="px-4 py-2 text-right">
                        <div className="font-medium text-slate-800">
                          {formatDuration(row.total_seconds)}
                        </div>
                        <div className="text-[11px] text-slate-400">
                          {formatHours(row.total_seconds)}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-center">
                        {row.session_count > 0 ? (
                          <Link
                            to={`/admin/chat-sessions?user_id=${row.user_id}`}
                            className="inline-flex items-center gap-1 text-brand-600 hover:underline text-xs"
                          >
                            <MessageSquare size={12} /> {row.session_count}
                          </Link>
                        ) : (
                          <span className="text-slate-300 text-xs">0</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-center text-xs text-slate-600">
                        {groupLabel(row.experiment_group)}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <button
                          onClick={() => setSelectedUserId(row.user_id)}
                          className="inline-flex items-center justify-center gap-1 px-2 py-1 rounded text-xs text-brand-700 hover:bg-brand-50"
                        >
                          <Eye size={13} /> 详情
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <aside className="bg-white rounded-lg border border-slate-200 overflow-hidden xl:sticky xl:top-6">
          <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
            <div className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Eye size={15} /> 学生明细
            </div>
          </div>

          {!selectedUserId ? (
            <div className="p-8 text-center text-slate-400 text-sm">未选择学生</div>
          ) : detailQ.isLoading && !selectedSummary ? (
            <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
              <Loader2 size={16} className="animate-spin" /> 加载中…
            </div>
          ) : selectedDetail ? (
            <div className="p-4">
              <div className="mb-4">
                <div className="text-base font-semibold text-slate-800">
                  {selectedDetail.display_name}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {selectedDetail.username} · {selectedDetail.class_code || "未分班"} · {groupLabel(selectedDetail.experiment_group)}
                </div>
              </div>

              <div className="border-y border-slate-200 mb-4">
                <div className="py-3 flex items-center justify-between gap-4">
                  <div className="text-xs text-slate-500">总时长</div>
                  <div className="text-right">
                    <div className="text-lg font-semibold text-slate-800">
                      {formatDuration(selectedDetail.total_seconds)}
                    </div>
                    <div className="text-xs text-slate-400">{formatHours(selectedDetail.total_seconds)}</div>
                  </div>
                </div>
              </div>

              <Link
                to={`/admin/chat-sessions?user_id=${selectedDetail.user_id}`}
                className="w-full mb-4 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-brand-200 text-sm text-brand-700 hover:bg-brand-50"
              >
                <MessageSquare size={14} /> 聊天记录
              </Link>

              <div>
                <div className="text-sm font-semibold text-slate-700 mb-2">会话时长</div>
                {!detailQ.data ? (
                  <div className="text-xs text-slate-400 flex items-center gap-2">
                    <Loader2 size={14} className="animate-spin" /> 加载会话…
                  </div>
                ) : !detailQ.data.by_session || detailQ.data.by_session.length === 0 ? (
                  <div className="text-sm text-slate-400 py-6 text-center">暂无会话</div>
                ) : (
                  <div className="max-h-[360px] overflow-y-auto border border-slate-200 rounded-lg">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-slate-50 text-slate-500">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium">会话</th>
                          <th className="text-left px-3 py-2 font-medium">题目</th>
                          <th className="text-right px-3 py-2 font-medium">时长</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailQ.data.by_session.map((session) => (
                          <tr key={session.session_id} className="border-t border-slate-100">
                            <td className="px-3 py-2">
                              <div className="font-medium text-slate-700">#{session.session_id}</div>
                              <div className="text-slate-400">
                                {DIAGRAM_LABELS[session.diagram_type] || session.diagram_type}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-slate-600">
                              <div>{session.problem_code || "—"}</div>
                              <div className="text-slate-400">
                                {session.latest_score != null ? `${session.latest_score}分` : session.status}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-right font-medium text-slate-800">
                              {formatDuration(session.active_seconds)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-slate-400 text-sm">无明细</div>
          )}
        </aside>
      </div>
    </div>
  );
}
