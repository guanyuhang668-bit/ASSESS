import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getGroupsSummary,
  getGroupsMembers,
  assignGroup,
  assignSessionGroup,
  listClasses,
  type GroupSummaryItem,
  type GroupMember,
  type AssignGroupResult,
  type AssignSessionGroupResult,
} from "@/lib/api";
import {
  Users,
  FlaskConical,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  MessageSquare,
  Trophy,
} from "lucide-react";
import { clsx } from "clsx";
import { Link } from "react-router-dom";

const GROUPS = [
  { value: "agent_a", label: "Agent A（单次反馈）", color: "bg-blue-100 text-blue-700", border: "border-blue-200" },
  { value: "agent_b", label: "Agent B（多轮引导）", color: "bg-purple-100 text-purple-700", border: "border-purple-200" },
  { value: "agent_c", label: "Agent C（渐进式）", color: "bg-amber-100 text-amber-700", border: "border-amber-200" },
  { value: "control", label: "对照组（教师）", color: "bg-slate-100 text-slate-700", border: "border-slate-200" },
  { value: "multi_model_a", label: "四模型 Agent A", color: "bg-emerald-100 text-emerald-700", border: "border-emerald-200" },
  { value: "unassigned", label: "未分配", color: "bg-red-100 text-red-700", border: "border-red-200" },
];

function groupLabel(g: string) {
  return GROUPS.find((x) => x.value === g)?.label || g;
}
function groupColor(g: string) {
  return GROUPS.find((x) => x.value === g)?.color || "bg-slate-100 text-slate-600";
}

function formatTime(ts: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export default function GroupManage() {
  const queryClient = useQueryClient();

  const summaryQ = useQuery({
    queryKey: ["groups-summary"],
    queryFn: getGroupsSummary,
  });

  const membersQ = useQuery({
    queryKey: ["groups-members"],
    queryFn: getGroupsMembers,
  });

  const classesQ = useQuery({
    queryKey: ["classes"],
    queryFn: listClasses,
  });

  const [selectedClass, setSelectedClass] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("agent_a");
  const [lastResult, setLastResult] = useState<AssignGroupResult | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // 本次实验 session_group 状态
  const [sgScope, setSgScope] = useState<"all" | "class">("all");
  const [sgClass, setSgClass] = useState("");
  const [sgGroup, setSgGroup] = useState("agent_c");
  const [sgResult, setSgResult] = useState<AssignSessionGroupResult | null>(null);

  const assignMut = useMutation({
    mutationFn: () => assignGroup(selectedClass, selectedGroup),
    onSuccess: (data) => {
      setLastResult(data);
      queryClient.invalidateQueries({ queryKey: ["groups-summary"] });
      queryClient.invalidateQueries({ queryKey: ["groups-members"] });
    },
  });

  const assignSgMut = useMutation({
    mutationFn: () =>
      assignSessionGroup({
        scope: sgScope,
        class_code: sgScope === "class" ? sgClass : undefined,
        session_group: sgGroup,
      }),
    onSuccess: (data) => {
      setSgResult(data);
      queryClient.invalidateQueries({ queryKey: ["admin-students"] });
    },
  });

  const toggleGroup = (g: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(g)) next.delete(g);
      else next.add(g);
      return next;
    });
  };

  const summary = summaryQ.data || [];
  const members = membersQ.data || {};
  const unassigned = summary.find((g) => g.group === "unassigned")?.count || 0;

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4 flex items-center gap-2">
        <FlaskConical size={20} /> 实验分组管理
      </h1>

      {/* 分组统计卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        {GROUPS.filter((g) => g.value !== "unassigned").map((g) => {
          const count = summary.find((s) => s.group === g.value)?.count || 0;
          return (
            <div
              key={g.value}
              className="bg-white rounded-lg border border-slate-200 p-4 cursor-pointer hover:shadow-sm transition-shadow"
              onClick={() => toggleGroup(g.value)}
            >
              <div className={clsx("text-xs font-medium px-2 py-0.5 rounded-full inline-block mb-2", g.color)}>
                {g.label}
              </div>
              <div className="text-2xl font-bold text-slate-800">{count}</div>
              <div className="text-xs text-slate-400">人 · 点击展开</div>
            </div>
          );
        })}
        <div
          className="bg-white rounded-lg border border-slate-200 p-4 cursor-pointer hover:shadow-sm transition-shadow"
          onClick={() => toggleGroup("unassigned")}
        >
          <div className="text-xs font-medium px-2 py-0.5 rounded-full inline-block mb-2 bg-red-100 text-red-700">
            未分配
          </div>
          <div className="text-2xl font-bold text-slate-800">{unassigned}</div>
          <div className="text-xs text-slate-400">人 · 点击展开</div>
        </div>
      </div>

      {/* 分组成员详情 */}
      {GROUPS.map((g) => {
        const isExpanded = expandedGroups.has(g.value);
        const groupMembers = members[g.value] || [];
        if (!isExpanded) return null;

        return (
          <div key={g.value} className={clsx("bg-white rounded-lg border mb-4", g.border)}>
            <div
              className="flex items-center justify-between p-4 cursor-pointer"
              onClick={() => toggleGroup(g.value)}
            >
              <div className="flex items-center gap-2">
                {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                <span className={clsx("text-xs font-medium px-2 py-0.5 rounded-full", g.color)}>{g.label}</span>
                <span className="text-sm text-slate-500">{groupMembers.length} 人</span>
              </div>
            </div>

            {groupMembers.length === 0 ? (
              <div className="px-4 pb-4 text-sm text-slate-400">暂无成员</div>
            ) : (
              <div className="px-4 pb-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-500 border-b border-slate-100">
                      <th className="text-left py-2 font-medium">学号</th>
                      <th className="text-left py-2 font-medium">姓名</th>
                      <th className="text-left py-2 font-medium">班级</th>
                      <th className="text-center py-2 font-medium">聊天会话</th>
                      <th className="text-center py-2 font-medium">最高分</th>
                      <th className="text-center py-2 font-medium">最近活跃</th>
                      <th className="text-center py-2 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupMembers.map((m) => (
                      <tr key={m.id} className="border-b border-slate-50 hover:bg-slate-50">
                        <td className="py-2 text-slate-700 font-mono text-xs">{m.username}</td>
                        <td className="py-2 text-slate-700">{m.display_name}</td>
                        <td className="py-2 text-slate-500">{m.class_code || "—"}</td>
                        <td className="py-2 text-center">
                          <span className="inline-flex items-center gap-1 text-slate-600">
                            <MessageSquare size={12} /> {m.session_count}
                          </span>
                        </td>
                        <td className="py-2 text-center">
                          {m.best_score != null ? (
                            <span className={clsx(
                              "inline-flex items-center gap-1 font-medium",
                              m.best_score >= 80 ? "text-green-600" : m.best_score >= 60 ? "text-amber-600" : "text-red-600"
                            )}>
                              <Trophy size={12} /> {m.best_score}
                            </span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                        <td className="py-2 text-center text-xs text-slate-400">{formatTime(m.last_active)}</td>
                        <td className="py-2 text-center">
                          {m.session_count > 0 && (
                            <Link
                              to={`/admin/chat-sessions?user_id=${m.id}`}
                              className="text-xs text-brand-600 hover:underline"
                            >
                              查看聊天
                            </Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}

      {/* 本次实验 Agent 批量分配（session_group，当前生效） */}
      <div className="bg-amber-50 rounded-lg border border-amber-200 p-5 mb-4">
        <h2 className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-2">
          <FlaskConical size={14} /> 本次实验 Agent 分配（session_group · 当前生效）
        </h2>
        <p className="text-xs text-amber-700 mb-4">
          此处设置当次实验学生实际使用的 Agent，与上方原始 <strong>experiment_group</strong> 分组解耦、互不影响。
          学生进入聊天界面时优先读取 <strong>session_group</strong>，未设置才回退到原始分组。
        </p>

        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-amber-700 mb-1">范围</label>
            <select
              value={sgScope}
              onChange={(e) => setSgScope(e.target.value as "all" | "class")}
              className="px-3 py-2 rounded-lg border border-amber-300 text-sm min-w-[140px] bg-white focus:ring-2 focus:ring-amber-500 outline-none"
            >
              <option value="all">全体学生</option>
              <option value="class">指定班级</option>
            </select>
          </div>

          {sgScope === "class" && (
            <div>
              <label className="block text-xs text-amber-700 mb-1">班级</label>
              <select
                value={sgClass}
                onChange={(e) => setSgClass(e.target.value)}
                className="px-3 py-2 rounded-lg border border-amber-300 text-sm min-w-[160px] bg-white focus:ring-2 focus:ring-amber-500 outline-none"
              >
                <option value="">-- 选择班级 --</option>
                {(classesQ.data || []).map((c) => (
                  <option key={c.id} value={c.code}>{c.code} - {c.name}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-xs text-amber-700 mb-1">Agent 类型</label>
            <select
              value={sgGroup}
              onChange={(e) => setSgGroup(e.target.value)}
              className="px-3 py-2 rounded-lg border border-amber-300 text-sm min-w-[200px] bg-white focus:ring-2 focus:ring-amber-500 outline-none"
            >
              {GROUPS.filter((g) => g.value !== "unassigned").map((g) => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
              <option value="">（清空 session_group）</option>
            </select>
          </div>

          <button
            disabled={
              assignSgMut.isPending || (sgScope === "class" && !sgClass)
            }
            onClick={() => assignSgMut.mutate()}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 disabled:opacity-60 flex items-center gap-2"
          >
            {assignSgMut.isPending ? <Loader2 size={14} className="animate-spin" /> : <Users size={14} />}
            {assignSgMut.isPending ? "分配中…" : "执行分配"}
          </button>
        </div>

        {sgResult && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 flex items-center gap-2">
            <CheckCircle2 size={16} />
            已将 <strong>{sgResult.updated}</strong> 名学生的 session_group 设为{" "}
            <strong>{sgResult.session_group ? groupLabel(sgResult.session_group) : "（已清空）"}</strong>
          </div>
        )}

        {assignSgMut.isError && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2">
            <AlertCircle size={16} />
            {(assignSgMut.error as any)?.response?.data?.detail || (assignSgMut.error as any)?.message || "分配失败"}
          </div>
        )}
      </div>

      {/* 按班级分配（原 experiment_group，历史字段，不再驱动 Agent） */}
      <div className="bg-white rounded-lg border border-slate-200 p-5 mb-4">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">
          按班级分配实验分组 <span className="text-xs text-slate-400 font-normal">（experiment_group · 历史字段，仅记录用）</span>
        </h2>
        <p className="text-xs text-slate-500 mb-4">
          选择一个班级和实验分组，将该班级内所有学生统一分配到该组。
          <span className="text-amber-700">
            注意：此字段为历史记录字段，<strong>不再决定学生使用哪个 Agent</strong>，请在上方"本次实验 Agent 分配"中设置。
          </span>
        </p>

        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-slate-500 mb-1">班级</label>
            <select
              value={selectedClass}
              onChange={(e) => setSelectedClass(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm min-w-[160px] focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
            >
              <option value="">-- 选择班级 --</option>
              {(classesQ.data || []).map((c) => (
                <option key={c.id} value={c.code}>{c.code} - {c.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-500 mb-1">实验分组</label>
            <select
              value={selectedGroup}
              onChange={(e) => setSelectedGroup(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm min-w-[200px] focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
            >
              {GROUPS.filter((g) => g.value !== "unassigned").map((g) => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
          </div>

          <button
            disabled={!selectedClass || assignMut.isPending}
            onClick={() => assignMut.mutate()}
            className="px-4 py-2 bg-brand-600 text-white rounded-lg text-sm hover:bg-brand-700 disabled:opacity-60 flex items-center gap-2"
          >
            {assignMut.isPending ? <Loader2 size={14} className="animate-spin" /> : <Users size={14} />}
            {assignMut.isPending ? "分配中…" : "执行分配"}
          </button>
        </div>

        {lastResult && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 flex items-center gap-2">
            <CheckCircle2 size={16} />
            已将班级 <strong>{lastResult.class_code}</strong> 的{" "}
            <strong>{lastResult.updated}</strong> 名学生分配到{" "}
            <strong>{groupLabel(lastResult.experiment_group)}</strong>
          </div>
        )}

        {assignMut.isError && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2">
            <AlertCircle size={16} />
            {(assignMut.error as any)?.response?.data?.detail || (assignMut.error as any)?.message || "分配失败"}
          </div>
        )}
      </div>

      {/* 说明 */}
      <div className="bg-white rounded-lg border border-slate-200 p-5">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">分组说明</h2>
        <div className="space-y-3 text-sm text-slate-600">
          <div className="flex gap-3">
            <span className={clsx("shrink-0 px-2 py-0.5 rounded-full text-xs font-medium", GROUPS[0].color)}>Agent A</span>
            <span><strong>单次反馈</strong>：提交后一次性获得完整的评分、问题列表和修改建议。学生自行修改后可重新提交。</span>
          </div>
          <div className="flex gap-3">
            <span className={clsx("shrink-0 px-2 py-0.5 rounded-full text-xs font-medium", GROUPS[1].color)}>Agent B</span>
            <span><strong>多轮引导</strong>：每轮只指出 1-2 个最关键问题，学生修改后再提交，循环直到达标（≥80分）。</span>
          </div>
          <div className="flex gap-3">
            <span className={clsx("shrink-0 px-2 py-0.5 rounded-full text-xs font-medium", GROUPS[2].color)}>Agent C</span>
            <span><strong>渐进式</strong>：先给问题方向不给答案，如果修改未改善则逐步深入，直到学生理解并改正。</span>
          </div>
          <div className="flex gap-3">
            <span className={clsx("shrink-0 px-2 py-0.5 rounded-full text-xs font-medium", GROUPS[3].color)}>对照组</span>
            <span><strong>教师批改</strong>：不使用 AI Agent，由教师手动提供反馈。学生端会显示提示。</span>
          </div>
        </div>
      </div>
    </div>
  );
}
