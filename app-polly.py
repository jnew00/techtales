import os
import uuid
import json
import boto3
import whisper
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)
UPLOAD_FOLDER = "static"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# AWS Clients
bedrock = boto3.client("bedrock-runtime", region_name="us-east-2")
dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
polly = boto3.client("polly", region_name="us-east-2")
model_id = "arn:aws:bedrock:us-east-2:827124175283:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"
table = dynamodb.Table("ConversationHistory")  # Table should exist

# Load whisper model
whisper_model = whisper.load_model("base")

# Routes
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)

@app.route("/intro", methods=["POST"])
def intro():
    voice_id = request.json.get("voice_id", "Joanna")
    # intro_text = f"Hello, I'm {voice_id}, your interviewer for a podcast called TechTales. Please tell us a little about yourself and what you want to talk about today."
    intro_text = f"Hello"

    polly_response = polly.synthesize_speech(
        Engine="standard",
        OutputFormat="mp3",
        VoiceId=voice_id,
        Text=intro_text
    )

    filename = f"{uuid.uuid4()}_intro.mp3"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    with open(filepath, "wb") as f:
        f.write(polly_response["AudioStream"].read())

    return jsonify({"audio_url": f"/static/{filename}"})


@app.route("/process", methods=["POST"])
def process():
    session_id = request.form.get("session_id", f"session-{uuid.uuid4()}")
    voice_id = request.form.get("voice_id", "Joanna")
    audio_file = request.files["audio"]

    audio_path = os.path.join(UPLOAD_FOLDER, "temp_audio.webm")
    audio_file.save(audio_path)

    result = whisper_model.transcribe(audio_path)
    transcript = result["text"]

    save_message(session_id, "user", transcript)

    conversation = load_conversation(session_id)
    if len(conversation) == 1:
        conversation = [{"role": "user", "content": [{"type": "text", "text": transcript}]}]

    response_text = chat_with_claude(conversation, voice_id)
    save_message(session_id, "assistant", response_text)

    polly_response = polly.synthesize_speech(
        Engine="standard",
        OutputFormat="mp3",
        VoiceId=voice_id,
        Text=response_text
    )

    audio_filename = f"{uuid.uuid4()}.mp3"
    audio_filepath = os.path.join(UPLOAD_FOLDER, audio_filename)
    with open(audio_filepath, "wb") as f:
        f.write(polly_response["AudioStream"].read())

    return jsonify({
        "transcript": transcript,
        "response": response_text,
        "audio_url": f"/static/{audio_filename}",
        "audio_id": f"audio-{uuid.uuid4()}"
    })


# Claude + Dynamo functions
def chat_with_claude(messages, voice_id):
    # Determine style prompt based on voice
    style_prompts = {
        "Joanna": "You are Joanna, a warm and thoughtful podcast interviewer with a knack for drawing out personal stories. ",
        "Matthew": "You're Matthew, a bold, funky host with a loud laugh and a love of tangents. Keep things lively! ",
        "Ivy": "You're Ivy, introspective and poetic. You ask questions like a spoken word artist probing for deeper truths. ",
        "Brian": "You're Brian, a laid-back, sarcastic host who keeps it casual but insightful and speaks like Seinfeld.",
        "Amy": "You're Amy, curious and enthusiastic, with a contagious energy and lots of follow-ups."
    }
    default_prompt = "You are an interviewer for a podcast. Keep responses brief (1-2 sentences), ask insightful follow-up questions, and stay on topic unless the user signals otherwise. Avoid rambling or unnecessary elaboration."
    voice_style = style_prompts.get(voice_id, "")
    system_prompt = f"{voice_style} {default_prompt}"

        # Remove any system message from the messages list
    filtered_messages = [m for m in messages if m.get("role") != "system"]
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "temperature": 0.7,
        "system": system_prompt,
        "messages": filtered_messages
    }
    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )
    result = json.loads(response['body'].read())
    return result['content'][0]['text']

def load_conversation(session_id):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("SessionId").eq(session_id),
            ScanIndexForward=True
        )
        items = response.get("Items", [])
        return [
            {"role": item["Role"], "content": [{"type": "text", "text": item["Message"]}]}
            for item in items
        ]
    except Exception as e:
        print("Error loading conversation:", e)
        return []

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
        print("Error saving message:", e)


if __name__ == "__main__":
    app.run(debug=True)