import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listChatSessions,
  getChatSession,
  sendChatMessage,
  type ChatSessionItem,
  type ChatMessageItem,
} from "@/lib/api";
import { useAuth } from "@/store/auth";
import { useActivityStore } from "@/store/activity";
import {
  Send,
  ImageIcon,
  FileJson,
  Plus,
  MessageSquare,
  CheckCircle2,
  Loader2,
  X,
  Bot,
  User as UserIcon,
  AlertCircle,
} from "lucide-react";
import { clsx } from "clsx";
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";

const DIAGRAM_TYPES = [
  { value: "use_case", label: "用例图" },
  { value: "class", label: "类图" },
  { value: "sequence", label: "时序图" },
  { value: "swimlane", label: "泳道图" },
];

const GROUP_LABELS: Record<string, string> = {
  agent_a: "Agent A（单次反馈）",
  agent_b: "Agent B（多轮引导）",
  agent_c: "Agent C（渐进式）",
  control: "对照组（教师）",
  multi_model_a: "四模型 Agent A",
};

const MODEL_LABELS: Record<string, string> = {
  gpt4o: "GPT-4o",
  deepseek_v3: "DeepSeek V3",
  gemini_3_flash: "Gemini 3 Flash",
  qwen_3_max: "Qwen 3 Max",
};

const ABILITY_DIMENSIONS = [
  "需求语义理解",
  "建模元素识别",
  "关系语义表达",
  "动态流程逻辑",
  "UML规范表达",
  "抽象粒度控制",
  "命名语义清晰",
  "结构完整闭环",
];

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function StudentChat() {
  const user = useAuth((s) => s.user);
  const queryClient = useQueryClient();
  const group = user?.session_group || user?.experiment_group;

  // ---- 会话列表 ----
  const sessionsQ = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: listChatSessions,
  });

  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [abilityProfile, setAbilityProfile] = useState<Record<string, number | null> | null>(null);
  const setCurrentChatSessionId = useActivityStore((s) => s.setCurrentChatSessionId);

  // 同步 activeSessionId 到全局 activity store（供心跳上报用）
  useEffect(() => {
    setCurrentChatSessionId(activeSessionId);
    return () => { setCurrentChatSessionId(null); };
  }, [activeSessionId, setCurrentChatSessionId]);

  // ---- 加载会话消息 ----
  const sessionDetailQ = useQuery({
    queryKey: ["chat-session", activeSessionId],
    queryFn: () => getChatSession(activeSessionId!),
    enabled: !!activeSessionId,
  });
  useEffect(() => {
    if (sessionDetailQ.data) {
      setMessages(sessionDetailQ.data.messages);
      setAbilityProfile(sessionDetailQ.data.ability_profile ?? null);
    } else {
      setAbilityProfile(null);
    }
  }, [sessionDetailQ.data]);

  // ---- 新建会话表单 ----
  const [showNewSession, setShowNewSession] = useState(false);
  const [newDiagramType, setNewDiagramType] = useState("use_case");
  const [newProblemCode, setNewProblemCode] = useState("");
  const [newProblemStatement, setNewProblemStatement] = useState("");

  // ---- 输入区 ----
  const [input, setInput] = useState("");
  const [mdjFile, setMdjFile] = useState<File | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [pendingUserMsg, setPendingUserMsg] = useState<{ content: string; mdj?: string; image?: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mdjInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自动滚到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pendingUserMsg]);

  // 自动调整 textarea 高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 150) + "px";
    }
  }, [input]);

  function handleImageSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] || null;
    setImageFile(f);
    if (f) {
      const reader = new FileReader();
      reader.onload = (ev) => setImagePreview(ev.target?.result as string);
      reader.readAsDataURL(f);
    } else {
      setImagePreview(null);
    }
  }

  // ---- 发送消息 ----
  const sendMut = useMutation({
    mutationFn: async (payload: {
      content: string; dt: string; mdjFile: File | null; imageFile: File | null;
      problemCode?: string; problemStatement?: string; sessionId: number | null;
    }) => {
      const result = await sendChatMessage({
        content: payload.content,
        diagram_type: payload.dt,
        problem_code: payload.sessionId ? undefined : payload.problemCode,
        problem_statement: payload.sessionId ? undefined : payload.problemStatement,
        session_id: payload.sessionId,
        mdj_file: payload.mdjFile,
        image: payload.imageFile,
      });
      return result;
    },
    onSuccess: (result) => {
      if (!result) return;
      setPendingUserMsg(null);
      // 追加真实消息
      setMessages((prev) => [...prev, result.user_message, result.assistant_message]);
      // 更新 session id
      if (!activeSessionId) {
        setActiveSessionId(result.session.id);
        setShowNewSession(false);
      }
      // 刷新会话列表
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
      queryClient.invalidateQueries({ queryKey: ["chat-session", result.session.id] });
    },
    onError: () => {
      setPendingUserMsg(null);
    },
  });

  const [validationError, setValidationError] = useState<string | null>(null);

  function handleSend() {
    if (sendMut.isPending) return;
    const trimmed = input.trim();
    if (!trimmed && !mdjFile && !imageFile) return;

    // 必须同时上传 mdj 和图片
    if (!mdjFile) {
      setValidationError("请上传 .mdj 文件（每次提交必须同时包含 mdj 文件和 UML 图截图）");
      return;
    }
    if (!imageFile) {
      setValidationError("请上传 UML 图截图（每次提交必须同时包含 mdj 文件和 UML 图截图）");
      return;
    }
    setValidationError(null);

    // 立即将用户消息显示到对话区
    const preview: { content: string; mdj?: string; image?: string } = {
      content: trimmed || (mdjFile ? `[上传文件] ${mdjFile.name}` : "") || (imageFile ? `[上传图片] ${imageFile.name}` : ""),
    };
    if (mdjFile) preview.mdj = mdjFile.name;
    if (imagePreview) preview.image = imagePreview;
    setPendingUserMsg(preview);

    // 已有会话时使用会话的 diagram_type，新建时使用表单选择
    const dt = activeSessionId
      ? currentSession?.diagram_type || newDiagramType
      : newDiagramType;

    // 发送请求（输入已清空，消息已显示在对话区）
    sendMut.mutate({
      content: trimmed,
      dt,
      mdjFile,
      imageFile,
      problemCode: newProblemCode,
      problemStatement: newProblemStatement,
      sessionId: activeSessionId,
    });

    // 立即清空输入区
    setInput("");
    setMdjFile(null);
    setImageFile(null);
    setImagePreview(null);
    if (mdjInputRef.current) mdjInputRef.current.value = "";
    if (imageInputRef.current) imageInputRef.current.value = "";
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function startNewSession() {
    setActiveSessionId(null);
    setMessages([]);
    setShowNewSession(true);
    setNewProblemCode("");
    setNewProblemStatement("");
  }

  // ---- 对照组提示 ----
  if (group === "control") {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-120px)]">
        <div className="text-center max-w-md">
          <Bot size={48} className="mx-auto text-slate-300 mb-4" />
          <h2 className="text-lg font-semibold text-slate-700 mb-2">对照组模式</h2>
          <p className="text-sm text-slate-500">
            你所在的组别由教师提供反馈。请按照教师的指导完成作业，
            无需使用 Agent 系统。如有疑问请联系教师。
          </p>
        </div>
      </div>
    );
  }

  if (!group) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-120px)]">
        <div className="text-center max-w-md">
          <Bot size={48} className="mx-auto text-slate-300 mb-4" />
          <h2 className="text-lg font-semibold text-slate-700 mb-2">尚未分配实验分组</h2>
          <p className="text-sm text-slate-500">请联系管理员为你分配实验分组后再使用。</p>
        </div>
      </div>
    );
  }

  const sessions = sessionsQ.data || [];
  const currentSession = sessions.find((s) => s.id === activeSessionId);
  const showAbilityProfile =
    group === "agent_c" &&
    !!abilityProfile &&
    ABILITY_DIMENSIONS.some((name) => Object.prototype.hasOwnProperty.call(abilityProfile, name));

  return (
    <div className="flex h-[calc(100vh-48px)] -m-6">
      {/* ---- 左侧会话列表 ---- */}
      <div className="w-72 bg-white border-r border-slate-200 flex flex-col">
        <div className="p-3 border-b border-slate-200">
          <button
            onClick={startNewSession}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition"
          >
            <Plus size={16} /> 新建对话
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => { setActiveSessionId(s.id); setShowNewSession(false); }}
              className={clsx(
                "w-full text-left px-3 py-3 border-b border-slate-100 hover:bg-slate-50 transition",
                activeSessionId === s.id && "bg-brand-50",
              )}
            >
              <div className="flex items-center gap-2">
                <MessageSquare size={14} className="text-slate-400 shrink-0" />
                <span className="text-sm font-medium text-slate-700 truncate">
                  {DIAGRAM_TYPES.find((d) => d.value === s.diagram_type)?.label || s.diagram_type}
                  {s.problem_code && ` · ${s.problem_code}`}
                </span>
                {s.passed && <CheckCircle2 size={14} className="text-green-500 shrink-0" />}
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-xs text-slate-400">{formatTime(s.created_at)}</span>
                {s.latest_score != null && (
                  <span className={clsx(
                    "text-xs font-medium px-1.5 py-0.5 rounded",
                    s.latest_score >= 80 ? "bg-green-100 text-green-700" :
                      s.latest_score >= 60 ? "bg-yellow-100 text-yellow-700" :
                        "bg-red-100 text-red-700",
                  )}>
                    {s.latest_score.toFixed(0)}分
                  </span>
                )}
              </div>
            </button>
          ))}
          {sessions.length === 0 && (
            <div className="p-4 text-center text-sm text-slate-400">
              暂无对话，点击上方按钮开始
            </div>
          )}
        </div>
        {/* 分组信息 */}
        <div className="p-3 border-t border-slate-200 bg-slate-50">
          <div className="text-xs text-slate-500">当前分组</div>
          <div className="text-sm font-medium text-brand-600">
            {GROUP_LABELS[group] || group}
          </div>
        </div>

        {/* UML 建模能力画像（仅 Agent C / 部分学生显示） */}
        {showAbilityProfile && abilityProfile && (
          <div className="px-4 pt-3 bg-slate-50 border-b border-slate-200">
            <AbilityProfileCard profile={abilityProfile} />
          </div>
        )}
      </div>

      {/* ---- 右侧聊天区 ---- */}
      <div className="flex-1 flex flex-col bg-slate-50">
        {/* 顶部信息栏 */}
        <div className="px-4 py-3 bg-white border-b border-slate-200 flex items-center justify-between">
          <div>
            {currentSession ? (
              <div className="flex items-center gap-3">
                <Bot size={20} className="text-brand-600" />
                <div>
                  <span className="text-sm font-medium text-slate-700">
                    UML 建模助手
                  </span>
                  <span className="text-xs text-slate-400 ml-2">
                    {DIAGRAM_TYPES.find((d) => d.value === currentSession.diagram_type)?.label}
                    {currentSession.problem_code && ` · 题目 ${currentSession.problem_code}`}
                    {` · 第 ${currentSession.round_number} 轮`}
                  </span>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Bot size={20} className="text-brand-600" />
                <span className="text-sm font-medium text-slate-700">UML 建模助手</span>
              </div>
            )}
          </div>
          {currentSession?.latest_score != null && (
            <div className={clsx(
              "text-sm font-semibold px-3 py-1 rounded-full",
              currentSession.passed ? "bg-green-100 text-green-700" :
                currentSession.latest_score >= 80 ? "bg-blue-100 text-blue-700" :
                  currentSession.latest_score >= 60 ? "bg-yellow-100 text-yellow-700" :
                    "bg-red-100 text-red-700",
            )}>
              当前评分: {currentSession.latest_score.toFixed(0)}/100
              {currentSession.passed ? " ✓ 已通过" :
                (group === "agent_b" || group === "agent_c") ? " · 继续修改" : ""}
            </div>
          )}
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {/* 新建会话表单 */}
          {showNewSession && !activeSessionId && (
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 max-w-lg mx-auto">
              <h3 className="text-sm font-semibold text-slate-700 mb-3">开始新的作业对话</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">图类型</label>
                  <select
                    value={newDiagramType}
                    onChange={(e) => setNewDiagramType(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
                  >
                    {DIAGRAM_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">题目编号</label>
                  <input
                    value={newProblemCode}
                    onChange={(e) => setNewProblemCode(e.target.value)}
                    placeholder="如 1、实验报告-1"
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">题目描述</label>
                  <textarea
                    value={newProblemStatement}
                    onChange={(e) => setNewProblemStatement(e.target.value)}
                    placeholder="请输入题目要求的描述..."
                    rows={3}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none resize-none"
                  />
                </div>
              </div>
              <p className="text-xs text-slate-400 mt-3">
                填写以上信息后，在下方上传 .mdj 文件开始对话。
              </p>
            </div>
          )}

          {/* 欢迎消息 */}
          {messages.length === 0 && !showNewSession && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Bot size={56} className="text-brand-200 mb-4" />
              <h2 className="text-lg font-semibold text-slate-600 mb-2">
                欢迎使用 UML 建模助手
              </h2>
              <p className="text-sm text-slate-400 max-w-md mb-4">
                点击"新建对话"开始提交作业。上传你的 .mdj 文件，
                我会根据你的 UML 图给出反馈和建议。
              </p>
              <p className="text-xs text-slate-400">
                当前模式：{GROUP_LABELS[group] || group}
              </p>
            </div>
          )}

          {/* 消息气泡 */}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}

          {/* UML 建模能力画像 - 直接显示在聊天区底部，仅 Agent C 学生且有画像数据时显示 */}
          {showAbilityProfile && abilityProfile && messages.length > 0 && (
            <div className="mt-4">
              <AbilityProfileCard profile={abilityProfile} />
            </div>
          )}

          {/* 发送中 - 先显示用户消息，再显示 AI 思考动画 */}
          {sendMut.isPending && pendingUserMsg && (
            <>
              {/* 用户消息（乐观显示） */}
              <div className="flex items-start gap-3 flex-row-reverse">
                <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
                  <UserIcon size={16} className="text-slate-600" />
                </div>
                <div className="max-w-[70%] rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm bg-brand-600 text-white">
                  {pendingUserMsg.mdj && (
                    <div className="flex items-center gap-1.5 text-xs mb-2 px-2 py-1 rounded bg-brand-700/50">
                      <FileJson size={12} />
                      {pendingUserMsg.mdj}
                    </div>
                  )}
                  {pendingUserMsg.image && (
                    <img src={pendingUserMsg.image} alt="preview" className="max-w-full max-h-48 rounded-lg mb-2" />
                  )}
                  <div className="text-sm whitespace-pre-wrap leading-relaxed">
                    {pendingUserMsg.content}
                  </div>
                </div>
              </div>

              {/* AI 思考动画（GPT 风格打字指示器） */}
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center shrink-0">
                  <Bot size={16} className="text-brand-600" />
                </div>
                <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-slate-200">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-[bounce_1.4s_ease-in-out_infinite]" />
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-[bounce_1.4s_ease-in-out_0.2s_infinite]" />
                    <span className="w-2 h-2 bg-slate-400 rounded-full animate-[bounce_1.4s_ease-in-out_0.4s_infinite]" />
                  </div>
                </div>
              </div>
            </>
          )}

          {/* 错误 */}
          {sendMut.isError && (
            <div className="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3 max-w-lg mx-auto">
              {(sendMut.error as any)?.response?.data?.detail || (sendMut.error as any)?.message || "发送失败"}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* ---- 输入区 ---- */}
        <div className="bg-white border-t border-slate-200 px-4 py-3">
          {/* 验证错误提示 */}
          {validationError && (
            <div className="bg-amber-50 text-amber-700 text-xs rounded-lg px-3 py-2 mb-2 flex items-center gap-2">
              <span>⚠️</span> {validationError}
            </div>
          )}
          {/* 附件状态提示 */}
          {!mdjFile && !imageFile && !sendMut.isPending && (
            <div className="text-xs text-slate-400 mb-2">
              📎 每次提交需同时上传 .mdj 文件和 UML 图截图
            </div>
          )}
          {/* 附件预览 */}
          {(mdjFile || imagePreview) && (
            <div className="flex gap-2 mb-2">
              {mdjFile && (
                <div className="flex items-center gap-1.5 bg-blue-50 text-blue-700 text-xs px-2.5 py-1.5 rounded-lg">
                  <FileJson size={14} />
                  <span className="max-w-[120px] truncate">{mdjFile.name}</span>
                  <button onClick={() => { setMdjFile(null); if (mdjInputRef.current) mdjInputRef.current.value = ""; }}>
                    <X size={12} />
                  </button>
                </div>
              )}
              {imagePreview && (
                <div className="relative">
                  <img src={imagePreview} alt="preview" className="h-16 rounded-lg border border-slate-200" />
                  <button
                    onClick={() => { setImageFile(null); setImagePreview(null); if (imageInputRef.current) imageInputRef.current.value = ""; }}
                    className="absolute -top-1 -right-1 bg-red-500 text-white rounded-full p-0.5"
                  >
                    <X size={10} />
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="flex items-end gap-2">
            {/* 附件按钮 */}
            <div className="flex gap-1">
              <input
                ref={mdjInputRef}
                type="file"
                accept=".mdj"
                className="hidden"
                onChange={(e) => setMdjFile(e.target.files?.[0] || null)}
              />
              <button
                onClick={() => mdjInputRef.current?.click()}
                className="p-2 text-slate-400 hover:text-brand-600 hover:bg-slate-100 rounded-lg transition"
                title="上传 .mdj 文件"
              >
                <FileJson size={18} />
              </button>

              <input
                ref={imageInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp"
                className="hidden"
                onChange={handleImageSelect}
              />
              <button
                onClick={() => imageInputRef.current?.click()}
                className="p-2 text-slate-400 hover:text-brand-600 hover:bg-slate-100 rounded-lg transition"
                title="上传图片"
              >
                <ImageIcon size={18} />
              </button>
            </div>

            {/* 文本输入 */}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息，或上传 .mdj 文件..."
              rows={1}
              className="flex-1 resize-none rounded-xl border border-slate-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none max-h-[150px]"
            />

            {/* 发送按钮 */}
            <button
              onClick={handleSend}
              disabled={sendMut.isPending || (!input.trim() && !mdjFile && !imageFile)}
              className={clsx(
                "p-2.5 rounded-xl transition",
                sendMut.isPending || (!input.trim() && !mdjFile && !imageFile)
                  ? "bg-slate-200 text-slate-400"
                  : "bg-brand-600 text-white hover:bg-brand-700",
              )}
            >
              {sendMut.isPending ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <Send size={18} />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


function MessageBubble({ msg }: { msg: ChatMessageItem }) {
  const isUser = msg.role === "user";

  return (
    <div className={clsx("flex items-start gap-3", isUser && "flex-row-reverse")}>
      {/* 头像 */}
      <div className={clsx(
        "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
        isUser ? "bg-slate-200" : "bg-brand-100",
      )}>
        {isUser ? (
          <UserIcon size={16} className="text-slate-600" />
        ) : (
          <Bot size={16} className="text-brand-600" />
        )}
      </div>

      {/* 消息体 */}
      <div className={clsx(
        "max-w-[70%] rounded-2xl px-4 py-3 shadow-sm",
        isUser
          ? "bg-brand-600 text-white rounded-tr-sm"
          : "bg-white text-slate-700 border border-slate-200 rounded-tl-sm",
      )}>
        {/* 附件标签 */}
        {msg.mdj_filename && (
          <div className={clsx(
            "flex items-center gap-1.5 text-xs mb-2 px-2 py-1 rounded",
            isUser ? "bg-brand-700/50" : "bg-blue-50 text-blue-600",
          )}>
            <FileJson size={12} />
            {msg.mdj_filename}
          </div>
        )}
        {msg.image_filename && (
          <div className={clsx(
            "flex items-center gap-1.5 text-xs mb-2 px-2 py-1 rounded",
            isUser ? "bg-brand-700/50" : "bg-green-50 text-green-600",
          )}>
            <ImageIcon size={12} />
            {msg.image_filename}
          </div>
        )}
        {msg.image_url && (
          <img
            src={msg.image_url}
            alt="uploaded"
            className="max-w-full max-h-48 rounded-lg mb-2"
          />
        )}

        {/* 内容 (使用 whitespace-pre-wrap 保留换行) */}
        <div className="text-sm whitespace-pre-wrap leading-relaxed">
          {msg.content}
        </div>

        {/* 评分标签 */}
        {msg.score_snapshot != null && (
          <div className={clsx(
            "mt-2 text-xs font-semibold inline-block px-2 py-0.5 rounded",
            msg.score_snapshot >= 80
              ? (isUser ? "bg-green-700/50" : "bg-green-100 text-green-700")
              : msg.score_snapshot >= 60
                ? (isUser ? "bg-yellow-700/50" : "bg-yellow-100 text-yellow-700")
                : (isUser ? "bg-red-700/50" : "bg-red-100 text-red-700"),
          )}>
            评分: {msg.score_snapshot.toFixed(0)}/100
          </div>
        )}

        {!isUser && msg.model_results && msg.model_results.length > 0 && (
          <div className="mt-3 grid grid-cols-1 xl:grid-cols-2 gap-3">
            {msg.model_results.map((result) => (
              <div key={result.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="font-semibold text-sm text-slate-700">
                    {MODEL_LABELS[result.model_key] || result.model_key}
                  </div>
                  {result.status === "success" ? (
                    <span className={clsx(
                      "text-xs font-semibold px-2 py-0.5 rounded-full",
                      (result.normalized_score ?? 0) >= 80
                        ? "bg-green-100 text-green-700"
                        : (result.normalized_score ?? 0) >= 60
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-red-100 text-red-700",
                    )}>
                      {result.normalized_score != null ? `${result.normalized_score.toFixed(0)}/100` : "—"}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-red-600">
                      <AlertCircle size={12} /> 失败
                    </span>
                  )}
                </div>
                {result.status !== "success" ? (
                  <div className="text-xs text-red-600 whitespace-pre-wrap">
                    {result.error || "模型调用失败"}
                  </div>
                ) : (
                  <>
                    <div className="text-xs text-slate-600 whitespace-pre-wrap max-h-40 overflow-y-auto border-t border-slate-200 pt-2">
                      {result.overall_comment || "暂无修改建议"}
                    </div>
                    {result.criterion_scores.length > 0 && (
                      <div className="mt-2 border-t border-slate-200 pt-2 max-h-52 overflow-y-auto">
                        <div className="text-[11px] font-medium text-slate-500 mb-1">指标评分</div>
                        <div className="space-y-1">
                          {result.criterion_scores.map((c) => (
                            <div key={c.id} className="text-[11px] bg-white border border-slate-100 rounded px-2 py-1">
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-mono text-brand-600">{c.code}</span>
                                <span className={c.has_issue ? "text-red-600" : "text-green-600"}>
                                  {c.score.toFixed(2)}/{c.max_score.toFixed(0)}
                                </span>
                              </div>
                              {(c.brief || c.reasoning) && (
                                <div className="text-slate-500 mt-0.5">
                                  {c.brief || c.reasoning}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 时间 */}
        <div className={clsx(
          "text-[10px] mt-1.5",
          isUser ? "text-brand-300" : "text-slate-400",
        )}>
          {formatTime(msg.created_at)}
        </div>
      </div>
    </div>
  );
}

interface AbilityProfileCardProps {
  profile: Record<string, number | null>;
}

function AbilityProfileCard({ profile }: AbilityProfileCardProps) {
  const data = ABILITY_DIMENSIONS.map((name) => ({
    dimension: name,
    value: profile[name] ?? null,
  }));

  const chartData = data.map((d) => ({
    dimension: d.dimension,
    // Recharts 需要数值，缺失时用 0 占位，tooltip 中区分“暂无数据”
    score: typeof d.value === "number" ? d.value : 0,
    raw: d.value,
  }));

  return (
    <div className="mt-3 bg-white rounded-xl border border-slate-200 p-4">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">
        UML建模能力画像
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
        {/* 雷达图 */}
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart
              data={chartData}
              margin={{ top: 10, right: 10, bottom: 10, left: 10 }}
            >
              <PolarGrid stroke="#e2e8f0" />
              <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11 }} />
              <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
              <RechartsTooltip
                formatter={(_v: number, _n: string, props: any) => {
                  const raw = props?.payload?.raw as number | null | undefined;
                  if (raw == null) return ["暂无数据", "得分"];
                  return [`${raw.toFixed(1)} 分`, "得分"];
                }}
              />
              <Radar
                name="本次作业"
                dataKey="score"
                stroke="#0f766e"
                fill="#14b8a6"
                fillOpacity={0.25}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        {/* 维度得分表格 */}
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-xs border border-slate-200 rounded-lg overflow-hidden">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left text-slate-500 font-medium">
                  能力维度
                </th>
                <th className="px-3 py-2 text-right text-slate-500 font-medium">
                  得分
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => {
                const v = d.value;
                const display =
                  v == null ? "暂无数据" : `${v.toFixed(1)} 分`;
                return (
                  <tr
                    key={d.dimension}
                    className="border-t border-slate-100"
                  >
                    <td className="px-3 py-1.5 text-slate-700">
                      {d.dimension}
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-700">
                      {display}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}