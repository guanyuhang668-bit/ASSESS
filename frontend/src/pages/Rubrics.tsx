import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activateRubric, getRubricDetail, importRubric, listRubricVersions,
} from "@/lib/api";
import { CheckCircle2 } from "lucide-react";

const DIAGRAM_TYPES = ["use_case", "class", "sequence", "swimlane"];

export default function Rubrics() {
  const qc = useQueryClient();
  const versions = useQuery({ queryKey: ["rubric-versions"], queryFn: () => listRubricVersions() });
  const [selected, setSelected] = useState<number | null>(null);
  const detail = useQuery({
    queryKey: ["rubric-detail", selected],
    queryFn: () => (selected ? getRubricDetail(selected) : Promise.resolve(null)),
    enabled: !!selected,
  });

  const importMut = useMutation({
    mutationFn: (body: { diagram_type: string; yaml_filename: string; name: string; activate: boolean }) =>
      importRubric(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rubric-versions"] }),
  });
  const activateMut = useMutation({
    mutationFn: (id: number) => activateRubric(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rubric-versions"] }),
  });

  const [impDtype, setImpDtype] = useState("use_case");
  const [impFile, setImpFile] = useState("use_case.yaml");
  const [impName, setImpName] = useState("v1");

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4">评分标准</h1>

      <div className="bg-white rounded-lg border border-slate-200 p-4 mb-4">
        <div className="text-sm font-medium mb-2">从 backend/configs/rubrics/ 导入 YAML</div>
        <div className="flex gap-2 flex-wrap">
          <select
            value={impDtype}
            onChange={(e) => setImpDtype(e.target.value)}
            className="px-3 py-2 rounded border border-slate-300 text-sm"
          >
            {DIAGRAM_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
          <input
            value={impFile} onChange={(e) => setImpFile(e.target.value)}
            placeholder="use_case.yaml"
            className="flex-1 min-w-[200px] px-3 py-2 rounded border border-slate-300 text-sm font-mono"
          />
          <input
            value={impName} onChange={(e) => setImpName(e.target.value)}
            placeholder="v1"
            className="w-32 px-3 py-2 rounded border border-slate-300 text-sm"
          />
          <button
            disabled={importMut.isPending}
            onClick={() => importMut.mutate({
              diagram_type: impDtype, yaml_filename: impFile, name: impName, activate: true,
            })}
            className="px-4 py-2 bg-brand-600 text-white rounded text-sm hover:bg-brand-700 disabled:opacity-60"
          >
            {importMut.isPending ? "导入中…" : "导入并激活"}
          </button>
        </div>
        {importMut.isError && (
          <div className="text-sm text-red-600 mt-2">
            {(importMut.error as any)?.response?.data?.detail || String(importMut.error)}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-slate-200">
          <div className="px-4 py-3 border-b text-sm font-medium">版本列表</div>
          <ul className="divide-y divide-slate-100 text-sm">
            {versions.data?.map((v) => (
              <li
                key={v.id}
                onClick={() => setSelected(v.id)}
                className={`px-4 py-2 cursor-pointer hover:bg-slate-50 flex items-center gap-2 ${
                  selected === v.id ? "bg-brand-50" : ""
                }`}
              >
                <span className="text-xs text-slate-400">#{v.id}</span>
                <span className="font-mono text-xs">{v.diagram_type}</span>
                <span className="flex-1">{v.name}</span>
                {v.is_active && <CheckCircle2 size={14} className="text-green-600" />}
              </li>
            ))}
          </ul>
        </div>

        <div className="md:col-span-2 bg-white rounded-lg border border-slate-200">
          <div className="px-4 py-3 border-b text-sm font-medium flex items-center justify-between">
            <span>指标详情</span>
            {detail.data && !detail.data.is_active && (
              <button
                onClick={() => activateMut.mutate(detail.data!.id)}
                className="text-xs text-brand-600 hover:underline"
              >
                激活此版本
              </button>
            )}
          </div>
          {!detail.data ? (
            <div className="p-8 text-center text-sm text-slate-400">请在左侧选择一个版本</div>
          ) : (
            <div className="p-4 space-y-2 max-h-[600px] overflow-auto">
              <div className="text-xs text-slate-500">
                {detail.data.diagram_type} / {detail.data.name} · 共 {detail.data.criteria.length} 条
              </div>
              {detail.data.criteria.map((c) => (
                <div key={c.id} className="border border-slate-100 rounded p-3 text-sm">
                  <div className="flex items-start gap-2">
                    <span className="font-mono text-xs text-brand-600 shrink-0">{c.code}</span>
                    <span className="font-medium flex-1">{c.name}</span>
                    <span className="text-xs text-slate-400">weight {c.weight}</span>
                    {c.error_freq_total > 0 && (
                      <span className="text-xs text-red-500">频次 {c.error_freq_total}</span>
                    )}
                  </div>
                  {c.description && (
                    <div className="text-xs text-slate-500 mt-1 pl-12">{c.description}</div>
                  )}
                  {c.common_errors.length > 0 && (
                    <ul className="mt-1 pl-12 text-xs text-slate-400 list-disc list-inside">
                      {c.common_errors.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
