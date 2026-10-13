import { useEffect, useRef } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/store/auth";
import { useActivityStore } from "@/store/activity";
import { sendHeartbeat } from "@/lib/api";
import {
  LayoutDashboard, Upload as UploadIcon, ListChecks, Play,
  GraduationCap, BarChart3, LogOut, Users, KeyRound, MessageSquare, FlaskConical,
  UserCog, History, Clock,
} from "lucide-react";
import { clsx } from "clsx";

const teacherItems = [
  { to: "/", label: "学生作品", icon: LayoutDashboard },
  { to: "/admin/chat-sessions", label: "聊天记录", icon: MessageSquare },
  { to: "/admin/activity", label: "使用时长", icon: Clock },
  { to: "/rubrics", label: "评分标准", icon: ListChecks },
  { to: "/admin/import", label: "导入学生", icon: Users },
  { to: "/admin/groups", label: "实验分组", icon: FlaskConical },
  { to: "/admin/students", label: "学生管理", icon: UserCog },
];

const studentItems = [
  { to: "/", label: "AI 助手", icon: MessageSquare },
  { to: "/student-upload", label: "UML图批阅", icon: UploadIcon },
  { to: "/history", label: "提交历史", icon: History },
  { to: "/password", label: "账户管理", icon: KeyRound },
];

const multiModelStudentItems = [
  { to: "/", label: "AI 助手", icon: MessageSquare },
  { to: "/password", label: "账户管理", icon: KeyRound },
];

export default function Layout() {
  const { user, clear } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 学生端心跳：每 30s 上报一次（仅在页面可见时）
  const currentChatSessionId = useActivityStore((s) => s.currentChatSessionId);

  useEffect(() => {
    if (user?.role !== "student") return;

    const tick = () => {
      if (document.visibilityState !== "visible") return;
      sendHeartbeat(location.pathname, currentChatSessionId).catch(() => {});
    };
    tick(); // 立即发送一次
    intervalRef.current = setInterval(tick, 30_000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [user?.role, location.pathname, currentChatSessionId]);

  function logout() {
    clear();
    navigate("/login");
  }

  const studentNavItems = (user?.session_group || user?.experiment_group) === "multi_model_a"
    ? multiModelStudentItems
    : studentItems;
  const items = user?.role === "student" ? studentNavItems : teacherItems;

  return (
    <div className="min-h-screen flex bg-slate-50">
      <aside className="w-56 bg-white border-r border-slate-200 flex flex-col">
        <div className="px-6 py-5 border-b border-slate-200">
          <Link to="/" className="text-lg font-semibold text-brand-600">
            ASSESS工具-UML批阅助手
          </Link>
          <div className="text-xs text-slate-500 mt-1">v0.2 · 研究版</div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  isActive
                    ? "bg-brand-50 text-brand-700 font-medium"
                    : "text-slate-600 hover:bg-slate-100",
                )
              }
            >
              <it.icon size={16} /> {it.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-200 text-sm">
          <div className="flex items-center gap-2 text-slate-700">
            <GraduationCap size={16} />
            <span className="flex-1 truncate">{user?.display_name || user?.username}</span>
            <span className="px-1.5 py-0.5 bg-slate-100 rounded text-xs">
              {user?.role}
            </span>
          </div>
          <button
            onClick={logout}
            className="mt-3 w-full flex items-center justify-center gap-2 text-xs text-slate-500 hover:text-red-600"
          >
            <LogOut size={14} /> 退出登录
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
