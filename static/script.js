const recordBtn = document.getElementById("recordBtn");
const transcriptEl = document.getElementById("transcript");
const responseEl = document.getElementById("response");
const audioPlayer = document.getElementById("audioPlayer");
const voiceSelect = document.getElementById("voiceSelect");

let mediaRecorder;
let chunks = [];

// Get or create session ID
function getSessionId() {
  let sessionId = localStorage.getItem("session_id");
  if (!sessionId) {
    sessionId = "session-" + Date.now() + "-" + Math.floor(Math.random() * 100000);
    localStorage.setItem("session_id", sessionId);
  }
  return sessionId;
}

// 🎤 Voice prompt on load
window.addEventListener("DOMContentLoaded", () => {
  const welcome = "To start, please tell us a little about yourself and what you want to talk about today. We're excited to hear your story.";

  const speakWelcome = () => {
    const selectedVoice = voiceSelect.value;
    const utterance = new SpeechSynthesisUtterance(welcome);
    utterance.lang = "en-US";
    utterance.pitch = 1;
    utterance.rate = 1;
    utterance.voice = speechSynthesis.getVoices().find(v => v.name.includes(selectedVoice)) || null;
    speechSynthesis.speak(utterance);
  };

  // Wait for voices to load
  if (speechSynthesis.getVoices().length === 0) {
    speechSynthesis.onvoiceschanged = speakWelcome;
  } else {
    speakWelcome();
  }
});

// 🎙️ Start/Stop Recording
recordBtn.addEventListener("click", async () => {
  if (!mediaRecorder || mediaRecorder.state === "inactive") {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.start();
    recordBtn.textContent = "⏹️ Stop Recording";
    chunks = [];

    mediaRecorder.ondataavailable = e => chunks.push(e.data);

    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("audio", blob, "input.webm");
      formData.append("session_id", getSessionId());
      formData.append("voice_id", voiceSelect.value);

      const res = await fetch("/process", {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      transcriptEl.textContent = data.transcript || "[No transcript returned]";
      responseEl.textContent = data.response || "[No response returned]";
      audioPlayer.src = data.audio_url;
      audioPlayer.style.display = "block";
      audioPlayer.play();
    };
  } else {
    mediaRecorder.stop();
    recordBtn.textContent = "🎙️ Start Recording";
  }
});