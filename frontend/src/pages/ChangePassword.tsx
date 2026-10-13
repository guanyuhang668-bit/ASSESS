import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { changePassword } from "@/lib/api";
import { KeyRound, CheckCircle2, AlertCircle } from "lucide-react";

export default function ChangePassword() {
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const mut = useMutation({
    mutationFn: async () => {
      if (!oldPwd) throw new Error("请输入原密码");
      if (newPwd.length < 6) throw new Error("新密码至少 6 位");
      if (newPwd !== confirmPwd) throw new Error("两次输入的新密码不一致");
      return changePassword(oldPwd, newPwd);
    },
    onSuccess: (data) => {
      setResult({ ok: true, message: data.message });
      setOldPwd("");
      setNewPwd("");
      setConfirmPwd("");
    },
    onError: (e: any) => {
      setResult({
        ok: false,
        message: e?.response?.data?.detail || e?.message || "修改失败",
      });
    },
  });

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-800 mb-4 flex items-center gap-2">
        <KeyRound size={20} /> 修改密码
      </h1>

      <div className="bg-white rounded-lg border border-slate-200 p-5 max-w-md space-y-4">
        <div>
          <label className="block text-xs text-slate-600 mb-1">原密码</label>
          <input
            type="password"
            value={oldPwd}
            onChange={(e) => setOldPwd(e.target.value)}
            className="w-full px-3 py-2 rounded border border-slate-300 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-600 mb-1">新密码（至少 6 位）</label>
          <input
            type="password"
            value={newPwd}
            onChange={(e) => setNewPwd(e.target.value)}
            className="w-full px-3 py-2 rounded border border-slate-300 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-600 mb-1">确认新密码</label>
          <input
            type="password"
            value={confirmPwd}
            onChange={(e) => setConfirmPwd(e.target.value)}
            className="w-full px-3 py-2 rounded border border-slate-300 text-sm"
          />
        </div>

        <button
          disabled={mut.isPending}
          onClick={() => mut.mutate()}
          className="px-4 py-2 bg-brand-600 text-white rounded text-sm hover:bg-brand-700 disabled:opacity-60"
        >
          {mut.isPending ? "提交中…" : "确认修改"}
        </button>

        {result && (
          <div className={`flex items-start gap-2 text-sm p-3 rounded ${result.ok ? "bg-green-50" : "bg-red-50"}`}>
            {result.ok ? (
              <CheckCircle2 size={16} className="text-green-600 mt-0.5" />
            ) : (
              <AlertCircle size={16} className="text-red-600 mt-0.5" />
            )}
            <span className={result.ok ? "text-green-700" : "text-red-700"}>
              {result.message}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
