import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { importStudents, type ImportResult } from "@/lib/api";
import { Upload as UploadIcon, CheckCircle2, AlertCircle, Users } from "lucide-react";

export default function AdminImport() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  const mut = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("请选择 xlsx 文件");
      return importStudents(file);
    },
    onSuccess: (data) => setResult(data),
    onError: (e: any) => {
      setResult(null);
      alert(e?.response?.data?.detail || e?.message || "导入失败");
    },
  });

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4 flex items-center gap-2">
        <Users size={20} /> 批量导入学生账号
      </h1>

      <div className="bg-white rounded-lg border border-slate-200 p-5 mb-4 space-y-4">
        <div className="text-sm text-slate-600 space-y-1">
          <p>上传 <strong>.xlsx</strong> 文件，格式如下（第一行为表头）：</p>
          <table className="mt-2 text-xs border border-slate-200 rounded">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-1.5 text-left border-r border-slate-200">班级</th>
                <th className="px-3 py-1.5 text-left border-r border-slate-200">学号</th>
                <th className="px-3 py-1.5 text-left">姓名</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-3 py-1 border-r border-t border-slate-200">12401</td>
                <td className="px-3 py-1 border-r border-t border-slate-200">2024001</td>
                <td className="px-3 py-1 border-t border-slate-200">张三</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-2 text-slate-500">
            用户名 = 学号，默认密码 = 学号 + "123"，学生可自行修改密码。
            <br />班级不存在时会自动创建。
          </p>
        </div>

        <div>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }}
            className="block text-sm"
          />
        </div>

        <button
          disabled={!file || mut.isPending}
          onClick={() => mut.mutate()}
          className="px-4 py-2 bg-brand-600 text-white rounded text-sm hover:bg-brand-700 disabled:opacity-60 flex items-center gap-2"
        >
          <UploadIcon size={14} />
          {mut.isPending ? "导入中…" : "开始导入"}
        </button>

        {result && (
          <div className="space-y-3">
            <div className="flex gap-4 text-sm">
              <span className="text-green-700">创建 {result.created}</span>
              <span className="text-slate-500">跳过 {result.skipped}</span>
              <span className="text-red-600">错误 {result.errors}</span>
              <span className="text-slate-400">共 {result.total} 行</span>
            </div>

            <div className="max-h-80 overflow-auto border border-slate-200 rounded">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 sticky top-0">
                  <tr>
                    <th className="px-2 py-1.5 text-left">班级</th>
                    <th className="px-2 py-1.5 text-left">学号</th>
                    <th className="px-2 py-1.5 text-left">姓名</th>
                    <th className="px-2 py-1.5 text-left">结果</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="px-2 py-1">{r.class_code}</td>
                      <td className="px-2 py-1">{r.username}</td>
                      <td className="px-2 py-1">{r.display_name}</td>
                      <td className="px-2 py-1">
                        {r.status === "created" && (
                          <span className="text-green-600 flex items-center gap-1">
                            <CheckCircle2 size={12} /> 已创建
                          </span>
                        )}
                        {r.status === "exists" && (
                          <span className="text-slate-500">已存在</span>
                        )}
                        {r.status === "error" && (
                          <span className="text-red-600 flex items-center gap-1">
                            <AlertCircle size={12} /> {r.message}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
