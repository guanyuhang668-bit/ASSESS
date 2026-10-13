import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createClass, listClasses, uploadSubmission } from "@/lib/api";
import { Upload as UploadIcon, CheckCircle2, AlertCircle } from "lucide-react";

const DIAGRAM_TYPES = [
  { value: "use_case", label: "用例图" },
  { value: "class", label: "类图" },
  { value: "sequence", label: "时序图" },
  { value: "swimlane", label: "泳道图" },
];

export default function Upload() {
  const qc = useQueryClient();
  const classes = useQuery({ queryKey: ["classes"], queryFn: listClasses });

  const [classId, setClassId] = useState<number | null>(null);
  const [newClassCode, setNewClassCode] = useState("");
  const [diagramType, setDiagramType] = useState("use_case");
  const [problemCode, setProblemCode] = useState("");
  const [problemStatement, setProblemStatement] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [results, setResults] = useState<
    { name: string; ok: boolean; message: string }[]
  >([]);

  const createClassMut = useMutation({
    mutationFn: (code: string) => createClass(code, code),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["classes"] });
      setClassId(c.id);
      setNewClassCode("");
    },
  });

  const uploadMut = useMutation({
    mutationFn: async () => {
      if (!classId) throw new Error("请先选班级");
      setResults([]);
      const out: typeof results = [];
      for (const f of files) {
        // 学号规则：文件名前缀连续数字（如 "202312345_xxx.mdj"）→ 学号
        const m = f.name.match(/^([0-9A-Za-z]+)/);
        const studentCode = m ? m[1] : f.name.replace(/\.mdj$/, "");
        try {
          const sub = await uploadSubmission({
            file: f, class_id: classId, student_code: studentCode,
            diagram_type: diagramType, problem_code: problemCode,
            problem_statement: problemStatement,
          });
          out.push({
            name: f.name, ok: !sub.parse_error,
            message: sub.parse_error
              ? `已收但解析失败: ${sub.parse_error}`
              : `#${sub.id}  元素 ${sub.element_count} 关系 ${sub.relation_count}`,
          });
        } catch (e: any) {
          out.push({
            name: f.name, ok: false,
            message: e?.response?.data?.detail || e?.message || "上传失败",
          });
        }
        setResults([...out]);
      }
    },
  });

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4">上传学生作品</h1>

      <div className="bg-white rounded-lg border border-slate-200 p-4 mb-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-600 mb-1">班级</label>
            <div className="flex gap-2">
              <select
                value={classId ?? ""}
                onChange={(e) => setClassId(Number(e.target.value) || null)}
                className="flex-1 px-3 py-2 rounded border border-slate-300 text-sm"
              >
                <option value="">请选择</option>
                {classes.data?.map((c) => (
                  <option key={c.id} value={c.id}>{c.code} {c.name}</option>
                ))}
              </select>
              <input
                value={newClassCode}
                onChange={(e) => setNewClassCode(e.target.value)}
                placeholder="新建班级编号"
                className="w-40 px-3 py-2 rounded border border-slate-300 text-sm"
              />
              <button
                onClick={() => newClassCode && createClassMut.mutate(newClassCode)}
                className="px-3 py-2 rounded bg-slate-100 hover:bg-slate-200 text-sm"
              >
                新建
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-600 mb-1">图类型</label>
            <select
              value={diagramType}
              onChange={(e) => setDiagramType(e.target.value)}
              className="w-full px-3 py-2 rounded border border-slate-300 text-sm"
            >
              {DIAGRAM_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-600 mb-1">题目编号</label>
            <input
              value={problemCode}
              onChange={(e) => setProblemCode(e.target.value)}
              placeholder="如 1、实验报告-1"
              className="w-full px-3 py-2 rounded border border-slate-300 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-600 mb-1">题目文本（可选）</label>
            <input
              value={problemStatement}
              onChange={(e) => setProblemStatement(e.target.value)}
              placeholder="题目描述，会带入 prompt"
              className="w-full px-3 py-2 rounded border border-slate-300 text-sm"
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="text-sm text-slate-600 mb-2">
          选择 .mdj 文件（支持多选；文件名前缀数字会作为学号）
        </div>
        <input
          type="file"
          multiple
          accept=".mdj,application/json"
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
          className="block text-sm mb-4"
        />
        <button
          disabled={!classId || !files.length || uploadMut.isPending}
          onClick={() => uploadMut.mutate()}
          className="px-4 py-2 bg-brand-600 text-white rounded text-sm hover:bg-brand-700 disabled:opacity-60 flex items-center gap-2"
        >
          <UploadIcon size={14} />
          {uploadMut.isPending ? `上传中… ${results.length}/${files.length}` : `开始上传 (${files.length})`}
        </button>

        {results.length > 0 && (
          <ul className="mt-4 space-y-1">
            {results.map((r, i) => (
              <li key={i} className="text-sm flex items-start gap-2">
                {r.ok ? (
                  <CheckCircle2 size={14} className="text-green-600 mt-0.5" />
                ) : (
                  <AlertCircle size={14} className="text-red-600 mt-0.5" />
                )}
                <span className="font-mono text-xs text-slate-500">{r.name}</span>
                <span className={r.ok ? "text-slate-600" : "text-red-600"}>
                  {r.message}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
