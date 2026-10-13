"""HTTP API 路由。"""
from fastapi import APIRouter

from . import admin, auth, chat, files, submissions, rubrics, grading, teacher, analysis, ws, activity

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])
router.include_router(submissions.router, prefix="/submissions", tags=["submissions"])
router.include_router(rubrics.router, prefix="/rubrics", tags=["rubrics"])
router.include_router(grading.router, prefix="/grading", tags=["grading"])
router.include_router(teacher.router, prefix="/teacher", tags=["teacher"])
router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(activity.router, prefix="/activity", tags=["activity"])
router.include_router(files.router, tags=["files"])
router.include_router(ws.router, tags=["ws"])
