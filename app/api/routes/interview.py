from __future__ import annotations

import json
from pathlib import Path
import asyncio

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy.orm import Session
import websockets

from app.core.database import get_db
from app.models.interview import Interview
from app.schemas.interview import (
    EndInterviewRequest,
    FinalReportResponse,
    StartInterviewRequest,
    StartInterviewResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    UploadResumeResponse,
)
from app.services.deps import get_context_service, get_interview_agent, get_voice_service
from app.services.context_service import ContextDistillationService
from app.services.jd_analyzer import compare_resume_with_jd
from app.services.resume_parser import parse_resume


router = APIRouter(tags=["interview"])


@router.post("/upload_resume", response_model=UploadResumeResponse)
async def upload_resume(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    db: Session = Depends(get_db),
    context_service: ContextDistillationService = Depends(get_context_service),
) -> UploadResumeResponse:
    if Path(resume.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Resume must be a PDF file.")

    upload_dir = Path("storage") / "resumes"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / (resume.filename or "resume.pdf")
    file_path.write_bytes(await resume.read())

    resume_text, profile = parse_resume(file_path)
    gap_analysis = compare_resume_with_jd(profile, job_description)
    distilled_context = await context_service.distill(
        resume_text=resume_text,
        profile=profile,
        job_description=job_description,
        gap_analysis=gap_analysis,
    )
    interview = Interview(
        candidate_name=profile.candidate_name,
        resume_filename=file_path.name,
        resume_text=resume_text,
        job_description=job_description,
        resume_summary_json=json.dumps(
            {
                "profile": profile.model_dump(),
                "distilled_context": distilled_context,
            }
        ),
        skill_gaps_json=json.dumps(gap_analysis),
        status="created",
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

    return UploadResumeResponse(
        interview_id=interview.id,
        candidate_name=profile.candidate_name,
        resume_profile=profile,
        matched_skills=gap_analysis["matched_skills"],
        missing_skills=gap_analysis["missing_skills"],
        additional_focus_areas=gap_analysis["additional_focus_areas"],
    )


@router.post("/start_interview", response_model=StartInterviewResponse)
async def start_interview(
    payload: StartInterviewRequest,
    db: Session = Depends(get_db),
    agent=Depends(get_interview_agent),
) -> StartInterviewResponse:
    interview = db.query(Interview).filter(Interview.id == payload.interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found.")

    if not interview.questions:
        await agent.seed_questions(db, interview)
        db.refresh(interview)

    current_question = agent.get_current_question(db, interview)
    interview.status = "in_progress"
    db.add(interview)
    db.commit()

    return StartInterviewResponse(
        interview_id=interview.id,
        status=interview.status,
        total_questions=interview.question_count,
        current_question=agent.to_payload(current_question),
        voice_hint="Speak naturally. The assistant speech can be interrupted when you start talking.",
    )


@router.post("/submit_answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    payload: SubmitAnswerRequest,
    db: Session = Depends(get_db),
    agent=Depends(get_interview_agent),
) -> SubmitAnswerResponse:
    interview = db.query(Interview).filter(Interview.id == payload.interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found.")

    if not payload.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    result = await agent.submit_answer(
        db=db,
        interview=interview,
        question_id=payload.question_id,
        answer_text=payload.answer,
        transcript_source=payload.transcript_source,
    )
    return SubmitAnswerResponse(
        interview_id=interview.id,
        status=interview.status,
        next_question=result["next_question"],
        follow_up_generated=result["follow_up_generated"],
        report_ready=result["report_ready"],
    )


@router.post("/end_interview")
async def end_interview(
    payload: EndInterviewRequest,
    db: Session = Depends(get_db),
    agent=Depends(get_interview_agent),
) -> dict[str, object]:
    interview = db.query(Interview).filter(Interview.id == payload.interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found.")

    updated = agent.end_interview(db, interview)
    return {
        "interview_id": updated.id,
        "status": updated.status,
        "report_ready": True,
    }


@router.get("/get_report", response_model=FinalReportResponse)
async def get_report(
    interview_id: int,
    db: Session = Depends(get_db),
    agent=Depends(get_interview_agent),
) -> FinalReportResponse:
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found.")

    report = await agent.build_report_if_ready(db, interview)
    if report is None:
        raise HTTPException(status_code=409, detail="Interview is still in progress.")

    return FinalReportResponse(**report)


@router.post("/voice/speak")
async def voice_speak(
    text: str = Form(...),
    voice_service=Depends(get_voice_service),
) -> Response:
    audio = await voice_service.synthesize(text)
    return Response(content=audio.content, media_type=audio.media_type)


@router.post("/voice/transcribe")
async def voice_transcribe(
    audio: UploadFile = File(...),
    voice_service=Depends(get_voice_service),
) -> dict[str, str]:
    transcript = await voice_service.transcribe(
        audio_bytes=await audio.read(),
        media_type=audio.content_type or "audio/webm",
    )
    return {"transcript": transcript}


@router.websocket("/ws/voice")
async def voice_ws(
    websocket: WebSocket,
    voice_service=Depends(get_voice_service),
) -> None:
    await websocket.accept()

    if not voice_service.configured:
        await websocket.send_json({"type": "Error", "detail": "Deepgram API key is not configured."})
        await websocket.close(code=1011)
        return

    async with websockets.connect(
        voice_service.live_transcription_url(),
        additional_headers={"Authorization": f"Token {voice_service.settings.deepgram_api_key}"},
        max_size=None,
    ) as deepgram_ws:
        async def client_to_deepgram() -> None:
            try:
                while True:
                    message = await websocket.receive()
                    if "bytes" in message and message["bytes"] is not None:
                        await deepgram_ws.send(message["bytes"])
                    elif "text" in message and message["text"]:
                        payload = message["text"]
                        if payload == "close":
                            await deepgram_ws.send('{"type":"CloseStream"}')
                            break
                    elif message.get("type") == "websocket.disconnect":
                        await deepgram_ws.send('{"type":"CloseStream"}')
                        break
            except WebSocketDisconnect:
                await deepgram_ws.send('{"type":"CloseStream"}')

        async def deepgram_to_client() -> None:
            try:
                async for message in deepgram_ws:
                    if isinstance(message, bytes):
                        continue
                    await websocket.send_text(message)
            except websockets.ConnectionClosed:
                await websocket.close()

        tasks = [
            asyncio.create_task(client_to_deepgram()),
            asyncio.create_task(deepgram_to_client()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exception = task.exception()
            if exception:
                raise exception
