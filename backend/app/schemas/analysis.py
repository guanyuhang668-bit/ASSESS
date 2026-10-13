from __future__ import annotations

from pydantic import BaseModel


class ModelAgreementRow(BaseModel):
    model_key: str
    submissions_graded: int
    mae_vs_teacher: float | None = None   # 百分制分差
    rho_vs_teacher: float | None = None   # Spearman 相关
    icc_vs_teacher: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    avg_tokens: float = 0.0
    avg_seconds: float = 0.0


class AnalysisSummaryOut(BaseModel):
    run_id: int
    rows: list[ModelAgreementRow]
    n_teacher_labelled: int
