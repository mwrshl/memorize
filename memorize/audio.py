import sounddevice as sd
import sys
import queue
import json
import logging
import os
from abc import ABC, abstractmethod

# Default to Vosk if available, fallback to Deepgram if not
DEFAULT_ENGINE = "vosk"

# Get audio device info
device_info = sd.query_devices(None, "input")
# soundfile expects an int, sounddevice provides a float:
samplerate = int(device_info["default_samplerate"])


class SpeechRecognitionEngine(ABC):
    """Abstract base class for speech recognition engines"""

    @abstractmethod
    def process_audio(self, audio_data, test_finished):
        """Process audio data and return transcribed text"""
        pass


class SpeechEngineFactory:
    """Factory for creating speech recognition engines"""
    
    @staticmethod
    def create_engine(engine_name):
        """
        Create and return a speech recognition engine instance
        
        Args:
            engine_name: Name of the engine to create ('vosk' or 'deepgram')
            
        Returns:
            A speech recognition engine instance
        
        Raises:
            ImportError: If the requested engine can't be imported
        """
        if engine_name == "vosk":
            # Import Vosk engine only when needed
            try:
                from memorize.vosk_engine import VoskEngine
                logging.info("Using Vosk speech recognition engine")
                return VoskEngine(samplerate)
            except ImportError:
                logging.error("Vosk module not found. Is it installed?")
                raise ImportError("Vosk not installed. Install with 'pip install vosk'")
        
        elif engine_name == "deepgram":
            # Import Deepgram engine only when needed
            try:
                from memorize.deepgram_engine import DeepgramStreamEngine
                logging.info("Using Deepgram speech recognition engine")
                return DeepgramStreamEngine()
            except ImportError:
                logging.error("Deepgram module not found. Is it installed?")
                raise ImportError("Deepgram SDK not installed. Install with 'pip install deepgram-sdk'")
        
        else:
            logging.error(f"Unknown speech engine: {engine_name}")
            raise ValueError(f"Unknown speech engine: {engine_name}")


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
        
    # Set sample rate based on engine
    engine_samplerate = 16000 if engine == "deepgram" else samplerate
    logging.info(f"Using sample rate: {engine_samplerate} Hz")
    
    # Create the appropriate engine using our factory
    try:
        speech_engine = SpeechEngineFactory.create_engine(engine)
    except ImportError as e:
        logging.error(f"Failed to initialize speech engine: {e}")
        # Fallback to another engine if available
        if engine == "vosk":
            logging.info("Falling back to Deepgram engine")
            try:
                speech_engine = SpeechEngineFactory.create_engine("deepgram")
                engine = "deepgram"
                engine_samplerate = 16000
            except ImportError:
                raise RuntimeError("No speech recognition engines available. Please install either vosk or deepgram-sdk.")
        else:
            logging.info("Falling back to Vosk engine")
            try:
                speech_engine = SpeechEngineFactory.create_engine("vosk")
                engine = "vosk"
                engine_samplerate = samplerate
            except ImportError:
                raise RuntimeError("No speech recognition engines available. Please install either vosk or deepgram-sdk.")

    # Set up audio recording
    q = queue.Queue()
    
    # The sample rate has already been set above
    
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
