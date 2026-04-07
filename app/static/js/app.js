const state = {
  interviewId: null,
  candidateName: "",
  currentQuestion: null,
  totalQuestions: 0,
  mediaRecorder: null,
  mediaStream: null,
  voiceSocket: null,
  currentAudio: null,
  speaking: false,
  phase: "idle",
  transcriptFinal: "",
  transcriptInterim: "",
  awaitingAnswerSubmission: false,
  voiceReady: false,
  interviewEnded: false,
  speechRequestId: 0,
};

const elements = {
  form: document.getElementById("upload-form"),
  resume: document.getElementById("resume"),
  jobDescription: document.getElementById("job-description"),
  resumeSummary: document.getElementById("resume-summary"),
  startBtn: document.getElementById("start-btn"),
  endBtn: document.getElementById("end-btn"),
  submitBtn: document.getElementById("submit-btn"),
  reportBtn: document.getElementById("report-btn"),
  answerBox: document.getElementById("answer-box"),
  voiceWave: document.getElementById("voice-wave"),
  voiceState: document.getElementById("voice-state"),
  stateDetail: document.getElementById("state-detail"),
  candidateName: document.getElementById("candidate-name"),
  interviewId: document.getElementById("interview-id"),
  questionCounter: document.getElementById("question-counter"),
  interviewStatus: document.getElementById("interview-status"),
  questionText: document.getElementById("question-text"),
  questionFocus: document.getElementById("question-focus"),
  scoreCorrectness: document.getElementById("score-correctness"),
  scoreClarity: document.getElementById("score-clarity"),
  scoreDepth: document.getElementById("score-depth"),
  scoreOverall: document.getElementById("score-overall"),
  answerFeedback: document.getElementById("answer-feedback"),
  reportOutput: document.getElementById("report-output"),
};

function setVoiceState(mode, title, detail) {
  elements.voiceWave.dataset.state = mode;
  elements.voiceState.textContent = title;
  elements.stateDetail.textContent = detail;
}

function updateQuestion(question) {
  state.currentQuestion = question;
  if (!question) {
    elements.questionText.textContent = "Interview complete.";
    elements.questionFocus.textContent = "Generating the final report is the only remaining step.";
    return;
  }
  elements.questionText.textContent = question.prompt;
  elements.questionFocus.textContent = question.expected_focus;
  elements.questionCounter.textContent = `${question.sequence} / ${state.totalQuestions}`;
}

function resetTranscript() {
  state.transcriptFinal = "";
  state.transcriptInterim = "";
  elements.answerBox.value = "";
}

function renderTranscript() {
  const fullTranscript = `${state.transcriptFinal} ${state.transcriptInterim}`.trim();
  elements.answerBox.value = fullTranscript;
}

function looksLikeSpeech(text) {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!/[a-z0-9]/i.test(normalized)) {
    return false;
  }
  const words = normalized.split(" ").filter(Boolean);
  return words.length >= 2 || normalized.length >= 8;
}

function stopSpeaking(updateState = true) {
  state.speechRequestId += 1;
  if (state.currentAudio) {
    state.currentAudio.pause();
    state.currentAudio.currentTime = 0;
    state.currentAudio = null;
  }
  state.speaking = false;
  if (updateState) {
    state.phase = "listening";
    setVoiceState("listening", "Listening", "Model speech stopped. Listening to the candidate now.");
  }
}

function shutdownVoiceCapture() {
  stopSpeaking(false);
  if (state.voiceSocket && state.voiceSocket.readyState === WebSocket.OPEN) {
    state.voiceSocket.send("close");
    state.voiceSocket.close();
  }
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
  }
  state.voiceSocket = null;
  state.mediaStream = null;
  state.mediaRecorder = null;
  state.voiceReady = false;
}

function formatReportText(report) {
  if (report.report_text) {
    return report.report_text;
  }
  const lines = [
    `Candidate: ${report.candidate_name}`,
    `Status: ${report.status}`,
    `Recommendation: ${report.hiring_recommendation}`,
    "",
    "Strengths:",
    ...(report.strengths.length ? report.strengths.map((item) => `- ${item}`) : ["- None"]),
    "",
    "Weaknesses:",
    ...(report.weaknesses.length ? report.weaknesses.map((item) => `- ${item}`) : ["- None"]),
    "",
    "Skill Gaps:",
    ...(report.skill_gaps.length ? report.skill_gaps.map((item) => `- ${item}`) : ["- None"]),
    "",
    "Answer Feedback:",
  ];

  if (!report.answered_questions.length) {
    lines.push("- No answers were recorded.");
    return lines.join("\n");
  }

  report.answered_questions.forEach((item, index) => {
    lines.push(`Q${index + 1}: ${item.question}`);
    lines.push(`Answer: ${item.answer}`);
    lines.push(`Feedback: ${item.score.feedback}`);
    lines.push("");
  });

  return lines.join("\n").trim();
}

async function speakQuestion(text) {
  if (!text || state.interviewEnded) {
    return;
  }

  stopSpeaking(false);
  const requestId = state.speechRequestId;
  resetTranscript();
  state.phase = "processing";
  setVoiceState("processing", "Loading Voice", "Generating interview audio with Deepgram.");

  const formData = new FormData();
  formData.append("text", text);
  const response = await fetch("/voice/speak", { method: "POST", body: formData });
  if (requestId !== state.speechRequestId || state.interviewEnded) {
    return;
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    state.phase = "listening";
    setVoiceState("listening", "Listening", data.detail || "Voice synthesis failed. Listening continues.");
    return;
  }

  const blob = await response.blob();
  if (requestId !== state.speechRequestId || state.interviewEnded) {
    return;
  }
  const audioUrl = URL.createObjectURL(blob);
  const audio = new Audio(audioUrl);
  state.currentAudio = audio;
  state.speaking = true;
  state.phase = "speaking";

  audio.onplay = () => {
    setVoiceState("speaking", "Speaking", "The interviewer is asking the next question.");
  };
  audio.onended = () => {
    state.speaking = false;
    state.currentAudio = null;
    URL.revokeObjectURL(audioUrl);
    state.phase = "listening";
    setVoiceState("listening", "Listening", "Question finished. Listening for your answer.");
  };
  audio.onerror = () => {
    state.speaking = false;
    state.currentAudio = null;
    URL.revokeObjectURL(audioUrl);
    state.phase = "listening";
    setVoiceState("listening", "Listening", "Audio playback failed. Listening for your answer.");
  };

  await audio.play().catch(() => {
    state.speaking = false;
    state.currentAudio = null;
    URL.revokeObjectURL(audioUrl);
    state.phase = "listening";
    setVoiceState("listening", "Listening", "Autoplay was blocked. Listening for your answer.");
  });
}

function handleTranscriptMessage(data) {
  if (state.phase === "processing" && !state.speaking) {
    return;
  }

  if (data.type === "Results") {
    const transcript = data.channel?.alternatives?.[0]?.transcript?.trim() || "";
    if (looksLikeSpeech(transcript) && state.speaking) {
      stopSpeaking(true);
    }

    if (data.is_final && transcript) {
      state.transcriptFinal = `${state.transcriptFinal} ${transcript}`.trim();
      state.transcriptInterim = "";
    } else {
      state.transcriptInterim = transcript;
    }
    renderTranscript();

    if (data.speech_final) {
      const finalText = `${state.transcriptFinal} ${state.transcriptInterim}`.trim();
      state.transcriptInterim = "";
      renderTranscript();
      if (looksLikeSpeech(finalText) && !state.awaitingAnswerSubmission) {
        state.awaitingAnswerSubmission = true;
        submitAnswer(finalText, "deepgram_stream").finally(() => {
          state.awaitingAnswerSubmission = false;
        });
      }
    }
    return;
  }

  if (data.type === "UtteranceEnd") {
    const finalText = `${state.transcriptFinal} ${state.transcriptInterim}`.trim();
    state.transcriptInterim = "";
    renderTranscript();
    if (looksLikeSpeech(finalText) && !state.awaitingAnswerSubmission) {
      state.awaitingAnswerSubmission = true;
      submitAnswer(finalText, "deepgram_stream").finally(() => {
        state.awaitingAnswerSubmission = false;
      });
    }
    return;
  }

  if (data.type === "Error") {
    setVoiceState("idle", "Voice Error", data.detail || "Voice streaming failed.");
  }
}

function connectVoiceSocket() {
  return new Promise((resolve, reject) => {
    if (state.voiceSocket && state.voiceSocket.readyState === WebSocket.OPEN) {
      resolve();
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/voice`);
    state.voiceSocket = socket;

    socket.onopen = () => {
      state.voiceReady = true;
      resolve();
    };

    socket.onmessage = (event) => {
      try {
        handleTranscriptMessage(JSON.parse(event.data));
      } catch {
        setVoiceState("idle", "Voice Error", "Received an unreadable voice event.");
      }
    };

    socket.onerror = () => {
      state.voiceReady = false;
      reject(new Error("Voice socket failed."));
    };

    socket.onclose = () => {
      state.voiceReady = false;
    };
  });
}

async function ensureVoiceCapture() {
  if (state.mediaRecorder && state.voiceReady) {
    return true;
  }

  try {
    await connectVoiceSocket();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const preferredMimeType = typeof MediaRecorder.isTypeSupported === "function" &&
      MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "";
    const recorder = preferredMimeType
      ? new MediaRecorder(stream, { mimeType: preferredMimeType })
      : new MediaRecorder(stream);

    recorder.ondataavailable = async (event) => {
      if (!event.data || event.data.size === 0 || !state.voiceSocket || state.voiceSocket.readyState !== WebSocket.OPEN) {
        return;
      }
      const arrayBuffer = await event.data.arrayBuffer();
      state.voiceSocket.send(arrayBuffer);
    };

    recorder.start(250);
    state.mediaStream = stream;
    state.mediaRecorder = recorder;
    state.phase = "listening";
    setVoiceState("listening", "Listening", "Microphone is live. The interview is hands-free now.");
    return true;
  } catch {
    setVoiceState("idle", "Voice Unavailable", "Microphone or Deepgram streaming could not be started.");
    return false;
  }
}

async function uploadResume(event) {
  event.preventDefault();
  const file = elements.resume.files[0];
  if (!file) return;

  setVoiceState("processing", "Processing", "Parsing resume and comparing it with the job description.");

  const formData = new FormData();
  formData.append("resume", file);
  formData.append("job_description", elements.jobDescription.value);

  const response = await fetch("/upload_resume", { method: "POST", body: formData });
  const data = await response.json();
  if (!response.ok) {
    elements.resumeSummary.textContent = data.detail || "Resume upload failed.";
    setVoiceState("idle", "Ready", "Please fix the upload issue and try again.");
    return;
  }

  state.interviewId = data.interview_id;
  state.candidateName = data.candidate_name;
  state.interviewEnded = false;
  elements.candidateName.textContent = data.candidate_name;
  elements.interviewId.textContent = String(data.interview_id);
  elements.interviewStatus.textContent = "Resume analyzed";
  elements.resumeSummary.textContent =
    `Matched skills: ${data.matched_skills.join(", ") || "None"}\n` +
    `Missing skills: ${data.missing_skills.join(", ") || "None"}\n` +
    `Projects found: ${data.resume_profile.projects.join(" | ") || "None"}`;
  elements.startBtn.disabled = false;
  elements.endBtn.disabled = true;
  elements.reportBtn.disabled = true;
  elements.scoreCorrectness.textContent = "-";
  elements.scoreClarity.textContent = "-";
  elements.scoreDepth.textContent = "-";
  elements.scoreOverall.textContent = "-";
  elements.answerFeedback.textContent = "Answer evaluation will be generated after the interview ends.";
  setVoiceState("idle", "Ready", "Resume analysis is complete. Start the interview to enable live voice mode.");
}

async function startInterview() {
  if (!state.interviewId) return;
  state.interviewEnded = false;
  setVoiceState("processing", "Preparing", "Generating interview questions and starting live voice mode.");

  const voiceReady = await ensureVoiceCapture();
  if (!voiceReady) {
    return;
  }

  const response = await fetch("/start_interview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interview_id: state.interviewId }),
  });
  const data = await response.json();
  if (!response.ok) {
    setVoiceState("idle", "Ready", data.detail || "Failed to start interview.");
    return;
  }

  state.totalQuestions = data.total_questions;
  elements.interviewStatus.textContent = data.status;
  elements.startBtn.disabled = true;
  elements.endBtn.disabled = false;
  elements.reportBtn.disabled = true;
  updateQuestion(data.current_question);
  await speakQuestion(data.current_question.prompt);
}

async function submitAnswer(answerText, transcriptSource = "text") {
  if (!state.interviewId || !state.currentQuestion) return;
  if (!answerText.trim()) return;
  if (state.interviewEnded) return;

  state.phase = "processing";
  state.transcriptFinal = answerText.trim();
  state.transcriptInterim = "";
  renderTranscript();
  setVoiceState("processing", "Saving", "Saving your answer and preparing the next question.");

  const response = await fetch("/submit_answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      interview_id: state.interviewId,
      question_id: state.currentQuestion.question_id,
      answer: answerText,
      transcript_source: transcriptSource,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    state.phase = "listening";
    setVoiceState("listening", "Listening", data.detail || "Failed to submit answer.");
    return;
  }

  elements.interviewStatus.textContent = data.status;
  elements.answerFeedback.textContent = "Per-question evaluation is deferred until the final report.";

  if (data.next_question) {
    if (data.follow_up_generated) {
      state.totalQuestions = Math.max(state.totalQuestions, data.next_question.sequence);
    }
    updateQuestion(data.next_question);
    await speakQuestion(data.next_question.prompt);
  } else {
    updateQuestion(null);
    shutdownVoiceCapture();
    elements.endBtn.disabled = true;
    elements.reportBtn.disabled = false;
    state.phase = "idle";
    setVoiceState("idle", "Completed", "Interview finished. Generating the final report is available now.");
  }
}

async function endInterview() {
  if (!state.interviewId) return;
  state.interviewEnded = true;
  shutdownVoiceCapture();
  setVoiceState("processing", "Ending", "Ending the interview and unlocking report generation.");

  const response = await fetch("/end_interview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interview_id: state.interviewId }),
  });
  const data = await response.json();
  if (!response.ok) {
    setVoiceState("idle", "Ready", data.detail || "Failed to end interview.");
    return;
  }

  state.phase = "idle";
  updateQuestion(null);
  elements.interviewStatus.textContent = data.status;
  elements.endBtn.disabled = true;
  elements.reportBtn.disabled = false;
  elements.answerFeedback.textContent = "Interview ended. Generate the report to score all answers together.";
  setVoiceState("idle", "Interview Ended", "You can generate the final report now.");
}

async function generateReport() {
  if (!state.interviewId) return;
  setVoiceState("processing", "Reporting", "Building the final hiring summary.");
  const response = await fetch(`/get_report?interview_id=${state.interviewId}`);
  const data = await response.json();
  if (!response.ok) {
    setVoiceState("idle", "Ready", data.detail || "Report generation failed.");
    return;
  }

  elements.scoreCorrectness.textContent = data.average_scores.correctness.toFixed(1);
  elements.scoreClarity.textContent = data.average_scores.clarity.toFixed(1);
  elements.scoreDepth.textContent = data.average_scores.depth.toFixed(1);
  elements.scoreOverall.textContent = data.average_scores.overall.toFixed(1);
  elements.answerFeedback.textContent = `Recommendation: ${data.hiring_recommendation}`;
  elements.reportOutput.textContent = formatReportText(data);
  elements.interviewStatus.textContent = data.status;
  setVoiceState("idle", "Report Ready", "Review the final interview outcome below.");
}

elements.form.addEventListener("submit", uploadResume);
elements.startBtn.addEventListener("click", startInterview);
elements.endBtn.addEventListener("click", endInterview);
elements.submitBtn.addEventListener("click", () => submitAnswer(elements.answerBox.value, "manual_text"));
elements.reportBtn.addEventListener("click", generateReport);
window.addEventListener("beforeunload", () => {
  shutdownVoiceCapture();
});
