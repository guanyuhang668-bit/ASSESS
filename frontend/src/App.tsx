import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import StudentUpload from "@/pages/StudentUpload";
import StudentChat from "@/pages/StudentChat";
import ResultCompare from "@/pages/ResultCompare";
import TeacherLabel from "@/pages/TeacherLabel";
import Rubrics from "@/pages/Rubrics";
import AdminImport from "@/pages/AdminImport";
import GroupManage from "@/pages/GroupManage";
import StudentManage from "@/pages/StudentManage";
import StudentHistory from "@/pages/StudentHistory";
import AdminChatSessions from "@/pages/AdminChatSessions";
import AdminActivity from "@/pages/AdminActivity";
import ChangePassword from "@/pages/ChangePassword";
import { useAuth } from "@/store/auth";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireRole({ allowed, children }: { allowed: string[]; children: ReactNode }) {
  const user = useAuth((s) => s.user);
  if (!user || !allowed.includes(user.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function BlockMultiModelStudent({ children }: { children: ReactNode }) {
  const user = useAuth((s) => s.user);
  const group = user?.session_group || user?.experiment_group;
  if (user?.role === "student" && group === "multi_model_a") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  const user = useAuth((s) => s.user);
  const isStudent = user?.role === "student";

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        {isStudent ? (
          <>
            <Route index element={<StudentChat />} />
            <Route path="/chat" element={<StudentChat />} />
            <Route path="/student-upload" element={<BlockMultiModelStudent><StudentUpload /></BlockMultiModelStudent>} />
            <Route path="/history" element={<BlockMultiModelStudent><StudentHistory /></BlockMultiModelStudent>} />
            <Route path="/password" element={<ChangePassword />} />
          </>
        ) : (
          <>
            <Route index element={<Dashboard />} />
            <Route path="/rubrics" element={<Rubrics />} />
            <Route path="/compare/:submissionId" element={<ResultCompare />} />
            <Route path="/teacher/:submissionId" element={<TeacherLabel />} />
            <Route path="/admin/import" element={<AdminImport />} />
            <Route path="/admin/groups" element={<GroupManage />} />
            <Route path="/admin/students" element={<StudentManage />} />
            <Route path="/admin/chat-sessions" element={<AdminChatSessions />} />
            <Route path="/admin/activity" element={<AdminActivity />} />
            <Route path="/password" element={<ChangePassword />} />
          </>
        )}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
