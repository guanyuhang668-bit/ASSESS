import { useState, useEffect, useRef, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { listClasses, studentUpload, type GradingFeedbackOut } from "@/lib/api";
import {
  Upload as UploadIcon,
  CheckCircle2,
  AlertCircle,
  ImageIcon,
  FileJson,
  X,
  School,
  ChevronDown,
  FileText,
  Loader2,
  Star,
  MessageSquare,
} from "lucide-react";
import { useAuth } from "@/store/auth";

const DIAGRAM_TYPES = [
  { value: "use_case", label: "用例图" },
  { value: "class", label: "类图" },
  { value: "sequence", label: "时序图" },
  { value: "swimlane", label: "泳道图" },
];

export default function StudentUpload() {
  const user = useAuth((s) => s.user);
  const classes = useQuery({ queryKey: ["classes"], queryFn: listClasses, enabled: !!user?.class_id });
  const myClass = classes.data?.find((c) => c.id === user?.class_id);

  const [diagramType, setDiagramType] = useState("use_case");
  const [problemCode, setProblemCode] = useState("");
  const [problemStatement, setProblemStatement] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [gradingFeedback, setGradingFeedback] = useState<GradingFeedbackOut | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const mdjInputRef = useRef<HTMLInputElement>(null);
  const imgInputRef = useRef<HTMLInputElement>(null);
  const [mdjDragOver, setMdjDragOver] = useState(false);
  const [imgDragOver, setImgDragOver] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) { clearInterval(timerRef.current); return; }
    timerRef.current = setInterval(() => setCooldown((c) => c - 1), 1000);
    return () => clearInterval(timerRef.current);
  }, [cooldown > 0]);

  function handleImageChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] || null;
    setImage(f);
    if (f) {
      const reader = new FileReader();
      reader.onload = (ev) => setImagePreview(ev.target?.result as string);
      reader.readAsDataURL(f);
    } else {
      setImagePreview(null);
    }
  }

  const handleMdjDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setMdjDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && (f.name.endsWith(".mdj") || f.type === "application/json")) {
      setFile(f);
    }
  }, []);

  const handleImgDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setImgDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.type.startsWith("image/")) {
      setImage(f);
      const reader = new FileReader();
      reader.onload = (ev) => setImagePreview(ev.target?.result as string);
      reader.readAsDataURL(f);
    }
  }, []);

  const uploadMut = useMutation({
    mutationFn: async () => {
      if (!user?.class_id) throw new Error("你的账号尚未分配班级，请联系管理员");
      if (!problemCode.trim()) throw new Error("请填写题目编号");
      if (!problemStatement.trim()) throw new Error("请填写题目描述");
      if (!file) throw new Error("请选择 .mdj 文件");
      if (!image) throw new Error("请上传 UML 图截图");
      setResult(null);
      setGradingFeedback(null);
      const sub = await studentUpload({
        file, image,
        diagram_type: diagramType,
        problem_code: problemCode,
        problem_statement: problemStatement,
      });
      if (sub.parse_error) {
        setResult({ ok: false, message: `已收但解析失败: ${sub.parse_error}` });
      } else {
        setResult({
          ok: true,
          message: `提交成功！#${sub.id} 元素 ${sub.element_count} 关系 ${sub.relation_count}`,
        });
        if (sub.grading_feedback) {
          setGradingFeedback(sub.grading_feedback);
        }
      }
    },
    onError: (e: any) => {
      setResult({
        ok: false,
        message: e?.response?.data?.detail || e?.message || "上传失败",
      });
    },
  });

  const canSubmit = !!user?.class_id && !!problemCode.trim() && !!problemStatement.trim() && !!file && !!image && !uploadMut.isPending && cooldown <= 0;

  return (
    <div className={gradingFeedback ? "max-w-6xl mx-auto" : "max-w-3xl mx-auto"}>
      {/* 页面标题 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">提交作业</h1>
        <p className="text-sm text-slate-500 mt-1">上传你的 UML 建模文件，系统将自动解析并评分</p>
      </div>

      {/* 班级信息条 */}
      <div className="bg-gradient-to-r from-brand-50 to-blue-50 border border-brand-200 rounded-xl px-5 py-3.5 mb-5 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-brand-100 flex items-center justify-center flex-shrink-0">
          <School size={18} className="text-brand-600" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-brand-600 font-medium">当前班级</p>
          <p className="text-sm font-semibold text-slate-800 truncate">
            {user?.class_id
              ? (myClass ? `${myClass.code} ${myClass.name}` : `班级 #${user.class_id}`)
              : <span className="text-red-500 font-normal">未分配班级，请联系管理员</span>}
          </p>
        </div>
      </div>

      {/* 主表单卡片 */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {/* 基础信息 */}
        <div className="p-5 space-y-4 border-b border-slate-100">
          <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <FileText size={15} className="text-slate-400" />
            基础信息
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">
                图类型 <span className="text-red-400">*</span>
              </label>
              <div className="relative">
                <select
                  value={diagramType}
                  onChange={(e) => setDiagramType(e.target.value)}
                  className="w-full appearance-none px-3 py-2.5 rounded-lg border border-slate-200 bg-white text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition"
                >
                  {DIAGRAM_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">
                题目编号 <span className="text-red-400">*</span>
              </label>
              <input
                value={problemCode}
                onChange={(e) => setProblemCode(e.target.value)}
                placeholder="如 1、实验报告-1"
                className="w-full px-3 py-2.5 rounded-lg border border-slate-200 text-sm placeholder:text-slate-350 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">
                题目描述 <span className="text-red-400">*</span>
              </label>
              <input
                value={problemStatement}
                onChange={(e) => setProblemStatement(e.target.value)}
                placeholder="简要描述题目要求"
                className="w-full px-3 py-2.5 rounded-lg border border-slate-200 text-sm placeholder:text-slate-350 focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition"
              />
            </div>
          </div>
        </div>

        {/* 文件上传区 */}
        <div className="p-5 space-y-4 border-b border-slate-100">
          <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <UploadIcon size={15} className="text-slate-400" />
            文件上传
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* mdj 文件上传 */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">
                .mdj 建模文件 <span className="text-red-400">*</span>
              </label>
              <input
                ref={mdjInputRef}
                type="file"
                accept=".mdj,application/json"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
              {file ? (
                <div className="flex items-center gap-3 px-4 py-3 rounded-lg border border-brand-200 bg-brand-50/50">
                  <div className="w-9 h-9 rounded-lg bg-brand-100 flex items-center justify-center flex-shrink-0">
                    <FileJson size={18} className="text-brand-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-800 truncate">{file.name}</p>
                    <p className="text-xs text-slate-400">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                  <button
                    onClick={() => { setFile(null); if (mdjInputRef.current) mdjInputRef.current.value = ""; }}
                    className="p-1 hover:bg-brand-100 rounded-md transition"
                  >
                    <X size={14} className="text-slate-400" />
                  </button>
                </div>
              ) : (
                <div
                  onClick={() => mdjInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setMdjDragOver(true); }}
                  onDragLeave={() => setMdjDragOver(false)}
                  onDrop={handleMdjDrop}
                  className={`flex flex-col items-center justify-center gap-2 px-4 py-6 rounded-lg border-2 border-dashed cursor-pointer transition-all ${
                    mdjDragOver
                      ? "border-brand-400 bg-brand-50"
                      : "border-slate-200 hover:border-brand-300 hover:bg-slate-50"
                  }`}
                >
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center">
                    <FileJson size={20} className="text-slate-400" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-slate-600">
                      <span className="text-brand-600 font-medium">点击选择</span> 或拖拽文件
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">仅支持 .mdj 格式</p>
                  </div>
                </div>
              )}
            </div>

            {/* 图片上传 */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">
                UML 图截图 <span className="text-red-400">*</span>
              </label>
              <input
                ref={imgInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg,image/gif,image/webp,image/bmp"
                onChange={handleImageChange}
                className="hidden"
              />
              {imagePreview ? (
                <div className="relative rounded-lg border border-slate-200 overflow-hidden group">
                  <img
                    src={imagePreview}
                    alt="预览"
                    className="w-full h-[136px] object-contain bg-slate-50"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition flex items-center justify-center opacity-0 group-hover:opacity-100">
                    <button
                      onClick={() => { setImage(null); setImagePreview(null); if (imgInputRef.current) imgInputRef.current.value = ""; }}
                      className="px-3 py-1.5 bg-white rounded-lg text-xs font-medium text-red-600 shadow-sm hover:bg-red-50 transition"
                    >
                      移除图片
                    </button>
                  </div>
                  {image && (
                    <div className="px-3 py-2 bg-white border-t border-slate-100 flex items-center gap-2">
                      <ImageIcon size={13} className="text-slate-400" />
                      <span className="text-xs text-slate-500 truncate flex-1">{image.name}</span>
                      <span className="text-xs text-slate-400">{(image.size / 1024).toFixed(1)} KB</span>
                    </div>
                  )}
                </div>
              ) : (
                <div
                  onClick={() => imgInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setImgDragOver(true); }}
                  onDragLeave={() => setImgDragOver(false)}
                  onDrop={handleImgDrop}
                  className={`flex flex-col items-center justify-center gap-2 px-4 py-6 rounded-lg border-2 border-dashed cursor-pointer transition-all ${
                    imgDragOver
                      ? "border-brand-400 bg-brand-50"
                      : "border-slate-200 hover:border-brand-300 hover:bg-slate-50"
                  }`}
                >
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center">
                    <ImageIcon size={20} className="text-slate-400" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-slate-600">
                      <span className="text-brand-600 font-medium">点击选择</span> 或拖拽图片
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">PNG / JPG / GIF / WebP</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 提交区 */}
        <div className="p-5 bg-slate-50/50">
          {result && (
            <div className={`mb-4 flex items-start gap-3 text-sm p-4 rounded-lg border ${result.ok ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`}>
              {result.ok ? (
                <CheckCircle2 size={18} className="text-green-500 mt-0.5 flex-shrink-0" />
              ) : (
                <AlertCircle size={18} className="text-red-500 mt-0.5 flex-shrink-0" />
              )}
              <div>
                <p className={`font-medium ${result.ok ? "text-green-800" : "text-red-800"}`}>
                  {result.ok ? "提交成功" : "提交失败"}
                </p>
                <p className={`mt-0.5 ${result.ok ? "text-green-600" : "text-red-600"}`}>
                  {result.message}
                </p>
              </div>
            </div>
          )}

          {/* 评分反馈：左右分栏（左=UML图，右=评分详情可滚动） */}
          {gradingFeedback && (
            <div className="mb-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* 左：学生 UML 图 */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 sticky top-4 self-start">
                <p className="text-sm font-medium text-slate-600 mb-2 flex items-center gap-2">
                  <ImageIcon size={14} className="text-slate-400" /> 我的 UML 图
                </p>
                {imagePreview ? (
                  <img
                    src={imagePreview}
                    alt="我的 UML 图"
                    className="w-full rounded-lg border border-slate-100"
                  />
                ) : (
                  <div className="py-12 text-center text-sm text-slate-400">暂无图片</div>
                )}
              </div>

              {/* 右：评分详情（可滚动） */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden max-h-[calc(100vh-10rem)] overflow-y-auto">
                <div className="px-5 py-3.5 bg-gradient-to-r from-amber-50 to-orange-50 border-b border-amber-200/50 flex items-center gap-3 sticky top-0 z-10">
                  <div className="w-9 h-9 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
                    <Star size={18} className="text-amber-600" />
                  </div>
                  <div className="flex-1">
                    <p className="text-xs text-amber-600 font-medium">AI 自动评分</p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold text-slate-800">
                      {gradingFeedback.normalized_score.toFixed(1)}
                    </p>
                    <p className="text-xs text-slate-400">/ 100</p>
                  </div>
                </div>
                {/* 总评 */}
                {gradingFeedback.overall_comment && (
                  <div className="px-5 py-3 border-b border-slate-100 flex items-start gap-2.5">
                    <MessageSquare size={15} className="text-slate-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-xs font-medium text-slate-500 mb-1">总评</p>
                      <p className="text-sm text-slate-700 leading-relaxed">{gradingFeedback.overall_comment}</p>
                    </div>
                  </div>
                )}
                {/* 分项评分 */}
                {gradingFeedback.criteria.length > 0 && (
                  <div className="px-5 py-3">
                    <p className="text-xs font-medium text-slate-500 mb-2">分项评分</p>
                    <div className="space-y-2">
                      {gradingFeedback.criteria.map((c) => {
                        const pct = c.max_score > 0 ? (c.score / c.max_score) * 100 : 0;
                        const barColor = pct >= 80 ? "bg-green-400" : pct >= 60 ? "bg-amber-400" : pct >= 40 ? "bg-orange-400" : "bg-red-400";
                        return (
                          <div key={c.code}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs font-medium text-slate-600">{c.code}</span>
                              <span className="text-xs text-slate-500">
                                {c.score.toFixed(1)} / {c.max_score.toFixed(1)}
                              </span>
                            </div>
                            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                                style={{ width: `${Math.min(pct, 100)}%` }}
                              />
                            </div>
                            {c.reasoning && (
                              <p className="text-xs text-slate-400 mt-1 leading-relaxed">{c.reasoning}</p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <button
            disabled={!canSubmit}
            onClick={() => { setCooldown(3); uploadMut.mutate(); }}
            className="w-full sm:w-auto px-6 py-2.5 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 flex items-center justify-center gap-2 transition shadow-sm shadow-brand-600/20"
          >
            {uploadMut.isPending ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                上传并评分中…
              </>
            ) : cooldown > 0 ? (
              `请稍候 (${cooldown}s)`
            ) : (
              <>
                <UploadIcon size={15} />
                提交作业
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
