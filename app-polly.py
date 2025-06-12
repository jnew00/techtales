from flask import Flask, request, render_template, send_file
import boto3
import whisper
import uuid
import os
import json

app = Flask(__name__)
whisper_model = whisper.load_model("base")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-2")
polly = boto3.client("polly", region_name="us-east-1")

AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

CLAUDE_MODEL = "arn:aws:bedrock:us-east-2:827124175283:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    file = request.files["audio"]
    filename = f"{uuid.uuid4()}.webm"
    filepath = os.path.join(AUDIO_DIR, filename)
    file.save(filepath)

    # Transcribe
    result = whisper_model.transcribe(filepath)
    user_input = result["text"]

    # Claude response
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": user_input}]
    }
    response = bedrock.invoke_model(
        modelId=CLAUDE_MODEL,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    claude_reply = json.loads(response["body"].read())["content"][0]["text"]

    # Polly TTS
    mp3_filename = f"{uuid.uuid4()}.mp3"
    mp3_path = os.path.join(AUDIO_DIR, mp3_filename)
    polly_response = polly.synthesize_speech(
        Text=claude_reply,
        OutputFormat="mp3",
        VoiceId="Emma",
        Engine="neural"
    )
    with open(mp3_path, "wb") as f:
        f.write(polly_response["AudioStream"].read())

    return { "audio_url": f"/audio/{mp3_filename}", "transcript": user_input, "response": claude_reply }

@app.route("/audio/<filename>")
def audio(filename):
    return send_file(os.path.join(AUDIO_DIR, filename), mimetype="audio/mpeg")
    
if __name__ == "__main__":
    app.run(debug=True)