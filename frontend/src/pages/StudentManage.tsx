import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listStudents,
  listClasses,
  updateStudent,
  resetStudentPassword,
  deleteStudent,
  type AdminStudent,
  type StudentUpdateBody,
} from "@/lib/api";
import {
  Users,
  Search,
  Edit3,
  KeyRound,
  Trash2,
  Check,
  X,
  Trophy,
  MessageSquare,
  Loader2,
} from "lucide-react";
import { clsx } from "clsx";
import { Link } from "react-router-dom";

const GROUPS = [
  { value: "", label: "全部分组" },
  { value: "agent_a", label: "Agent A", color: "bg-blue-100 text-blue-700" },
  { value: "agent_b", label: "Agent B", color: "bg-purple-100 text-purple-700" },
  { value: "agent_c", label: "Agent C", color: "bg-amber-100 text-amber-700" },
  { value: "control", label: "对照组", color: "bg-slate-100 text-slate-700" },
  { value: "multi_model_a", label: "四模型A", color: "bg-emerald-100 text-emerald-700" },
  { value: "unassigned", label: "未分配", color: "bg-red-100 text-red-700" },
];

const ORDER_LABELS: Record<string, string> = {
  normal: "class1→class2、swimlane1→swimlane2",
  reversed: "class2→class1、swimlane2→swimlane1",
};

function groupBadge(g: string | null) {
  const grp = GROUPS.find((x) => x.value === (g || "unassigned"));
  if (!grp || !grp.color) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span className={clsx("px-2 py-0.5 rounded-full text-xs font-medium", grp.color)}>
      {grp.label}
    </span>
  );
}

interface EditState {
  experiment_group: string;
  cohort_group: string;
  problem_order: string;
  session_group: string;
  display_name: string;
}

export default function StudentManage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [filterClass, setFilterClass] = useState("");
  const [filterGroup, setFilterGroup] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editState, setEditState] = useState<EditState>({
    experiment_group: "",
    cohort_group: "",
    problem_order: "",
    session_group: "",
    display_name: "",
  });

  const studentsQ = useQuery({
    queryKey: ["admin-students", search, filterClass, filterGroup],
    queryFn: () =>
      listStudents({
        search: search || undefined,
        class_code: filterClass || undefined,
        experiment_group: filterGroup || undefined,
      }),
  });

  const classesQ = useQuery({
    queryKey: ["classes"],
    queryFn: listClasses,
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: StudentUpdateBody }) =>
      updateStudent(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-students"] });
      setEditingId(null);
    },
  });

  const resetPwdMut = useMutation({
    mutationFn: resetStudentPassword,
    onSuccess: (data) => alert(data.message),
  });

  const deleteMut = useMutation({
    mutationFn: deleteStudent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-students"] }),
  });

  const students = studentsQ.data || [];

  function startEdit(s: AdminStudent) {
    setEditingId(s.id);
    setEditState({
      experiment_group: s.experiment_group || "",
      cohort_group: s.cohort_group || "",
      problem_order: s.problem_order || "",
      session_group: s.session_group || "",
      display_name: s.display_name,
    });
  }

  function cancelEdit() {
    setEditingId(null);
  }

  function saveEdit(id: number) {
    updateMut.mutate({
      id,
      body: {
        display_name: editState.display_name,
        experiment_group: editState.experiment_group,
        cohort_group: editState.cohort_group,
        problem_order: editState.problem_order,
        session_group: editState.session_group,
      },
    });
  }

  function handleResetPwd(s: AdminStudent) {
    if (confirm(`确认重置 ${s.display_name}（${s.username}）的密码为 ${s.username}123？`)) {
      resetPwdMut.mutate(s.id);
    }
  }

  function handleDelete(s: AdminStudent) {
    if (confirm(`确认删除 ${s.display_name}（${s.username}）？相关聊天记录将一并删除！`)) {
      deleteMut.mutate(s.id);
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4 flex items-center gap-2">
        <Users size={20} /> 学生管理
      </h1>

      {/* 筛选栏 */}
      <div className="bg-white rounded-lg border border-slate-200 p-4 mb-4">
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-slate-500 mb-1">搜索</label>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="学号或姓名…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">班级</label>
            <select
              value={filterClass}
              onChange={(e) => setFilterClass(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm min-w-[140px] focus:ring-2 focus:ring-brand-500 outline-none"
            >
              <option value="">全部班级</option>
              {(classesQ.data || []).map((c) => (
                <option key={c.id} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">分组</label>
            <select
              value={filterGroup}
              onChange={(e) => setFilterGroup(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-300 text-sm min-w-[140px] focus:ring-2 focus:ring-brand-500 outline-none"
            >
              {GROUPS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </select>
          </div>
          <div className="text-sm text-slate-500 self-center">
            共 <strong>{students.length}</strong> 人
          </div>
        </div>
      </div>

      {/* 学生表格 */}
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        {studentsQ.isLoading ? (
          <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
            <Loader2 size={16} className="animate-spin" /> 加载中…
          </div>
        ) : students.length === 0 ? (
          <div className="p-8 text-center text-slate-400">无匹配学生</div>
        ) : (
          <div className="overflow-y-auto max-h-[calc(100vh-12rem)]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="text-xs text-slate-500 border-b border-slate-200 bg-slate-50">
                  <th className="text-left px-3 py-2.5 font-medium">学号</th>
                  <th className="text-left px-3 py-2.5 font-medium">姓名</th>
                  <th className="text-left px-3 py-2.5 font-medium">班级</th>
                  <th className="text-center px-3 py-2.5 font-medium" title="原实验分组字段，仅供参考">实验分组</th>
                  <th className="text-center px-3 py-2.5 font-medium bg-amber-50" title="当次实验实际使用的 Agent">本次分组</th>
                  <th className="text-center px-3 py-2.5 font-medium">C组</th>
                  <th className="text-center px-3 py-2.5 font-medium">题目顺序</th>
                  <th className="text-center px-3 py-2.5 font-medium">会话</th>
                  <th className="text-center px-3 py-2.5 font-medium">最高分</th>
                  <th className="text-center px-3 py-2.5 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s) => {
                  const isEditing = editingId === s.id;
                  return (
                    <tr
                      key={s.id}
                      className={clsx(
                        "border-b border-slate-50 hover:bg-slate-50 transition-colors",
                        !s.is_active && "opacity-50"
                      )}
                    >
                      <td className="px-3 py-2 font-mono text-xs text-slate-700">
                        {s.username}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <input
                            value={editState.display_name}
                            onChange={(e) =>
                              setEditState((p) => ({ ...p, display_name: e.target.value }))
                            }
                            className="w-full px-2 py-1 border border-slate-300 rounded text-sm"
                          />
                        ) : (
                          <span className="text-slate-700">{s.display_name}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-500 text-xs">{s.class_name || "—"}</td>
                      <td className="px-3 py-2 text-center">
                        {isEditing ? (
                          <select
                            value={editState.experiment_group}
                            onChange={(e) =>
                              setEditState((p) => ({ ...p, experiment_group: e.target.value }))
                            }
                            className="px-2 py-1 border border-slate-300 rounded text-xs"
                          >
                            <option value="">未分配</option>
                            <option value="agent_a">Agent A</option>
                            <option value="agent_b">Agent B</option>
                            <option value="agent_c">Agent C</option>
                            <option value="control">对照组</option>
                            <option value="multi_model_a">四模型A</option>
                          </select>
                        ) : (
                          groupBadge(s.experiment_group)
                        )}
                      </td>
                      <td className="px-3 py-2 text-center bg-amber-50/30">
                        {isEditing ? (
                          <select
                            value={editState.session_group}
                            onChange={(e) =>
                              setEditState((p) => ({ ...p, session_group: e.target.value }))
                            }
                            className="px-2 py-1 border border-slate-300 rounded text-xs"
                          >
                            <option value="">未分配</option>
                            <option value="agent_a">Agent A</option>
                            <option value="agent_b">Agent B</option>
                            <option value="agent_c">Agent C</option>
                            <option value="control">对照组</option>
                            <option value="multi_model_a">四模型A</option>
                          </select>
                        ) : (
                          groupBadge(s.session_group)
                        )}
                      </td>
                      <td className="px-3 py-2 text-center text-xs text-slate-600">
                        {isEditing ? (
                          <input
                            value={editState.cohort_group}
                            onChange={(e) =>
                              setEditState((p) => ({ ...p, cohort_group: e.target.value }))
                            }
                            placeholder="C1~C16"
                            className="w-16 px-2 py-1 border border-slate-300 rounded text-xs text-center"
                          />
                        ) : (
                          s.cohort_group || "—"
                        )}
                      </td>
                      <td className="px-3 py-2 text-center text-xs text-slate-500">
                        {isEditing ? (
                          <select
                            value={editState.problem_order}
                            onChange={(e) =>
                              setEditState((p) => ({ ...p, problem_order: e.target.value }))
                            }
                            className="px-2 py-1 border border-slate-300 rounded text-xs"
                          >
                            <option value="">未设置</option>
                            <option value="normal">normal</option>
                            <option value="reversed">reversed</option>
                          </select>
                        ) : s.problem_order ? (
                          <span title={ORDER_LABELS[s.problem_order] || ""}>
                            {s.problem_order}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {s.session_count > 0 ? (
                          <Link
                            to={`/admin/chat-sessions?user_id=${s.id}`}
                            className="inline-flex items-center gap-1 text-brand-600 hover:underline text-xs"
                          >
                            <MessageSquare size={12} /> {s.session_count}
                          </Link>
                        ) : (
                          <span className="text-slate-300 text-xs">0</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {s.best_score != null ? (
                          <span
                            className={clsx(
                              "inline-flex items-center gap-1 text-xs font-medium",
                              s.best_score >= 80
                                ? "text-green-600"
                                : s.best_score >= 60
                                ? "text-amber-600"
                                : "text-red-600"
                            )}
                          >
                            <Trophy size={12} /> {s.best_score}
                          </span>
                        ) : (
                          <span className="text-slate-300 text-xs">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {isEditing ? (
                          <div className="flex items-center justify-center gap-1">
                            <button
                              onClick={() => saveEdit(s.id)}
                              disabled={updateMut.isPending}
                              className="p-1 text-green-600 hover:bg-green-50 rounded"
                              title="保存"
                            >
                              {updateMut.isPending ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : (
                                <Check size={14} />
                              )}
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="p-1 text-slate-400 hover:bg-slate-100 rounded"
                              title="取消"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-center gap-1">
                            <button
                              onClick={() => startEdit(s)}
                              className="p-1 text-slate-500 hover:text-brand-600 hover:bg-brand-50 rounded"
                              title="编辑"
                            >
                              <Edit3 size={14} />
                            </button>
                            <button
                              onClick={() => handleResetPwd(s)}
                              className="p-1 text-slate-500 hover:text-amber-600 hover:bg-amber-50 rounded"
                              title="重置密码"
                            >
                              <KeyRound size={14} />
                            </button>
                            <button
                              onClick={() => handleDelete(s)}
                              className="p-1 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded"
                              title="删除"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
