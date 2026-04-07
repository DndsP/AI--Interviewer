# Architecture, Workflow, HLD And LLD

This is the team-facing architecture document for the AI Interview System. It covers:

- HLD: high-level design
- LLD: low-level design
- workflow: full runtime pipeline
- prompt architecture: how prompt responsibilities are split across the system

The goal is to give engineering, product, and future contributors a shared understanding of how the system works end to end.

## 1. System Summary

The AI Interview System is a FastAPI application that:

1. accepts a resume PDF and job description
2. parses the resume into structured candidate data
3. compresses the full resume and full JD with separate LLM prompts
4. generates 6 tailored interview questions
5. runs a live voice interview using Deepgram
6. uses an interviewer decision prompt after each answer
7. stores all interview interactions in SQLite
8. defers scoring until interview end
9. generates a detailed interview-coach style report

## 2. HLD

### 2.1 High-Level Goals

- Create a realistic, encouraging interview experience
- Keep live interview latency low
- Reduce repeated token usage with compact summaries
- Separate prompt responsibilities for maintainability
- Preserve strong traceability across questions, answers, and scores
- Keep architecture simple enough for a small team to own

### 2.2 High-Level System Layers

The system is organized into six layers:

1. Frontend Layer
2. API Layer
3. Service Layer
4. Persistence Layer
5. External Provider Layer
6. Storage Layer

### 2.3 High-Level Architecture

```text
Browser UI
  -> FastAPI routes / websocket
    -> Interview orchestration and service layer
      -> SQLite
      -> OpenRouter
      -> Deepgram
```

### 2.4 Core High-Level Components

#### Frontend Layer

Owners:

- [index.html](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/templates/index.html)
- [app.js](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/static/js/app.js)
- [styles.css](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/static/css/styles.css)

Responsibilities:

- collect inputs
- manage voice interview lifecycle
- render live transcript
- render final report text

#### API Layer

Owner:

- [interview.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/api/routes/interview.py)

Responsibilities:

- expose HTTP endpoints
- expose websocket proxy for voice streaming
- coordinate service calls

#### Service Layer

Owners:

- [resume_parser.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/resume_parser.py)
- [jd_analyzer.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/jd_analyzer.py)
- [context_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/context_service.py)
- [question_generator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/question_generator.py)
- [interview_agent.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/interview_agent.py)
- [evaluator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/evaluator.py)
- [report_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/report_service.py)
- [voice_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/voice_service.py)
- [llm.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/llm.py)

Responsibilities:

- implement business logic
- isolate provider integrations
- orchestrate prompt-driven interview behavior
- keep prompts and token usage manageable

#### Persistence Layer

Owners:

- [database.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/core/database.py)
- [interview.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/models/interview.py)

Responsibilities:

- session management
- interview lifecycle persistence
- question, answer, and score storage

#### External Providers

- OpenRouter
  - resume compression
  - JD compression
  - question generation
  - interviewer turn decision
  - deferred answer evaluation
  - final report generation
- Deepgram
  - streaming STT
  - TTS

#### Storage Layer

- `storage/resumes`
- `storage/app.db`

### 2.5 HLD Design Decisions

#### Separate Prompt Families

Decision:

- split prompt responsibilities into separate specialized prompts

Reason:

- clearer ownership
- easier prompt tuning
- lower coupling
- simpler production debugging

#### Deferred Evaluation

Decision:

- do not score each answer during the live interview

Reason:

- reduces response latency
- keeps the voice interview smooth
- centralizes scoring in the final report stage

#### Resume/JD Compression Before Interview

Decision:

- summarize the full resume and full JD once, then reuse compressed summaries everywhere

Reason:

- reduces token usage
- avoids resending large raw documents every turn
- improves consistency across question generation and follow-up decisions

#### Single Orchestrated Interview Agent

Decision:

- keep a single workflow-oriented interview agent instead of building a multi-agent system

Reason:

- easier persistence
- simpler runtime flow
- enough for guided interview orchestration

## 3. Prompt Architecture

The system currently uses five distinct prompt families.

### 3.1 Resume Compression Prompt

Owner:

- [context_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/context_service.py)

Purpose:

- convert full raw resume text into a compressed interviewer-facing summary

Output style:

- plain-text structured summary
- under 200 words
- interview-relevant details only

### 3.2 JD Compression Prompt

Owner:

- [context_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/context_service.py)

Purpose:

- convert full JD text into a compressed interviewer-facing JD summary

Output style:

- plain-text structured summary
- under 150 words
- signal only, no boilerplate

### 3.3 6-Question Generation Prompt

Owner:

- [question_generator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/question_generator.py)

Purpose:

- generate exactly 6 interview questions with a fixed role-based structure:
  - icebreaker
  - must-have technical
  - project deep-dive
  - behavioral
  - problem-solving/system design
  - motivation/culture fit

### 3.4 Interviewer Turn-Decision Prompt

Owner:

- [question_generator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/question_generator.py)

Purpose:

- decide the next conversational move after each answer

Allowed actions:

- `NEXT_QUESTION`
- `FOLLOWUP`
- `CLARIFY`
- `ENCOURAGE`

Inputs:

- compressed resume summary
- compressed JD summary
- current question number
- question bank
- current question
- student response

### 3.5 Final Report Prompt

Owner:

- [report_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/report_service.py)

Purpose:

- generate the final interview-coach style report

Inputs:

- compressed resume summary
- compressed JD summary
- full interview transcript

Outputs:

- structured strengths
- structured weaknesses
- hiring recommendation
- full formatted report text

## 4. HLD Data Flow

### 4.1 Primary Request Flow

```text
Upload Resume
  -> Parse Resume
  -> Analyze JD
  -> Compress Resume
  -> Compress JD
  -> Save Interview

Start Interview
  -> Generate 6 Questions
  -> Speak Question
  -> Stream Voice
  -> Save Answer
  -> Decide Next Action
  -> Repeat

End Interview
  -> Stop Voice
  -> Mark Report Pending

Generate Report
  -> Evaluate Answers
  -> Build Transcript
  -> Generate Final Coach Report
  -> Return Text Report
```

### 4.2 Voice Flow

```text
Browser Mic
  -> MediaRecorder chunks
  -> WS /ws/voice
  -> Deepgram streaming STT
  -> transcript events
  -> frontend transcript rendering
  -> auto answer submit
```

### 4.3 TTS Flow

```text
Question text
  -> POST /voice/speak
  -> Deepgram TTS
  -> audio bytes
  -> browser playback
```

## 5. LLD

### 5.1 File-Level Ownership

#### [app/main.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/main.py)

- bootstraps the FastAPI app
- creates DB tables
- mounts static routes
- includes the interview router

#### [app/core/config.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/core/config.py)

- loads app settings
- manages provider configuration

#### [app/core/database.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/core/database.py)

- creates engine
- provides DB sessions

#### [app/models/interview.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/models/interview.py)

- defines `Interview`
- defines `Question`
- defines `Answer`
- defines `Score`

#### [app/schemas/interview.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/schemas/interview.py)

- defines request/response contracts
- includes final `report_text` in the report response

#### [app/services/llm.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/llm.py)

- shared OpenRouter JSON wrapper
- central fallback behavior

#### [app/services/context_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/context_service.py)

Responsibilities:

- compress resume with `RESUME_COMPRESSION_PROMPT`
- compress JD with `JD_COMPRESSION_PROMPT`
- create compact focus and risk areas

Output contract:

- `candidate_brief`
- `jd_brief`
- `focus_areas`
- `risk_areas`

#### [app/services/question_generator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/question_generator.py)

Responsibilities:

- generate 6 initial questions
- decide next interviewer action

Key prompt constants:

- `QUESTION_GENERATION_PROMPT`
- `INTERVIEWER_DECISION_PROMPT`

Key runtime methods:

- `generate_questions(...)`
- `decide_next_turn(...)`

#### [app/services/interview_agent.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/interview_agent.py)

Responsibilities:

- seed initial question set
- track interview progression
- save answers
- apply next-turn decisions
- insert adaptive follow-up/clarify/encourage questions
- end the interview

#### [app/services/evaluator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/evaluator.py)

Responsibilities:

- evaluate saved answers after interview end
- score answer quality
- generate per-answer feedback

#### [app/services/report_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/report_service.py)

Responsibilities:

- score missing answers
- build transcript text
- generate final coach-style report

Key prompt constant:

- `FINAL_REPORT_PROMPT`

#### [app/services/voice_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/voice_service.py)

Responsibilities:

- Deepgram streaming URL
- Deepgram TTS
- optional non-streaming STT helper

#### [app/services/deps.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/deps.py)

- central service dependency wiring

### 5.2 API-Level LLD

#### `POST /upload_resume`

Processing:

- store PDF
- parse resume
- analyze JD
- compress resume
- compress JD
- create interview row

#### `POST /start_interview`

Processing:

- generate 6 questions if absent
- set current question

#### `POST /submit_answer`

Processing:

- save answer
- run interviewer turn-decision prompt
- if `NEXT_QUESTION`, move on
- if `FOLLOWUP`, insert contextual probe
- if `CLARIFY`, insert gentle rephrased question
- if `ENCOURAGE`, insert simpler encouraging prompt

#### `POST /end_interview`

Processing:

- stop active interview progression
- mark `report_pending`

#### `GET /get_report`

Processing:

- evaluate answers
- build transcript
- run final report prompt
- return `report_text` and structured fields

#### `POST /voice/speak`

- returns Deepgram TTS audio bytes

#### `WS /ws/voice`

- proxies voice audio to Deepgram streaming STT
- relays transcript events back to browser

### 5.3 Database LLD

#### `interviews`

Stores:

- candidate metadata
- raw resume text
- raw JD text
- `resume_summary_json`
  - profile
  - compressed resume summary
  - compressed JD summary
  - focus areas
  - risk areas
- `skill_gaps_json`
- current question tracking
- final summaries and recommendation

#### `questions`

Stores:

- sequence
- category
- prompt
- expected focus
- follow-up flag

#### `answers`

Stores:

- answer text
- transcript source
- timestamp

#### `scores`

Stores:

- correctness
- clarity
- depth
- overall
- feedback

### 5.4 Frontend LLD

Owner:

- [app.js](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/static/js/app.js)

Responsibilities:

- upload resume/JD
- manage live voice loop
- auto-submit answers
- stop TTS on barge-in
- end interview cleanly
- render final `report_text`

Key state:

- `interviewId`
- `currentQuestion`
- `voiceSocket`
- `currentAudio`
- `speaking`
- `phase`
- `transcriptFinal`
- `transcriptInterim`
- `interviewEnded`
- `speechRequestId`

### 5.5 Token Optimization Strategy

Current token minimization approach:

1. Parse resume once
2. Compress resume once
3. Compress JD once
4. Reuse compressed summaries for:
   - 6-question generation
   - turn decisions
   - deferred evaluation
   - final reporting

Why this is production-ready:

- smaller repeated prompts
- more stable latency
- more controlled prompt behavior
- easier observability and prompt debugging

### 5.6 Backward Compatibility Handling

The system supports legacy interview rows where `resume_summary_json` may contain only profile data.

Behavior:

- if `profile` exists, use wrapped payload
- otherwise treat JSON as legacy profile and use empty distilled context

## 6. Runtime Workflow

### Step 1: Upload Resume

1. user uploads resume and JD
2. API stores PDF
3. resume parser extracts structured profile
4. JD analyzer computes skill gap summary
5. context service compresses full resume
6. context service compresses full JD
7. compact context is stored

### Step 2: Start Interview

1. frontend requests interview start
2. interview agent seeds 6 questions if needed
3. first question becomes active
4. TTS reads the first question

### Step 3: Live Interview Loop

1. browser streams mic audio
2. backend proxies to Deepgram
3. Deepgram sends transcript events
4. frontend renders transcript
5. answer is auto-submitted on utterance end
6. interview agent stores answer
7. interviewer decision prompt chooses next action
8. system inserts or moves to next question

### Step 4: End Interview

1. frontend stops speech immediately
2. frontend closes voice capture
3. backend marks report pending

### Step 5: Generate Final Report

1. report service evaluates unscored answers
2. score rows are created
3. full transcript is assembled
4. final report prompt creates interview coach feedback
5. frontend renders the returned text report

## 7. Current Service Ownership Summary

- Resume parsing: [resume_parser.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/resume_parser.py)
- JD analysis: [jd_analyzer.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/jd_analyzer.py)
- Resume/JD compression: [context_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/context_service.py)
- Question generation and turn decisions: [question_generator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/question_generator.py)
- Interview orchestration: [interview_agent.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/interview_agent.py)
- Deferred evaluation: [evaluator.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/evaluator.py)
- Final report generation: [report_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/report_service.py)
- Voice provider integration: [voice_service.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/voice_service.py)
- Shared LLM client: [llm.py](/c:/Users/SuryaD/Desktop/Ai-Interviewer/app/services/llm.py)

## 8. Risks And Known Constraints

- SQLite is acceptable for local/small use but not ideal for high concurrency
- live voice quality still depends on browser mic quality and environment noise
- external provider quality still affects output consistency
- no auth/session ownership yet
- no migration framework yet
- no background report worker yet

## 9. Recommended Next Enhancements

- add authentication and session ownership
- add Alembic migrations
- add automated tests for routes and services
- add retry/timeouts around provider calls
- add structured logging and observability
- move final report generation to a background job if scale grows
- replace placeholder vector memory with persistent retrieval if needed
