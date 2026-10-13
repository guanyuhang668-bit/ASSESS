import axios from "axios";
import { useAuth } from "@/store/auth";

// ---- axios 实例 ----
export const api = axios.create({
  baseURL: "/api",
  timeout: 300_000,
});

api.interceptors.request.use((cfg) => {
  const token = useAuth.getState().token;
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      useAuth.getState().clear();
      if (location.pathname !== "/login") location.href = "/login";
    }
    return Promise.reject(err);
  },
);

// ---- 类型 ----
export interface SchoolClass { id: number; code: string; name: string }
export interface Student { id: number; class_id: number; student_code: string; name: string }
export interface GradingStatusItem {
  model_key: string; status: string; score: number;
}
export interface CriterionScoreOut {
  code: string; name: string; score: number; max_score: number; reasoning: string;
}
export interface GradingFeedbackOut {
  model_key: string; status: string;
  total_score: number; max_total_score: number; normalized_score: number;
  overall_comment: string; criteria: CriterionScoreOut[];
}
export interface Submission {
  id: number; student_id: number; student_code: string; student_name: string;
  diagram_type: string; problem_code: string;
  problem_statement: string; original_filename: string; image_filename: string;
  source_format: string;
  element_count: number; relation_count: number; container_count: number;
  parse_error: string; created_at: string;
  grading_status: GradingStatusItem[];
  grading_feedback: GradingFeedbackOut | null;
}
export interface SubmissionDetail extends Submission { ir_textual: string }
export interface RubricVersion {
  id: number; diagram_type: string; name: string; is_active: boolean;
  description: string; source_file: string;
}
export interface Criterion {
  id: number; code: string; parent_code: string; parent_name: string;
  name: string; description: string; weight: number; max_score: number;
  order_index: number; error_freq_total: number; common_errors: string[];
  scoring_hint: string; not_applicable_when: string;
}
export interface RubricDetail extends RubricVersion { criteria: Criterion[] }

export type GradingRunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type GradingResultStatus = "pending" | "running" | "success" | "failed";

export interface GradingRun {
  id: number; name: string; description: string; status: GradingRunStatus;
  model_keys: string[]; rubric_version_ids: number[]; submission_ids: number[];
  total_tasks: number; completed_tasks: number; failed_tasks: number;
  started_at: string | null; finished_at: string | null; error: string;
  created_at: string;
}

export interface Issue {
  id: number; element_refs: string[]; description: string;
  severity: string; suggestion: string;
}
export interface CriterionScore {
  id: number; code: string; score: number; max_score: number;
  not_applicable: boolean; reasoning: string; issues: Issue[];
}
export interface GradingResult {
  id: number; run_id: number; submission_id: number; rubric_version_id: number;
  model_key: string; status: GradingResultStatus;
  total_score: number; max_total_score: number; normalized_score: number;
  overall_comment: string; prompt_tokens: number; completion_tokens: number;
  elapsed_seconds: number; error: string;
  started_at: string | null; finished_at: string | null;
  criterion_scores: CriterionScore[];
}

export interface GradingProgress {
  run_id: number; status: GradingRunStatus;
  total: number; completed: number; failed: number;
  running: number; pending: number;
  per_model: Record<string, Record<string, number>>;
}

export interface TeacherIssueIn {
  element_refs: string[]; description: string; severity: string;
}
export interface TeacherScoreIn {
  submission_id: number; code: string; score: number;
  max_score?: number; not_applicable?: boolean; comment?: string;
  issues?: TeacherIssueIn[];
}
export interface TeacherScore {
  id: number; submission_id: number; teacher_id: number; code: string;
  score: number; max_score: number; not_applicable: boolean; comment: string;
  issues: (TeacherIssueIn & { id: number })[];
}

export interface ModelAgreementRow {
  model_key: string; submissions_graded: number;
  mae_vs_teacher: number | null; rho_vs_teacher: number | null;
  icc_vs_teacher: number | null;
  precision: number | null; recall: number | null; f1: number | null;
  avg_tokens: number; avg_seconds: number;
}
export interface AnalysisSummary {
  run_id: number; rows: ModelAgreementRow[]; n_teacher_labelled: number;
}

// ---- auth ----
export async function apiLogin(username: string, password: string) {
  const { data } = await api.post("/auth/login", { username, password });
  return data as { access_token: string; token_type: string; expires_in_min: number };
}
export async function apiRegister(
  username: string, password: string, display_name: string, role: string,
) {
  const { data } = await api.post("/auth/register", { username, password, display_name, role });
  return data;
}
export async function apiMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

// ---- admin ----
export interface ImportRowResult {
  username: string; display_name: string; class_code: string;
  status: "created" | "exists" | "error"; message: string;
}
export interface ImportResult {
  total: number; created: number; skipped: number; errors: number;
  rows: ImportRowResult[];
}
export async function importStudents(file: File) {
  const fd = new FormData();
  fd.set("file", file);
  const { data } = await api.post<ImportResult>("/admin/import-students", fd);
  return data;
}
export interface UmlArtifactsExportParams {
  class_id?: number;
  class_code?: string;
  experiment_group?: string;
  session_group?: string;
  cohort_group?: string;
  diagram_type?: string;
  user_id?: number;
}
export async function downloadUmlArtifacts(params?: UmlArtifactsExportParams) {
  const response = await api.get<Blob>("/admin/export-uml-artifacts", {
    params,
    responseType: "blob",
    timeout: 600_000,
  });
  const disposition = response.headers["content-disposition"] as string | undefined;
  let filename = "uml_artifacts.zip";
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/)?.[1];
  const plain = disposition?.match(/filename="?([^"]+)"?/)?.[1];
  if (encoded) {
    filename = decodeURIComponent(encoded);
  } else if (plain) {
    filename = plain;
  }
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

// ---- password ----
export async function changePassword(old_password: string, new_password: string) {
  const { data } = await api.put("/auth/password", { old_password, new_password });
  return data as { ok: boolean; message: string };
}

// ---- submissions ----
export async function listClasses() {
  const { data } = await api.get<SchoolClass[]>("/submissions/classes");
  return data;
}
export async function createClass(code: string, name: string) {
  const fd = new FormData();
  fd.set("code", code); fd.set("name", name);
  const { data } = await api.post<SchoolClass>("/submissions/classes", fd);
  return data;
}
export async function uploadSubmission(args: {
  file: File; class_id: number; student_code: string; student_name?: string;
  diagram_type: string; problem_code?: string; problem_statement?: string;
}) {
  const fd = new FormData();
  fd.set("file", args.file);
  fd.set("class_id", String(args.class_id));
  fd.set("student_code", args.student_code);
  fd.set("student_name", args.student_name ?? "");
  fd.set("diagram_type", args.diagram_type);
  fd.set("problem_code", args.problem_code ?? "");
  fd.set("problem_statement", args.problem_statement ?? "");
  const { data } = await api.post<Submission>("/submissions/upload", fd);
  return data;
}
export async function studentUpload(args: {
  file: File; image: File;
  diagram_type: string; problem_code?: string; problem_statement?: string;
}) {
  const fd = new FormData();
  fd.set("file", args.file);
  fd.set("image", args.image);
  fd.set("diagram_type", args.diagram_type);
  fd.set("problem_code", args.problem_code ?? "");
  fd.set("problem_statement", args.problem_statement ?? "");
  const { data } = await api.post<Submission>("/submissions/student-upload", fd);
  return data;
}
// 学生查看自己的提交历史
export interface MySubmissionCriterion {
  code: string;
  score: number;
  max_score: number;
  reasoning: string;
}
export interface MySubmissionFeedback {
  normalized_score: number;
  overall_comment: string;
  criteria: MySubmissionCriterion[];
}
export interface MySubmission {
  id: number;
  diagram_type: string;
  problem_code: string;
  problem_statement: string;
  original_filename: string;
  image_filename: string;
  element_count: number;
  relation_count: number;
  parse_error: string;
  best_score: number | null;
  grading_feedback: MySubmissionFeedback | null;
  created_at: string;
}
export async function listMySubmissions() {
  const { data } = await api.get<MySubmission[]>("/submissions/my-submissions");
  return data;
}

export async function listSubmissions(
  params: { class_id?: number; diagram_type?: string; page?: number; page_size?: number },
) {
  const { data } = await api.get<{ meta: { total: number; page: number; page_size: number }; items: Submission[] }>(
    "/submissions", { params },
  );
  return data;
}
export async function getSubmission(id: number) {
  const { data } = await api.get<SubmissionDetail>(`/submissions/${id}`);
  return data;
}

// ---- rubrics ----
export async function listRubricVersions(diagram_type?: string) {
  const { data } = await api.get<RubricVersion[]>("/rubrics/versions", { params: { diagram_type } });
  return data;
}
export async function getRubricDetail(id: number) {
  const { data } = await api.get<RubricDetail>(`/rubrics/versions/${id}`);
  return data;
}
export async function importRubric(body: {
  diagram_type: string; yaml_filename: string; name: string; activate: boolean;
}) {
  const { data } = await api.post<RubricDetail>("/rubrics/import", body);
  return data;
}
export async function activateRubric(id: number) {
  const { data } = await api.post(`/rubrics/versions/${id}/activate`);
  return data;
}

// ---- grading ----
export async function listModels() {
  const { data } = await api.get<string[]>("/grading/models");
  return data;
}
export async function createGradingRun(body: {
  name: string; description?: string; submission_ids: number[];
  model_keys: string[]; rubric_version_ids?: number[];
}) {
  const { data } = await api.post<GradingRun>("/grading/runs", body);
  return data;
}
export async function listGradingRuns() {
  const { data } = await api.get<GradingRun[]>("/grading/runs");
  return data;
}
export async function getGradingRun(id: number) {
  const { data } = await api.get<GradingRun>(`/grading/runs/${id}`);
  return data;
}
export async function getGradingProgress(id: number) {
  const { data } = await api.get<GradingProgress>(`/grading/runs/${id}/progress`);
  return data;
}
export async function listRunResults(id: number) {
  const { data } = await api.get<GradingResult[]>(`/grading/runs/${id}/results`);
  return data;
}
export async function getGradingResult(id: number) {
  const { data } = await api.get<GradingResult>(`/grading/results/${id}`);
  return data;
}
export async function resultsBySubmission(submission_id: number, run_id?: number) {
  const { data } = await api.get<GradingResult[]>(
    `/grading/results/by-submission/${submission_id}`, { params: { run_id } },
  );
  return data;
}
export async function cancelRun(id: number) {
  const { data } = await api.post(`/grading/runs/${id}/cancel`);
  return data;
}

// ---- teacher ----
export async function upsertTeacherScore(body: TeacherScoreIn) {
  const { data } = await api.post<TeacherScore>("/teacher/scores", body);
  return data;
}
export async function listTeacherScores(submission_id: number) {
  const { data } = await api.get<TeacherScore[]>(`/teacher/scores/${submission_id}`);
  return data;
}

// ---- analysis ----
export async function runSummary(run_id: number) {
  const { data } = await api.get<AnalysisSummary>(`/analysis/runs/${run_id}/summary`);
  return data;
}

// ---- admin: experiment group ----
export interface GroupSummaryItem {
  group: string;
  count: number;
}
export interface AssignGroupResult {
  class_code: string;
  experiment_group: string;
  updated: number;
}
export async function getGroupsSummary() {
  const { data } = await api.get<{ groups: GroupSummaryItem[] }>("/admin/groups-summary");
  return data.groups;
}
export async function assignGroup(class_code: string, experiment_group: string) {
  const { data } = await api.post<AssignGroupResult>("/admin/assign-group", {
    class_code, experiment_group,
  });
  return data;
}

// ---- admin: session group (当次实验使用的 Agent) ----
export interface AssignSessionGroupBody {
  scope: "all" | "class" | "users";
  class_code?: string;
  user_ids?: number[];
  session_group: string; // agent_a | agent_b | agent_c | control | ""(清空)
}
export interface AssignSessionGroupResult {
  scope: string;
  session_group: string | null;
  updated: number;
}
export async function assignSessionGroup(body: AssignSessionGroupBody) {
  const { data } = await api.post<AssignSessionGroupResult>(
    "/admin/assign-session-group", body,
  );
  return data;
}

// ---- admin: group members ----
export interface GroupMember {
  id: number;
  username: string;
  display_name: string;
  class_code: string;
  class_name: string;
  session_count: number;
  best_score: number | null;
  last_active: string | null;
}
export async function getGroupsMembers() {
  const { data } = await api.get<{ groups: Record<string, GroupMember[]> }>("/admin/groups-members");
  return data.groups;
}

// ---- admin: chat sessions ----
export interface AdminChatSession {
  id: number; user_id: number; username: string; display_name: string;
  experiment_group: string; session_group?: string; class_code?: string; diagram_type: string;
  problem_code: string; problem_statement: string;
  status: string; round_number: number; latest_score: number | null;
  passed: boolean; teacher_scored_count: number;
  created_at: string; updated_at: string;
}
export interface AdminChatSessionDetail extends AdminChatSession {
  messages: ChatMessageItem[];
}
export async function adminListChatSessions(params?: {
  experiment_group?: string;
  session_group?: string;
  class_id?: number;
  class_code?: string;
  diagram_type?: string;
  user_id?: number;
}) {
  const { data } = await api.get<AdminChatSession[]>("/admin/chat-sessions", { params });
  return data;
}
export async function adminGetChatSession(id: number) {
  const { data } = await api.get<AdminChatSessionDetail>(`/admin/chat-sessions/${id}`);
  return data;
}

// ---- admin: chat teacher scores ----
export interface ChatTeacherIssueIn {
  element_refs: string[]; description: string; severity: string;
}
export interface ChatTeacherScoreIn {
  session_id: number; code: string; score: number;
  max_score?: number; not_applicable?: boolean; comment?: string;
  issues?: ChatTeacherIssueIn[];
}
export interface ChatTeacherIssueOut {
  id: number; element_refs: string[]; description: string; severity: string;
}
export interface ChatTeacherScore {
  id: number; session_id: number; teacher_id: number; code: string;
  score: number; max_score: number; not_applicable: boolean; comment: string;
  issues: ChatTeacherIssueOut[];
}
export async function upsertChatTeacherScore(body: ChatTeacherScoreIn) {
  const { data } = await api.post<ChatTeacherScore>(
    `/admin/chat-sessions/${body.session_id}/scores`, body,
  );
  return data;
}
export async function listChatTeacherScores(sessionId: number) {
  const { data } = await api.get<ChatTeacherScore[]>(
    `/admin/chat-sessions/${sessionId}/scores`,
  );
  return data;
}
export async function studentListTeacherScores(sessionId: number) {
  const { data } = await api.get<ChatTeacherScore[]>(
    `/chat/sessions/${sessionId}/scores`,
  );
  return data;
}

// ---- admin: student management ----
export interface AdminStudent {
  id: number;
  username: string;
  display_name: string;
  class_code: string | null;
  class_name: string | null;
  experiment_group: string | null;
  cohort_group: string | null;
  problem_order: string | null;
  session_group: string | null;
  is_active: boolean;
  session_count: number;
  best_score: number | null;
}
export interface StudentUpdateBody {
  display_name?: string;
  experiment_group?: string;
  cohort_group?: string;
  problem_order?: string;
  session_group?: string;
  is_active?: boolean;
}
export async function listStudents(params?: { search?: string; class_code?: string; experiment_group?: string }) {
  const { data } = await api.get<AdminStudent[]>("/admin/students", { params });
  return data;
}
export async function updateStudent(userId: number, body: StudentUpdateBody) {
  const { data } = await api.put<AdminStudent>(`/admin/students/${userId}`, body);
  return data;
}
export async function resetStudentPassword(userId: number) {
  const { data } = await api.post<{ ok: boolean; message: string }>(`/admin/students/${userId}/reset-password`);
  return data;
}
export async function deleteStudent(userId: number) {
  const { data } = await api.delete<{ ok: boolean; message: string }>(`/admin/students/${userId}`);
  return data;
}

// ---- chat (Part 2) ----
export interface ChatSessionItem {
  id: number; user_id: number; experiment_group: string;
  diagram_type: string; problem_code: string; problem_statement: string;
  status: string; round_number: number; latest_score: number | null;
  passed: boolean; created_at: string; updated_at: string;
}
export interface ChatMessageItem {
  id: number; session_id: number; role: string; content: string;
  mdj_filename: string | null; image_filename: string | null;
  image_url: string | null; score_snapshot: number | null;
  model_results?: ChatModelResult[];
  created_at: string;
}
export interface ChatModelCriterionScore {
  id: number; code: string; score: number; max_score: number;
  not_applicable: boolean; has_issue: boolean; brief: string; reasoning: string;
}
export interface ChatModelResult {
  id: number; model_key: string; status: string;
  total_score: number | null; max_total_score: number;
  normalized_score: number | null; overall_comment: string; raw_response: string;
  error: string; prompt_tokens: number; completion_tokens: number;
  elapsed_seconds: number; criterion_scores: ChatModelCriterionScore[];
}
export interface ChatSessionDetail extends ChatSessionItem {
  messages: ChatMessageItem[];
  ability_profile?: Record<string, number | null>;
}
export interface SendMessageResult {
  user_message: ChatMessageItem;
  assistant_message: ChatMessageItem;
  session: ChatSessionItem;
}

export async function listChatSessions() {
  const { data } = await api.get<ChatSessionItem[]>("/chat/sessions");
  return data;
}
export async function getChatSession(id: number) {
  const { data } = await api.get<ChatSessionDetail>(`/chat/sessions/${id}`);
  return data;
}
export async function sendChatMessage(args: {
  content?: string;
  diagram_type?: string;
  problem_code?: string;
  problem_statement?: string;
  session_id?: number | null;
  mdj_file?: File | null;
  image?: File | null;
}) {
  const fd = new FormData();
  if (args.content) fd.set("content", args.content);
  if (args.diagram_type) fd.set("diagram_type", args.diagram_type);
  if (args.problem_code) fd.set("problem_code", args.problem_code);
  if (args.problem_statement) fd.set("problem_statement", args.problem_statement);
  if (args.session_id) fd.set("session_id", String(args.session_id));
  if (args.mdj_file) fd.set("mdj_file", args.mdj_file);
  if (args.image) fd.set("image", args.image);
  const { data } = await api.post<SendMessageResult>("/chat/send", fd, { timeout: 120_000 });
  return data;
}
export async function getChatImageUrl(objectKey: string) {
  const { data } = await api.get<{ url: string }>("/chat/image-url", { params: { object_key: objectKey } });
  return data.url;
}

// ---- activity (使用时长) ----
export async function sendHeartbeat(page: string, chatSessionId?: number | null) {
  await api.post("/activity/heartbeat", {
    page,
    chat_session_id: chatSessionId ?? null,
  });
}
export interface MyActivitySummary {
  total_seconds: number;
  today_seconds: number;
  by_session: {
    session_id: number;
    diagram_type: string;
    problem_code: string;
    active_seconds: number;
    status: string;
    latest_score: number | null;
  }[];
}
export async function getMyActivity() {
  const { data } = await api.get<MyActivitySummary>("/activity/me");
  return data;
}
export interface AdminActivityItem {
  user_id: number;
  username: string;
  display_name: string;
  class_code: string | null;
  experiment_group: string | null;
  total_seconds: number;
  heartbeat_seconds: number;
  reconstructed_seconds: number;
  session_count: number;
  by_session?: {
    session_id: number;
    diagram_type: string;
    problem_code: string;
    active_seconds: number;
    status: string;
    latest_score: number | null;
  }[] | null;
}
export async function getAdminActivity(params?: { class_code?: string; search?: string }) {
  const { data } = await api.get<AdminActivityItem[]>("/activity/admin", { params });
  return data;
}
export async function getAdminUserActivity(userId: number) {
  const { data } = await api.get<AdminActivityItem>(`/activity/admin/${userId}`);
  return data;
}
export async function downloadAdminActivityXlsx(params?: { class_code?: string; search?: string }) {
  const response = await api.get<Blob>("/activity/admin/export", {
    params,
    responseType: "blob",
  });
  const disposition = response.headers["content-disposition"] as string | undefined;
  let filename = "使用时长.xlsx";
  const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/)?.[1];
  const plain = disposition?.match(/filename="?([^"]+)"?/)?.[1];
  if (encoded) {
    filename = decodeURIComponent(encoded);
  } else if (plain) {
    filename = plain;
  }
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

// ---- ws ----
export function openProgressWs(run_id: number, onMsg: (snap: GradingProgress) => void) {
  const token = useAuth.getState().token;
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/runs/${run_id}${q}`);
  ws.onmessage = (e) => {
    try { onMsg(JSON.parse(e.data)); } catch { /* ignore */ }
  };
  return ws;
}
