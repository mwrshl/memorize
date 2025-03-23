import vosk
import sounddevice as sd
import sys
import queue
import json
import logging
import os
from abc import ABC, abstractmethod

from memorize.deepgram_engine import DeepgramStreamEngine

# Default to Vosk
DEFAULT_ENGINE = "vosk"

# Vosk model initialization
model = vosk.Model("model")

device_info = sd.query_devices(None, "input")
# soundfile expects an int, sounddevice provides a float:
samplerate = int(device_info["default_samplerate"])


class SpeechRecognitionEngine(ABC):
    """Abstract base class for speech recognition engines"""

    @abstractmethod
    def process_audio(self, audio_data, test_finished):
        """Process audio data and return transcribed text"""
        pass


class VoskEngine(SpeechRecognitionEngine):
    """Speech recognition using Vosk"""

    def process_audio(self, audio_queue, test_finished):
        so_far = []

        sys.stdout.write("\n")
        sys.stdout.write("listening...\r")
        sys.stdout.flush()

        rec = vosk.KaldiRecognizer(model, samplerate)
        rec.SetMaxAlternatives(5)
        empty_partial_count = 0

        while True:
            data = audio_queue.get()
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                logging.info(f"alternatives: {res['alternatives']}")
                so_far.append(res["alternatives"][0]["text"])
                empty_partial_count = 0
                if test_finished(" ".join(so_far)):
                    break
                sys.stdout.write("listening for more...\r")
            else:
                partial = json.loads(rec.PartialResult())["partial"]
                if so_far and len(so_far) > 3 and not partial:
                    empty_partial_count += 1
                    if empty_partial_count > 40:
                        break
                # if partial:
                # sys.stdout.write(f"{partial[-79:]}\r")
                # sys.stdout.flush()

        sys.stdout.write(" " * 79 + "\r")
        sys.stdout.flush()
        return " ".join(so_far)


class DeepgramEngine(SpeechRecognitionEngine):
    """Speech recognition using Deepgram's real-time streaming API"""

    def __init__(self):
        """Initialize Deepgram stream engine"""
        self.engine = DeepgramStreamEngine()

    def process_audio(self, audio_queue, test_finished):
        """Stream audio data to Deepgram in real-time"""
        return self.engine.process_audio(audio_queue, test_finished)


def get_audio(test_finished, engine=None):
    """Record and transcribe speech using the specified engine.

    Args:
        test_finished: Callback that determines when recording is complete
        engine: Speech recognition engine to use ('vosk' or 'deepgram')
               If None, uses the DEFAULT_ENGINE

    Returns:
        Transcribed text
    """
    # Determine which engine to use
    if engine is None:
        engine = os.environ.get("MEMORIZE_SPEECH_ENGINE", DEFAULT_ENGINE)

    # Initialize the appropriate engine
    if engine == "deepgram":
        logging.info(f"Using Deepgram speech recognition engine")
        speech_engine = DeepgramEngine()
    else:  # Default to Vosk
        logging.info(f"Using Vosk speech recognition engine")
        speech_engine = VoskEngine()

    # Set up audio recording
    q = queue.Queue()
    
    # Use appropriate sample rate based on engine
    engine_samplerate = 16000 if engine == "deepgram" else samplerate
    logging.info(f"Using sample rate: {engine_samplerate} Hz")
    
    def callback(indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(status, file=sys.stderr)
        q.put(bytes(indata))

    # Record and process audio
    with sd.RawInputStream(
        samplerate=engine_samplerate,
        blocksize=8000,
        dtype="int16",
        channels=1,
        callback=callback,
    ):
        return speech_engine.process_audio(q, test_finished)
