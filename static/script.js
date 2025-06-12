const recordBtn = document.getElementById("recordBtn");
const startBtn = document.getElementById("startBtn");
const transcriptEl = document.getElementById("transcript");
const responseEl = document.getElementById("response");
const audioPlayer = document.getElementById("audioPlayer");
const introAudio = document.getElementById("introAudio");
const voiceSelect = document.getElementById("voiceSelect");

let mediaRecorder;
let chunks = [];

function getSessionId() {
  let sessionId = localStorage.getItem("session_id");
  if (!sessionId) {
    sessionId = "session-" + Date.now() + "-" + Math.floor(Math.random() * 100000);
    localStorage.setItem("session_id", sessionId);
  }
  return sessionId;
}

// 🎬 Intro playback from backend
startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  const voice = voiceSelect.value;

  const res = await fetch("/intro", {
    method: "POST",
    body: JSON.stringify({ voice_id: voice }),
    headers: { "Content-Type": "application/json" }
  });

  const data = await res.json();
  introAudio.src = data.audio_url;
  introAudio.style.display = "block";
  introAudio.play();
  introAudio.onended = () => {
    recordBtn.style.display = "inline-block";
  };
});

// 🎙️ Recording flow
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