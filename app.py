from flask import Flask, request, jsonify
from flask_cors import CORS
import whisper
import boto3
import json
import os
from datetime import datetime
from tempfile import NamedTemporaryFile

app = Flask(__name__)
CORS(app)

# Load Whisper model once
model = whisper.load_model("base")

# AWS Bedrock
region = "us-east-2"
bedrock = boto3.client("bedrock-runtime", region_name=region)
model_id = "arn:aws:bedrock:us-east-2:827124175283:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"

@app.route("/transcribe", methods=["POST"])
def transcribe_and_respond():
    audio = request.data
    with NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
        tmpfile.write(audio)
        tmpfile.flush()
        result = model.transcribe(tmpfile.name, fp16=False)
        text = result["text"].strip()
        os.remove(tmpfile.name)

    # Claude
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}]
    }

    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )
    result = json.loads(response["body"].read())
    reply = result["content"][0]["text"]

    return jsonify({"transcript": text, "reply": reply})

if __name__ == "__main__":
    app.run(debug=True)