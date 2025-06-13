import os
import uuid
import json
import boto3
import whisper
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, send_from_directory
from boto3.dynamodb.conditions import Key

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
            KeyConditionExpression=Key("SessionId").eq(session_id),
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


# End Conversation Route
@app.route("/end", methods=["POST"])
def end_conversation():
    session_id = request.json.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    try:
        items = load_conversation_from_dynamo(session_id)
        transcript_text = flatten_messages(items)
        print("TRANSCRIPT TEXT:\n", transcript_text)

        summary_text = summarize_conversation(transcript_text)
        print("RAW SUMMARY TEXT:\n", summary_text)
        summary_text = summary_text.strip()
        if summary_text.startswith("```json"):
            summary_text = summary_text.replace("```json", "").replace("```", "").strip()
        json_data = json.loads(summary_text)
        # Debug: Print parsed keys and structure of emotional themes
        print("Parsed JSON keys:", json_data.keys())
        for theme in json_data.get("emotional_themes", []):
            print("Theme entry:", theme)

        return jsonify(json_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# Helper functions for end conversation
def load_conversation_from_dynamo(session_id):
    response = table.query(
        KeyConditionExpression=Key("SessionId").eq(session_id),
        ScanIndexForward=True
    )
    items = response.get("Items", [])
    if not items:
        raise ValueError(f"No conversation found for SessionId: {session_id}")
    return items

def flatten_messages(items):
    transcript = ""
    for item in items:
        role = item.get("Role", "user").capitalize()
        message = item.get("Message", "").strip()
        transcript += f"{role}: {message}\n"
    return transcript

def summarize_conversation(transcript_text):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.5,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f'''
Here is a transcript of a storytelling conversation.

Return a JSON object with the following structure:
{{
  "summary": "A 3–4 sentence summary of the story.",
  "tags": ["tag1", "tag2", "tag3", ...],
  "emotional_themes": [
    {{
      "theme": "A short, clearly defined emotion or psychological theme (e.g., 'Pride in accomplishment', 'Playful testing', 'Affectionate frustration')",
      "description": "A one-sentence explanation summarizing how this theme appears in the conversation."
    }},
    ...
  ],
  "title": "One-sentence story title"
}}

Transcript:
{transcript_text}
'''
                    }
                ]
            }
        ]
    }

    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )

    try:
        result = json.loads(response["body"].read())
        content_blocks = result.get("content", [])
        if not content_blocks or "text" not in content_blocks[0]:
            raise ValueError("Claude returned empty or malformed response")
        return content_blocks[0]["text"]
    except Exception as e:
        print("ERROR parsing Claude response:", e)
        print("RAW response:", response)
        raise


if __name__ == "__main__":
    app.run(debug=True)