const recordBtn = document.getElementById("recordBtn");
const transcriptEl = document.getElementById("transcript");
const responseEl = document.getElementById("response");
const audioPlayer = document.getElementById("audioPlayer");

let mediaRecorder;
let chunks = [];

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

      const res = await fetch("/process", {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      transcriptEl.textContent = data.transcript;
      responseEl.textContent = data.response;
      audioPlayer.src = data.audio_url;
      audioPlayer.style.display = "block";
      audioPlayer.play();
    };
  } else {
    mediaRecorder.stop();
    recordBtn.textContent = "🎙️ Start Recording";
  }
});