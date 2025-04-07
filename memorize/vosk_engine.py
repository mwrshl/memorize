"""Vosk speech recognition engine for memorize."""

import sys
import json
import logging
import vosk


class VoskEngine:
    """Speech recognition using Vosk local model"""

    def __init__(self, samplerate):
        """Initialize Vosk with the given sample rate"""
        self.samplerate = samplerate

        # Initialize Vosk model
        try:
            self.model = vosk.Model("model")
            logging.info("Vosk model loaded successfully")
        except Exception as e:
            logging.error(f"Error loading Vosk model: {e}")
            raise RuntimeError(f"Failed to load Vosk model: {e}")

    def process_audio(self, audio_queue, test_finished):
        """
        Process audio data and transcribe speech with Vosk

        Args:
            audio_queue: Queue containing audio data from the microphone
            test_finished: Callback to determine when recording is complete

        Returns:
            The transcribed text
        """
        so_far = []

        sys.stdout.write("\n")
        sys.stdout.write("listening...\r")
        sys.stdout.flush()

        rec = vosk.KaldiRecognizer(self.model, self.samplerate)
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
