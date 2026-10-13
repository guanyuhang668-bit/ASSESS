import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  cancelRun, createGradingRun, getGradingProgress, getGradingRun,
  listGradingRuns, listModels, listRunResults, listSubmissions,
  openProgressWs,
} from "@/lib/api";
import { Play, RefreshCw, XCircle } from "lucide-react";

const DIAGRAM_TYPES = ["use_case", "class", "sequence", "swimlane"] as const;

function StatusBadge({ status }: { status: string }) {
  const color: Record<string, string> = {
    pending: "bg-slate-100 text-slate-600",
    running: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    cancelled: "bg-amber-100 text-amber-700",
    success: "bg-green-100 text-green-700",
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs ${color[status] || "bg-slate-100"}`}>
      {status}
    </span>
  );
}

function CreateForm({ onCreated }: { onCreated: (id: number) => void }) {
  const qc = useQueryClient();
  const models = useQuery({ queryKey: ["models"], queryFn: listModels });
  const [name, setName] = useState(`run-${new Date().toISOString().slice(0, 16)}`);
  const [diagramType, setDiagramType] = useState<string>("use_case");
  const subs = useQuery({
    queryKey: ["subs-for-run", diagramType],
    queryFn: () => listSubmissions({ diagram_type: diagramType, page: 1, page_size: 500 }),
  });
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [pickedModels, setPickedModels] = useState<Set<string>>(new Set(["mock"]));

  const mut = useMutation({
    mutationFn: createGradingRun,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      onCreated(r.id);
    },
  });

  const allIds = useMemo(() => (subs.data?.items || []).map((s) => s.id), [subs.data]);
  const allSelected = allIds.length > 0 && allIds.every((i) => picked.has(i));

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 mb-6">
      <div className="text-sm font-medium mb-3">新建批改任务</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-600 mb-1">任务名</label>
          <input value={name} onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 rounded border border-slate-300 text-sm" />
        </div>
        <div>
          <label className="block text-xs text-slate-600 mb-1">图类型（筛选作品）</label>
          <select value={diagramType} onChange={(e) => { setDiagramType(e.target.value); setPicked(new Set()); }}
            className="w-full px-3 py-2 rounded border border-slate-300 text-sm">
            {DIAGRAM_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      </div>

      <div className="mt-3">
        <label className="block text-xs text-slate-600 mb-1">模型</label>
        <div className="flex flex-wrap gap-2">
          {models.data?.map((m) => (
            <label key={m} className={`px-3 py-1.5 rounded border text-xs cursor-pointer ${
              pickedModels.has(m) ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600"
            }`}>
              <input type="checkbox" className="mr-1" checked={pickedModels.has(m)}
                onChange={() => {
                  const s = new Set(pickedModels);
                  s.has(m) ? s.delete(m) : s.add(m);
                  setPickedModels(s);
                }} />
              {m}
            </label>
          ))}
        </div>
      </div>

      <div className="mt-3">
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs text-slate-600">待批作品（{diagramType}，共 {subs.data?.items.length ?? 0}）</label>
          <button
            onClick={() => setPicked(allSelected ? new Set() : new Set(allIds))}
            className="text-xs text-brand-600 hover:underline"
          >
            {allSelected ? "清空选择" : "全选"}
          </button>
        </div>
        <div className="border border-slate-200 rounded max-h-52 overflow-auto text-sm">
          {subs.data?.items.map((s) => (
            <label key={s.id} className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-100 last:border-0 hover:bg-slate-50">
              <input type="checkbox" checked={picked.has(s.id)}
                onChange={() => {
                  const s2 = new Set(picked);
                  s2.has(s.id) ? s2.delete(s.id) : s2.add(s.id);
                  setPicked(s2);
                }} />
              <span className="font-mono text-xs text-slate-400">#{s.id}</span>
              <span className="text-xs text-slate-500 truncate max-w-[220px]">{s.original_filename}</span>
              <span className="ml-auto text-xs text-slate-400">{s.element_count}e / {s.relation_count}r</span>
            </label>
          ))}
          {!subs.data?.items.length && (
            <div className="p-6 text-center text-slate-400 text-xs">没有符合条件的作品</div>
          )}
        </div>
      </div>

      <button
        disabled={!name || picked.size === 0 || pickedModels.size === 0 || mut.isPending}
        onClick={() => mut.mutate({
          name, description: "",
          submission_ids: Array.from(picked),
          model_keys: Array.from(pickedModels),
        })}
        className="mt-4 px-4 py-2 bg-brand-600 text-white rounded text-sm hover:bg-brand-700 disabled:opacity-60 flex items-center gap-2"
      >
        <Play size={14} />
        {mut.isPending
          ? "创建中…"
          : `创建（${picked.size} 作品 × ${pickedModels.size} 模型 = ${picked.size * pickedModels.size} 任务）`}
      </button>
      {mut.isError && (
        <div className="text-sm text-red-600 mt-2">
          {(mut.error as any)?.response?.data?.detail || String(mut.error)}
        </div>
      )}
    </div>
  );
}

function RunDetail({ runId }: { runId: number }) {
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => getGradingRun(runId) });
  const prog = useQuery({
    queryKey: ["prog", runId], queryFn: () => getGradingProgress(runId),
    refetchInterval: run.data?.status === "running" ? 2000 : false,
  });
  const results = useQuery({
    queryKey: ["run-results", runId], queryFn: () => listRunResults(runId),
    refetchInterval: run.data?.status === "running" ? 3000 : false,
  });
  const qc = useQueryClient();
  const cancelMut = useMutation({
    mutationFn: () => cancelRun(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run", runId] }),
  });

  // WebSocket 实时（可选：有 ws 后端推就用，失败降级为轮询）
  useEffect(() => {
    const ws = openProgressWs(runId, () => qc.invalidateQueries({ queryKey: ["prog", runId] }));
    return () => { try { ws.close(); } catch { /* ignore */ } };
  }, [runId, qc]);

  if (run.isLoading || !run.data) return <div className="text-sm text-slate-500">加载中…</div>;
  const r = run.data;

  const totalDone = (prog.data?.completed ?? 0) + (prog.data?.failed ?? 0);
  const pct = prog.data?.total ? Math.round((totalDone / prog.data.total) * 100) : 0;

  const bySub: Record<number, typeof results.data extends (infer U)[] ? U : never> = {} as any;
  const rows: Record<number, Record<string, { score: number; status: string; id: number }>> = {};
  (results.data || []).forEach((res) => {
    rows[res.submission_id] = rows[res.submission_id] || {};
    rows[res.submission_id][res.model_key] = {
      score: res.normalized_score, status: res.status, id: res.id,
    };
  });

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center gap-3">
          <div className="text-lg font-semibold">{r.name}</div>
          <StatusBadge status={r.status} />
          <div className="ml-auto text-xs text-slate-400">
            {r.started_at ? `起 ${r.started_at.slice(0, 19).replace("T", " ")}` : "未开始"}
          </div>
          {r.status === "running" && (
            <button onClick={() => cancelMut.mutate()}
              className="text-xs text-red-600 hover:underline flex items-center gap-1">
              <XCircle size={12} /> 取消
            </button>
          )}
        </div>
        <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
          <span>共 {prog.data?.total ?? 0} 任务</span>
          <span>完成 {prog.data?.completed ?? 0}</span>
          <span>失败 {prog.data?.failed ?? 0}</span>
          <span>运行中 {prog.data?.running ?? 0}</span>
          <span>待办 {prog.data?.pending ?? 0}</span>
          <button onClick={() => { prog.refetch(); results.refetch(); }}
            className="ml-auto text-brand-600 hover:underline flex items-center gap-1">
            <RefreshCw size={12} /> 刷新
          </button>
        </div>
        <div className="mt-2 w-full h-2 bg-slate-100 rounded overflow-hidden">
          <div className="h-full bg-brand-600 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {Object.entries(prog.data?.per_model || {}).map(([mk, counts]) => (
            <div key={mk} className="border border-slate-100 rounded px-3 py-2 text-xs">
              <div className="font-medium text-slate-700">{mk}</div>
              <div className="text-slate-500">
                ✓ {counts.success ?? 0} · ✗ {counts.failed ?? 0} · ⟳ {counts.running ?? 0} · … {counts.pending ?? 0}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">作品</th>
              {r.model_keys.map((m) => (
                <th key={m} className="text-right px-4 py-2">{m}</th>
              ))}
              <th className="text-left px-4 py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(rows).map((sidStr) => {
              const sid = Number(sidStr);
              return (
                <tr key={sid} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono text-xs text-slate-400">#{sid}</td>
                  {r.model_keys.map((m) => {
                    const cell = rows[sid][m];
                    return (
                      <td key={m} className="px-4 py-2 text-right">
                        {!cell ? <span className="text-slate-300">—</span> :
                          cell.status === "success" ? (
                            <span className="font-medium">{cell.score.toFixed(1)}</span>
                          ) : (
                            <StatusBadge status={cell.status} />
                          )}
                      </td>
                    );
                  })}
                  <td className="px-4 py-2">
                    <Link to={`/compare/${sid}`} className="text-brand-600 text-xs hover:underline">
                      对比
                    </Link>
                  </td>
                </tr>
              );
            })}
            {Object.keys(rows).length === 0 && (
              <tr><td colSpan={r.model_keys.length + 2} className="p-6 text-center text-slate-400 text-xs">暂无结果</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex justify-end">
        <Link to={`/analysis/${r.id}`} className="text-sm text-brand-600 hover:underline">
          查看一致性分析 →
        </Link>
      </div>
    </div>
  );
}

export default function GradingRuns() {
  const { runId: runIdParam } = useParams();
  const [selectedId, setSelectedId] = useState<number | null>(
    runIdParam ? Number(runIdParam) : null,
  );
  const runs = useQuery({ queryKey: ["runs"], queryFn: listGradingRuns });

  useEffect(() => {
    if (runIdParam) setSelectedId(Number(runIdParam));
  }, [runIdParam]);

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4">批改任务</h1>

      <CreateForm onCreated={setSelectedId} />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border border-slate-200">
          <div className="px-4 py-3 border-b text-sm font-medium">任务列表</div>
          <ul className="divide-y divide-slate-100 text-sm">
            {runs.data?.map((r) => (
              <li key={r.id} onClick={() => setSelectedId(r.id)}
                className={`px-4 py-2 cursor-pointer hover:bg-slate-50 ${
                  selectedId === r.id ? "bg-brand-50" : ""
                }`}>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">#{r.id}</span>
                  <span className="flex-1 truncate">{r.name}</span>
                  <StatusBadge status={r.status} />
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {r.model_keys.length} 模型 · {r.submission_ids.length} 作品 ·
                  {" "}{r.completed_tasks}/{r.total_tasks}
                </div>
              </li>
            ))}
            {!runs.data?.length && (
              <li className="px-4 py-8 text-center text-xs text-slate-400">暂无任务</li>
            )}
          </ul>
        </div>

        <div className="md:col-span-3">
          {selectedId ? <RunDetail runId={selectedId} /> :
            <div className="p-12 text-center text-slate-400 text-sm bg-white rounded-lg border border-slate-200">
              请在左侧选择一个任务，或创建新任务
            </div>
          }
        </div>
      </div>
    </div>
  );
}
