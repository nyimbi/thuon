#!/usr/bin/env python3

"""
Audio Logger and Transcriber with Summarization and Notes App Integration (MPS Support)

This script continuously records audio from your macOS computer, transcribes it using
the Whisper model (now with MPS device support for Apple Silicon), logs the transcripts,
and summarizes key information daily and weekly using an on-device Ollama-based LLM.
It also writes daily and weekly summaries to the macOS Notes app in a "Snippets" folder.

Features:
    - Continuous audio recording from all system sources.
    - Transcription using OpenAI's Whisper model, leveraging MPS device (Apple Silicon GPU) if available.
    - 10-minute transcript logging to a timestamped audio log file.
    - End-of-day summarization of transcripts using a local Ollama LLM for:
        - Action points
        - Decisions
        - Key ideas
        - To-dos
    - Daily summary notification.
    - End-of-week highlights document in Markdown format.
    - Writes daily and weekly summaries to macOS Notes App in "Snippets" folder.
    - Organizes notes by week number in subfolders within "Snippets".
    - Designed to run continuously in the background on macOS.

Dependencies:
    - Python 3.7+
    - sounddevice: For audio recording (pip install sounddevice)
    - whisper: For audio transcription (pip install openai-whisper)
    - torch: Required for Whisper MPS support (installed with openai-whisper, but ensure it's installed with MPS support if needed) (pip install torch)
    - ollama: Python library to interact with a local Ollama server (pip install ollama)
    - plyer: For notifications (pip install plyer)
    - schedule: For scheduling tasks (pip install schedule)
    - virtualenv (recommended): For managing Python environment (pip install virtualenv)
    - appscript: For macOS Notes app integration (pip install appscript)

Setup Instructions: (See detailed instructions in previous responses, plus MPS and Notes integration)
1. Install Dependencies (virtualenv recommended): `pip install sounddevice openai-whisper torch ollama plyer schedule appscript`
   - Ensure `torch` is installed correctly with MPS support if you are on Apple Silicon.
     `openai-whisper` generally installs `torch` as a dependency. If you encounter issues,
      refer to PyTorch documentation for MPS setup: https://pytorch.org/get-started/locally/
2. Install and Run Ollama (ensure a model is pulled, e.g., llama2).
3. Install BlackHole (or similar virtual audio device) and configure macOS audio settings.
4. Configure Script Settings in the SCRIPT_CONFIG section below.
5. Run the Script (using screen for background execution is recommended).
6. macOS Notes App Permissions: Grant permissions as described in previous instructions.

Important Notes: (See detailed notes in previous responses, plus MPS note)
    - macOS Privacy: Microphone and Notes access required.
    - Audio Quality: Impacts transcription accuracy.
    - Resource Usage: Can be intensive, MPS can help reduce CPU load for transcription.
    - Error Handling: Basic error handling included.
    - Ollama Model: Choose a suitable model for summarization.
    - Log File Management: Logs will grow.
    - Virtual Audio Device: Critical for system-wide audio capture on macOS.
    - MPS Device: Script will attempt to use MPS if available. Performance benefits may vary
      depending on model size and system load.
"""

import sounddevice as sd
import whisper
import time
import datetime
import os
import logging
from plyer import notification
import schedule
from langchain_ollama.llms import OllamaLLM
import ollama
import markdown
from appscript import *
import torch

# ####################### SCRIPT CONFIGURATION #######################
SCRIPT_CONFIG = {
    "AUDIO_DEVICE_INDEX": None,  # Set to None for default, or find BlackHole's input index using query_devices()
    "SAMPLE_RATE": 16000,
    "RECORD_CHANNELS": 1,  # Mono audio for Whisper
    "BLOCK_DURATION_SECONDS": 10,  # Duration to record and transcribe in each block
    "TRANSCRIPTION_INTERVAL_SECONDS": 600,  # 10 minutes (600 seconds) - how often to save transcript chunk
    "WHISPER_MODEL_NAME": "medium",  # "tiny", "base", "small", "medium", "large" - larger models are more accurate but slower
    "AUDIO_LOG_DIR": "audio_logs",
    "DAILY_SUMMARY_TIME": "23:00",  # Time to perform daily summary (24-hour format)
    "WEEKLY_HIGHLIGHTS_DAY": "Sunday",  # Day of the week for weekly highlights
    "HIGHLIGHTS_OUTPUT_DIR": "weekly_highlights",
    "OLLAMA_MODEL": "qwen2.5",  # Model name in Ollama for summarization
    "NOTIFICATION_TITLE": "Audio Logger",
    "NOTIFICATION_ICON": "icon.png",  # Path to notification icon (optional, place in script directory)
    "NOTES_SNIPPETS_FOLDER_NAME": "Snippets",  # Name of the main folder in Notes app
}
# ####################################################################


def ensure_directories():
    if not os.path.exists(SCRIPT_CONFIG["AUDIO_LOG_DIR"]):
        os.makedirs(SCRIPT_CONFIG["AUDIO_LOG_DIR"])
    if not os.path.exists(SCRIPT_CONFIG["HIGHLIGHTS_OUTPUT_DIR"]):
        os.makedirs(SCRIPT_CONFIG["HIGHLIGHTS_OUTPUT_DIR"])


def get_audio_device_info():
    devices = sd.query_devices()
    print("Available audio devices:")
    for i, device in enumerate(devices):
        print(
            f"Index: {i}, Name: {device['name']}, Input channels: {device['max_input_channels']}, Output channels: {device['max_output_channels']}"
        )


def record_audio(duration, sample_rate, channels, device_index=None):
    try:
        recording = sd.rec(
            int(sample_rate * duration),
            samplerate=sample_rate,
            channels=channels,
            device=device_index,
        )
        sd.wait()
        return recording
    except sd.PortAudioError as e:
        logging.error(f"PortAudioError during recording: {e}")
        return None
    except Exception as e:
        logging.error(f"Error during audio recording: {e}")
        return None


def transcribe_audio(audio, model):
    if audio is None:
        return "No audio recorded."
    try:
        transcript = model.transcribe(audio.flatten())
        print(transcript["text"])   # delete line
        return transcript["text"]
    except Exception as e:
        logging.error(f"Error during transcription: {e}")
        return "Transcription failed."


def save_transcript_to_log(transcript):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = os.path.join(
        SCRIPT_CONFIG["AUDIO_LOG_DIR"],
        f"audio_log_{datetime.datetime.now().strftime('%Y-%m-%d')}.txt",
    )
    try:
        with open(log_filename, "a") as log_file:
            log_file.write(f"[{timestamp}]: {transcript}\n")
        logging.info(f"Transcript saved to log at {timestamp}")
    except Exception as e:
        logging.error(f"Error saving transcript to log: {e}")


def ensure_notes_folders():
    """Ensures the "Snippets" folder and week subfolder exist in Notes app."""
    try:
        notes_app = app("Notes")
        snippets_folder_name = SCRIPT_CONFIG["NOTES_SNIPPETS_FOLDER_NAME"]
        week_folder_name = (
            f"Week {datetime.date.today().isocalendar()[1]}"  # e.g., "Week 44"
        )

        # Check if Snippets folder exists, create if not
        snippets_folder = None
        for folder in notes_app.folders.get():
            if folder.name.get() == snippets_folder_name:
                snippets_folder = folder
                break
        if not snippets_folder:
            snippets_folder = notes_app.make(
                new=k.folder, with_properties={k.name: snippets_folder_name}
            )
            logging.info(f"Created Notes folder: {snippets_folder_name}")

        # Check if week folder exists within Snippets, create if not
        week_folder = None
        for folder in snippets_folder.folders.get():
            if folder.name.get() == week_folder_name:
                week_folder = folder
                break
        if not week_folder:
            week_folder = snippets_folder.make(
                new=k.folder, with_properties={k.name: week_folder_name}
            )
            logging.info(
                f"Created Notes subfolder: {week_folder_name} in {snippets_folder_name}"
            )

        return week_folder

    except Exception as e:
        logging.error(f"Error ensuring Notes folders: {e}")
        return None


def write_daily_summary_to_notes(summary_text):
    """Writes daily summary to Notes app in the week folder."""
    week_folder = ensure_notes_folders()
    if not week_folder:
        logging.error(
            "Week folder not found/created, cannot write daily summary to Notes."
        )
        return

    try:
        note_title = f"Daily Summary {datetime.datetime.now().strftime('%Y-%m-%d')}"
        new_note = week_folder.make(
            new=k.note, with_properties={k.name: note_title, k.body: summary_text}
        )
        logging.info(
            f"Daily summary written to Notes: {note_title} in {week_folder.name.get()}"
        )
    except Exception as e:
        logging.error(f"Error writing daily summary to Notes: {e}")


def write_weekly_highlights_to_notes(highlights_markdown):
    """Writes weekly highlights to Notes app in the week folder."""
    week_folder = ensure_notes_folders()
    if not week_folder:
        logging.error(
            "Week folder not found/created, cannot write weekly highlights to Notes."
        )
        return

    try:
        today = datetime.date.today()
        start_of_week = today - datetime.timedelta(days=today.weekday())
        end_of_week = start_of_week + datetime.timedelta(days=6)
        note_title = f"Weekly Highlights Week-{start_of_week.strftime('%Y-%m-%d')}_to_{end_of_week.strftime('%Y-%m-%d')}"
        new_note = week_folder.make(
            new=k.note,
            with_properties={k.name: note_title, k.body: highlights_markdown},
        )
        logging.info(
            f"Weekly highlights written to Notes: {note_title} in {week_folder.name.get()}"
        )
    except Exception as e:
        logging.error(f"Error writing weekly highlights to Notes: {e}")


def perform_daily_summary():
    today_log_filename = os.path.join(
        SCRIPT_CONFIG["AUDIO_LOG_DIR"],
        f"audio_log_{datetime.datetime.now().strftime('%Y-%m-%d')}.txt",
    )
    if not os.path.exists(today_log_filename):
        logging.info("No daily log file found for today. Skipping daily summary.")
        return

    try:
        with open(today_log_filename, "r") as log_file:
            daily_transcript = log_file.read()

        if not daily_transcript.strip():
            logging.info("Daily log file is empty. Skipping daily summary.")
            return

        ollama_client = OllamaLLM(model=SCRIPT_CONFIG["OLLAMA_MODEL"])

        prompt = f"""
        Summarize the following transcript from today's audio log, and extract:
        - Action points: List any actions that were mentioned or implied.
        - Decisions: List any decisions that were made.
        - Key ideas: List the most important ideas discussed.
        - To-dos: List any specific to-dos or tasks mentioned.

        Transcript:
        {daily_transcript}

        ---
        Summary and extractions:
        """
        response = ollama_client.invoke(prompt)
        summary_text = response

        notification_message = f"Daily Audio Log Summary:\n\n{summary_text}"
        send_notification(notification_message)
        logging.info("Daily summary performed and notification sent.")

        write_daily_summary_to_notes(summary_text)  # Write to Notes App

    except FileNotFoundError:
        logging.error(f"Daily log file not found: {today_log_filename}")
    except Exception as e:
        logging.error(f"Error during daily summarization process: {e}")


def perform_weekly_highlights():
    highlights_dir = SCRIPT_CONFIG["HIGHLIGHTS_OUTPUT_DIR"]
    audio_log_dir = SCRIPT_CONFIG["AUDIO_LOG_DIR"]
    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    end_of_week = start_of_week + datetime.timedelta(days=6)

    weekly_logs = []
    for i in range(7):
        date = start_of_week + datetime.timedelta(days=i)
        log_filename = os.path.join(
            audio_log_dir, f"audio_log_{date.strftime('%Y-%m-%d')}.txt"
        )
        if os.path.exists(log_filename):
            weekly_logs.append(log_filename)

    if not weekly_logs:
        logging.info("No weekly log files found. Skipping weekly highlights.")
        return

    weekly_transcript_content = ""
    for log_file in weekly_logs:
        try:
            with open(log_file, "r") as f:
                weekly_transcript_content += f.read() + "\n\n---\n\n"
        except Exception as e:
            logging.error(f"Error reading weekly log file {log_file}: {e}")
            continue

    if not weekly_transcript_content.strip():
        logging.info(
            "Weekly log content is empty. Skipping weekly highlights generation."
        )
        return

    ollama_client = OllamaLLM(model=SCRIPT_CONFIG["OLLAMA_MODEL"])
    prompt = f"""
        Create a highlights document in Markdown format from the following weekly audio transcript content.
        Focus on summarizing the week's key discussions, decisions, and important topics.
        Organize the highlights into clear sections and use Markdown formatting for readability (headings, bullet points, etc.).

        Weekly Transcript Content:
        {weekly_transcript_content}

        ---
        Weekly Highlights (Markdown):
        """
    try:
        response = ollama_client.invoke(prompt)
        highlights_markdown = response

        highlights_filename = os.path.join(
            highlights_dir,
            f"weekly_highlights_{start_of_week.strftime('%Y-%m-%d')}_to_{end_of_week.strftime('%Y-%m-%d')}.md",
        )
        with open(highlights_filename, "w") as md_file:
            md_file.write(highlights_markdown)

        logging.info(f"Weekly highlights document created: {highlights_filename}")
        send_notification(
            f"Weekly highlights document created: {highlights_filename}",
            title="Weekly Highlights Generated",
        )

        write_weekly_highlights_to_notes(
            highlights_markdown
        )  # Write to Notes App in Markdown

    except Exception as e:
        logging.error(f"Error during weekly highlights generation: {e}")


def send_notification(message, title=None):
    notification_title = title if title else SCRIPT_CONFIG["NOTIFICATION_TITLE"]
    try:
        notification.notify(
            title=notification_title,
            message=message,
            app_name=SCRIPT_CONFIG["NOTIFICATION_TITLE"],
            timeout=10,
            icon=SCRIPT_CONFIG["NOTIFICATION_ICON"]
            if os.path.exists(SCRIPT_CONFIG["NOTIFICATION_ICON"])
            else None,
        )
        logging.info("Notification sent.")
    except Exception as e:
        logging.error(f"Error sending notification: {e}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename="audio_logger.log",
    )
    logging.info("Script started.")

    ensure_directories()

    if SCRIPT_CONFIG["AUDIO_DEVICE_INDEX"] is None:
        get_audio_device_info()
        logging.warning(
            "AUDIO_DEVICE_INDEX is None, using default audio input device. Check device list and configure AUDIO_DEVICE_INDEX in SCRIPT_CONFIG if needed."
        )
    else:
        logging.info(f"Using audio device index: {SCRIPT_CONFIG['AUDIO_DEVICE_INDEX']}")

    # Determine device for Whisper model (MPS if available, else CPU)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    device = "cpu"  # delete line
    logging.info(f"Using device for Whisper model: {device}")
    print(f'device =  {device}')  # delete line
    try:
        whisper_model = whisper.load_model(
            SCRIPT_CONFIG["WHISPER_MODEL_NAME"], device=device
        )  # Load model with device specification
        logging.info(
            f"Whisper model '{SCRIPT_CONFIG['WHISPER_MODEL_NAME']}' loaded on {device}."
        )
        print('Whisper loaded')
    except Exception as e:
        print(f"Error loading Whisper model: {e}. Please ensure the model name is correct and you have internet access to download it initially, and that MPS is correctly configured if you intend to use it.")
        logging.error(
            f"Error loading Whisper model: {e}. Please ensure the model name is correct and you have internet access to download it initially, and that MPS is correctly configured if you intend to use it."
        )
        return

    schedule.every().day.at(SCRIPT_CONFIG["DAILY_SUMMARY_TIME"]).do(
        perform_daily_summary
    )
    schedule.every().sunday.at("08:00").do(perform_weekly_highlights)
    logging.info(f"Daily summary scheduled for {SCRIPT_CONFIG['DAILY_SUMMARY_TIME']}.")
    logging.info(
        f"Weekly highlights scheduled for every {SCRIPT_CONFIG['WEEKLY_HIGHLIGHTS_DAY']} at 8:00."
    )

    while True:
        logging.info("Starting audio recording block...")
        audio_data = record_audio(
            SCRIPT_CONFIG["BLOCK_DURATION_SECONDS"],
            SCRIPT_CONFIG["SAMPLE_RATE"],
            SCRIPT_CONFIG["RECORD_CHANNELS"],
            SCRIPT_CONFIG["AUDIO_DEVICE_INDEX"],
        )
        if audio_data is not None:
            transcript_text = transcribe_audio(audio_data, whisper_model)
            save_transcript_to_log(transcript_text)
        else:
            logging.warning("No audio recorded in this block.")

        schedule.run_pending()

        time.sleep(SCRIPT_CONFIG["TRANSCRIPTION_INTERVAL_SECONDS"])


if __name__ == "__main__":
    main()
