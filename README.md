# AI Interview System

A FastAPI-based AI interview platform that parses a resume, compresses both the resume and job description with LLM prompts, generates role-specific interview questions, runs a live voice interview with Deepgram, stores the complete interview in SQLite, and produces a coach-style final feedback report after the interview ends.

## Current Architecture

- Backend: FastAPI
- Database: SQLite with SQLAlchemy ORM
- LLM provider: OpenRouter
- Voice provider: Deepgram
- Frontend: server-rendered HTML with plain JavaScript and CSS
- Evaluation timing: deferred until final report generation
- Prompt strategy: separate prompts for resume compression, JD compression, question generation, turn decision, and final reporting

## Core Capabilities

- Upload resume PDF and job description
- Parse raw resume text into a structured candidate profile
- Compress the full resume into a concise interview summary
- Compress the full JD into a concise interviewer-facing JD summary
- Compare resume skills against the JD and identify gaps
- Generate exactly 6 tailored interview questions using a dedicated question-generation prompt
- Run a live voice interview with:
  - Deepgram TTS for interviewer speech
  - Deepgram streaming STT for candidate speech
  - live transcript updates
  - automatic answer capture on utterance end
  - automatic barge-in when the candidate starts speaking over model audio
- Use LLM-driven interviewer turn decisions after each answer:
  - `NEXT_QUESTION`
  - `FOLLOWUP`
  - `CLARIFY`
  - `ENCOURAGE`
- Save each answer during the interview without scoring it live
- End the interview manually
- Generate a final interview-coach report with:
  - overall score
  - hiring recommendation
  - metric breakdown
  - strengths
  - areas to work on
  - question-by-question feedback
  - resources to improve
  - next steps

## Prompt Architecture

The current system uses five distinct LLM prompt families:

1. Resume Compression Prompt
2. JD Compression Prompt
3. 6-Question Generation Prompt
4. Interviewer Turn-Decision Prompt
5. Final Interview Feedback Report Prompt

This separation improves maintainability, prompt quality, and prompt-token efficiency.

## Project Structure

```text
app/
  api/
    routes/
      interview.py        Main HTTP and websocket routes
  core/
    config.py             Environment and app settings
    database.py           SQLAlchemy engine, session, base
  models/
    interview.py          Interviews, questions, answers, scores tables
  schemas/
    interview.py          Request and response models
  services/
    deps.py               Dependency wiring for services
    evaluator.py          Answer scoring logic
    context_service.py    Resume/JD compression and context distillation
    interview_agent.py    Interview loop orchestration
    jd_analyzer.py        JD skill extraction and gap analysis
    llm.py                OpenRouter client wrapper
    question_generator.py Question generation and interviewer turn decisions
    report_service.py     Final deferred evaluation and report generation
    resume_parser.py      Resume PDF parsing and profile extraction
    vector_store.py       Optional in-memory question memory abstraction
    voice_service.py      Deepgram STT/TTS helpers
  static/
    css/styles.css        Frontend styles
    js/app.js             Frontend interview state machine
  templates/
    index.html            Main UI
  main.py                 FastAPI app bootstrap
storage/
  resumes/                Uploaded resumes
  app.db                  SQLite database
```

## Runtime Flow

### 1. Resume Intake

- User uploads a PDF resume and JD text from the UI.
- `POST /upload_resume` in [interview.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/api/routes/interview.py) saves the PDF.
- [resume_parser.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/resume_parser.py) extracts:
  - candidate name
  - skills
  - experience
  - projects
  - education
- [jd_analyzer.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/jd_analyzer.py) extracts JD skills and computes:
  - matched skills
  - missing skills
  - additional focus areas
- [context_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/context_service.py) runs:
  - resume compression prompt
  - JD compression prompt
  - compact focus/risk context generation
- A new `interviews` row is created in SQLite.

### 2. Interview Start

- User clicks `Start Interview`.
- `POST /start_interview` loads or seeds interview questions.
- [interview_agent.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/interview_agent.py) calls [question_generator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/question_generator.py).
- [question_generator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/question_generator.py) uses:
  - compressed resume summary
  - compressed JD summary
  - dedicated 6-question generation prompt
- Questions are stored in the `questions` table.

### 3. Voice Interview Loop

- Frontend opens `ws/voice`.
- Browser microphone audio is chunked with `MediaRecorder`.
- Backend proxies those chunks to Deepgram streaming STT.
- Deepgram sends interim and final transcript events back through the websocket.
- [app.js](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/static/js/app.js) updates the transcript live in the UI.
- For interviewer speech:
  - frontend calls `POST /voice/speak`
  - [voice_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/voice_service.py) calls Deepgram TTS
  - returned audio is played in the browser

### 4. Turn Taking

- While model audio is playing, transcript events are monitored.
- If real speech text appears from the candidate, frontend stops playback immediately.
- After enough silence, Deepgram marks the utterance complete.
- Frontend auto-submits the answer with `POST /submit_answer`.

### 5. During Interview

- Answers are stored in the `answers` table.
- No runtime evaluation is performed.
- The LLM decides the next interviewer move using the turn-decision prompt.
- The system may:
  - move to the next prepared question
  - ask a follow-up
  - clarify the same question
  - encourage the student and simplify
- This decision uses:
  - compressed resume summary
  - compressed JD summary
  - current question number
  - question bank
  - latest student response

### 6. End Interview

- User clicks `End Interview`.
- Frontend immediately:
  - stops TTS
  - closes the voice websocket
  - stops microphone capture
- Backend marks the interview as `report_pending`.

### 7. Final Report

- User clicks `Generate Report`.
- `GET /get_report` triggers [report_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/report_service.py).
- [report_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/report_service.py):
  - evaluates every saved answer using [evaluator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/evaluator.py)
  - stores results in the `scores` table
  - computes average scores
  - builds the full interview transcript
  - uses the final interview-coach report prompt to generate the final feedback report
- Frontend renders the final report as text using the returned `report_text`.

## API Surface

- `POST /upload_resume`
- `POST /start_interview`
- `POST /submit_answer`
- `POST /end_interview`
- `GET /get_report?interview_id=<id>`
- `POST /voice/speak`
- `POST /voice/transcribe`
- `WS /ws/voice`

## Database Tables

- `interviews`
  - stores session metadata, compressed summaries, skill gaps, lifecycle state, and final recommendation
- `questions`
  - stores generated and adaptive interviewer questions
- `answers`
  - stores raw user answers and transcript source
- `scores`
  - stores deferred evaluation results produced during final reporting

## Environment Variables

Copy [.env.example](/c:/Users/SuryaD/Desktop/Ai-Interviewer/.env.example) to `.env`.

```env
DEEPGRAM_API_KEY=your_deepgram_key_here
DEEPGRAM_STT_MODEL=nova-3
DEEPGRAM_TTS_MODEL=aura-2-thalia-en
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Notes:

- Without `OPENROUTER_API_KEY`, the app falls back to deterministic question/evaluation behavior.
- Without `DEEPGRAM_API_KEY`, voice features will fail, but typed flows can still be used where applicable.

## Setup

### 1. Create or activate the virtual environment

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Run the app

```powershell
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Validation

```powershell
python -m compileall app
python -c "from app.main import app; print(app.title)"
```

## Documentation

- Architecture and runtime workflow: [WORKFLOW.md](/c:/Users/SuryaD/Desktop/Ai-Interviewer/WORKFLOW.md)

## Production Notes

- Restrict CORS before deployment
- Add authentication and user ownership
- Replace SQLite if you need multi-user concurrent production scale
- Add Alembic migrations for schema evolution
- Move uploaded resume storage to object storage if deploying across instances
