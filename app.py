import os
import speech_recognition as sr
from moviepy.editor import VideoFileClip
from flask import Flask, request, render_template, redirect, url_for, flash
import language_tool_python
from textblob import TextBlob
import nltk
from pydub import AudioSegment

nltk.download('punkt')

app = Flask(__name__)
app.secret_key = '2324'  # Change this to a random secret key for security

# Initialize grammar tool
tool = language_tool_python.LanguageTool('en-US')

# List of common filler words
filler_words = [
    "um", "uh", "like", "you know", "so", "actually", "basically", "literally",
    "kind of", "sort of", "you see", "I mean", "well", "hmm", "ah", "er", "uhm",
    "right", "you know what I mean", "you know what I'm saying", "okay", "yeah",
    "totally", "just", "really", "maybe", "kinda", "sorta", "anyway", "I guess",
    "I suppose", "I dunno", "alright", "or something", "stuff like that", "and all that",
    "whatever", "probably", "I think", "to be honest", "honestly", "let’s see"
]

# Function to extract audio from video and save it as a .wav file
def extract_audio_from_video(video_path, audio_output_path):
    try:
        video_clip = VideoFileClip(video_path)
        if video_clip.audio is None:
            video_clip.close()
            return False

        audio_clip = video_clip.audio
        audio_clip.write_audiofile(audio_output_path)
        duration = audio_clip.duration  # Get duration of the audio
        video_clip.close()

        return os.path.exists(audio_output_path), duration
    except Exception as e:
        return False, 0

# Function to convert audio to text using SpeechRecognition
def audio_to_text(audio_path):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_path) as audio_file:
            audio_data = recognizer.record(audio_file)
            text = recognizer.recognize_google(audio_data)
            return text
    except sr.UnknownValueError:
        return "Google Speech Recognition could not understand the audio"
    except sr.RequestError:
        return "Could not request results from Google Speech Recognition service"
    except Exception as e:
        return "Error converting audio to text"

# Function to detect filler words in the transcription
def detect_filler_words(transcription):
    words = transcription.lower().split()
    filler_word_count = {word: words.count(word) for word in filler_words if word in words}
    total_filler_words = sum(filler_word_count.values())
    return filler_word_count, total_filler_words

# Function for Emotion and Tone Analysis
def analyze_emotion_and_tone(transcription):
    blob = TextBlob(transcription)
    polarity = blob.sentiment.polarity
    subjectivity = blob.sentiment.subjectivity

    if polarity > 0.5:
        tone = "Positive"
    elif polarity < -0.5:
        tone = "Negative"
    else:
        tone = "Neutral"

    emotion_feedback = f"The emotional tone of the speech is {tone}."
    return tone, polarity, subjectivity, emotion_feedback

# Function to provide pronunciation feedback based on transcription
def get_pronunciation_feedback(total_words, grammar_score, average_sentence_length):
    if total_words < 5:
        return "Poor pronunciation, unable to transcribe properly.", 50
    elif grammar_score > 90 and average_sentence_length > 5:
        return "Good pronunciation with clear speech.", 90
    elif grammar_score > 75:
        return "Pronunciation is understandable but could be clearer.", 75
    else:
        return "Pronunciation is unclear, affecting accuracy.", 60

# Function to evaluate speech quality and return specific grammar mistakes
def evaluate_speech_quality(transcription, audio_duration):
    matches = tool.check(transcription)

    # Filter out unwanted error messages and prepare grammar mistakes
    grammar_mistakes = []
    for match in matches:
        # Filter out unwanted error messages
        if not any(keyword in match.message.lower() for keyword in ["comma", "hyphen"]):
            grammar_mistakes.append({
                'sentence': transcription[max(0, match.offset - 30):min(len(transcription), match.offset + 30)],
                'error': match.message,
                'suggestion': match.replacements
            })

    # Now calculate grammar issues based on filtered mistakes
    grammar_issues = len(grammar_mistakes)
    total_words = len(transcription.split())
    grammar_score = max(0, 100 - (grammar_issues / total_words) * 100)

    blob = TextBlob(transcription)
    sentence_count = len(blob.sentences)
    average_sentence_length = total_words / max(1, sentence_count)

    pronunciation_feedback, pronunciation_score = get_pronunciation_feedback(total_words, grammar_score, average_sentence_length)

    final_score = (grammar_score + pronunciation_score) / 2

    # Format scores to three decimal places
    grammar_score = round(grammar_score, 3)
    final_score = round(final_score, 3)

    filler_word_count, total_filler_words = detect_filler_words(transcription)
    filler_word_feedback = f"Filler words detected: {total_filler_words}. Filler words used: {filler_word_count}"

    tone, polarity, subjectivity, emotion_feedback = analyze_emotion_and_tone(transcription)

    # Calculate pace (words per minute)
    wpm = (total_words / audio_duration) * 60 if audio_duration > 0 else 0
    pace_feedback = f"Pace: {wpm:.2f} words per minute."

    feedback = {
        'grammar_issues': grammar_issues,  # Now correctly reflects the count of filtered grammar issues
        'grammar_mistakes': grammar_mistakes,  # Adding detailed grammar issues
        'grammar_score': grammar_score,
        'pronunciation_feedback': pronunciation_feedback,
        'pronunciation_score': pronunciation_score,
        'total_filler_words': total_filler_words,
        'filler_word_feedback': filler_word_feedback,
        'emotion_feedback': emotion_feedback,
        'final_score': final_score,
        'pace_feedback': pace_feedback,  # Adding pace feedback
        'wpm': wpm  # WPM value
    }
    return feedback


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    

    

    if file:
        video_path = os.path.join('uploads', file.filename)
        file.save(video_path)

        audio_output_path = os.path.join('uploads', f"{os.path.splitext(file.filename)[0]}.wav")
        
        audio_extracted, duration = extract_audio_from_video(video_path, audio_output_path)
        if audio_extracted:
            text = audio_to_text(audio_output_path)
            
            # Save the transcript to a .txt file
            transcript_path = os.path.join('uploads', f"{os.path.splitext(file.filename)[0]}.txt")
            with open(transcript_path, "w") as transcript_file:
                transcript_file.write(text)

            feedback = evaluate_speech_quality(text, duration)

            return render_template('results.html', file_name=file.filename, feedback=feedback)

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
