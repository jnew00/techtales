from flask import Flask, request, render_template, send_file
import boto3
import whisper
import uuid
import os
import json
from datetime import datetime, timezone

app = Flask(__name__)
AUDIO_DIR = "audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# AWS Clients
region = "us-east-2"
bedrock = boto3.client("bedrock-runtime", region_name=region)
polly = boto3.client("polly", region_name="us-east-1")  # neural support
dynamodb = boto3.resource("dynamodb", region_name=region)

# Models & Tables
whisper_model = whisper.load_model("base")
model_id = "arn:aws:bedrock:us-east-2:827124175283:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"
table = dynamodb.Table("ConversationHistory")

# === DynamoDB conversation functions ===

def save_message(session_id, role, message_text):
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        table.put_item(Item={
            "SessionId": session_id,
            "Timestamp": timestamp,
            "Role": role,
            "Message": message_text
        })
    except Exception as e:
        print("❌ Error saving to DynamoDB:", e)

def load_conversation(session_id):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('SessionId').eq(session_id),
            ScanIndexForward=True
        )
        items = response.get("Items", [])
        return [
            {
                "role": item["Role"],
                "content": [{"type": "text", "text": item["Message"]}]
            }
            for item in items
        ]
    except Exception as e:
        print("❌ Error loading from DynamoDB:", e)
        return []

def chat_with_claude(messages):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.7,
        "messages": messages
    }
    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )
    result = json.loads(response['body'].read())
    return result['content'][0]['text']

# === Routes ===

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    voice_id = request.form.get("voice_id", "Joanna") 
    file = request.files["audio"]
    session_id = request.form.get("session_id", "default-session")

    # Save & transcribe
    filename = f"{uuid.uuid4()}.webm"
    filepath = os.path.join(AUDIO_DIR, filename)
    file.save(filepath)
    result = whisper_model.transcribe(filepath)
    user_input = result["text"].strip()

    # Save user message
    save_message(session_id, "user", user_input)

    # Fetch conversation, fallback if first
    convo = load_conversation(session_id)
    if len(convo) == 1:
        convo = [{"role": "user", "content": [{"type": "text", "text": user_input}]}]

    # Claude response
    claude_reply = chat_with_claude(convo)
    save_message(session_id, "assistant", claude_reply)

    # Polly synthesis
    mp3_filename = f"{uuid.uuid4()}.mp3"
    mp3_path = os.path.join(AUDIO_DIR, mp3_filename)
    polly_response = polly.synthesize_speech(
        Text=claude_reply,
        OutputFormat="mp3",
        VoiceId=voice_id,
        Engine="neural"
    )
    with open(mp3_path, "wb") as f:
        f.write(polly_response["AudioStream"].read())

    return {
        "audio_url": f"/audio/{mp3_filename}",
        "transcript": user_input,
        "response": claude_reply
    }

@app.route("/audio/<filename>")
def audio(filename):
    return send_file(os.path.join(AUDIO_DIR, filename), mimetype="audio/mpeg")

if __name__ == "__main__":
    app.run(debug=True)