import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiLogin, apiMe } from "@/lib/api";
import { useAuth } from "@/store/auth";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setAuth = useAuth((s) => s.setAuth);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      const t = await apiLogin(username, password);
      // 先 setAuth 让 token 生效，再取 me
      useAuth.getState().setAuth(t.access_token, {
        id: 0, username, display_name: username, role: "", class_id: null, experiment_group: null, session_group: null,
      });
      const me = await apiMe();
      setAuth(t.access_token, me);
      navigate("/");
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form
        onSubmit={submit}
        className="w-96 bg-white rounded-xl shadow-sm border border-slate-200 p-6"
      >
        <div className="text-xl font-semibold text-brand-600 mb-1">ASSESS工具-UML批阅助手</div>
        <div className="text-sm text-slate-500 mb-5">使用账号登录</div>

        <label className="block text-xs text-slate-600 mb-1">用户名</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full mb-3 px-3 py-2 rounded border border-slate-300 text-sm"
          placeholder="admin"
        />

        <label className="block text-xs text-slate-600 mb-1">密码</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full mb-3 px-3 py-2 rounded border border-slate-300 text-sm"
          placeholder="至少 6 位"
        />

        {err && (
          <div className="text-sm text-red-600 bg-red-50 rounded px-3 py-2 mb-3">{err}</div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-brand-600 hover:bg-brand-700 text-white text-sm py-2 rounded disabled:opacity-60"
        >
          {loading ? "处理中…" : "登录"}
        </button>

      </form>
    </div>
  );
} 
