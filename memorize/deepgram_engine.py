"""Deepgram speech recognition engine for memorize."""

import sys
import logging
import os
import queue
from threading import Event, Thread

# Import Deepgram
from deepgram import DeepgramClient, LiveTranscriptionEvents
from deepgram import LiveOptions

logger = logging.getLogger(__name__)
logger.setLevel("WARNING")


class DeepgramStreamEngine:
    """Speech recognition using Deepgram's real-time streaming API"""

    def __init__(self):
        """Initialize Deepgram client with API key"""
        api_key = os.environ.get("DEEPGRAM_API_KEY")
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable not set")
        self.deepgram = DeepgramClient(api_key)
        self.connection = None
        self.transcript = ""
        self.finished = False
        self.transcript_event = Event()
        self.exit_event = Event()

    def process_audio(self, audio_queue, test_finished):
        """
        Stream audio data to Deepgram in real-time

        Args:
            audio_queue: Queue containing audio data from the microphone
            test_finished: Callback to check if we have enough text to finish

        Returns:
            The transcribed text
        """
        # Setup UI
        sys.stdout.write("\n")
        sys.stdout.write("listening...\r")
        sys.stdout.flush()

        # Initialize transcript collection
        self.transcript = ""
        self.finished = False
        self.transcript_event.clear()
        self.exit_event.clear()

        # Setup the live transcription connection
        self.connection = self.deepgram.listen.websocket.v("1")

        # Define event handlers
        def on_open(connection_self, *args, **kwargs):
            logger.info("Connection to Deepgram opened")

        def on_message(connection_self, result, *args, **kwargs):
            logger.debug(f"Received Deepgram message, {result}")
            try:
                # Check if we have a transcript
                is_final = result.is_final
                if hasattr(result, "channel") and hasattr(
                    result.channel, "alternatives"
                ):
                    sentence = result.channel.alternatives[0].transcript
                    if sentence:
                        logger.info(
                            f"Deepgram transcript [{'final' if is_final else 'interim'}]: {sentence}"
                        )

                        # Only add final transcripts to our cumulative transcript to avoid duplicates
                        if is_final:
                            if self.transcript:
                                self.transcript += " " + sentence
                            else:
                                self.transcript = sentence

                            # Check if we've met the completion criteria
                            if test_finished(self.transcript):
                                self.finished = True
                                self.transcript_event.set()
                                # Don't call finish directly from this callback
                            else:
                                sys.stdout.write("listening for more...\r")
                                sys.stdout.flush()
                                self.transcript_event.set()
            except Exception as e:
                logger.exception(f"Error processing Deepgram message: {e}")

        def on_error(connection_self, error, *args, **kwargs):
            logger.error(f"Deepgram connection error: {error}")
            self.transcript_event.set()

        def on_close(connection_self, *args, **kwargs):
            logger.info("Deepgram connection closed")
            self.transcript_event.set()

        # Register event handlers
        self.connection.on(LiveTranscriptionEvents.Open, on_open)
        self.connection.on(LiveTranscriptionEvents.Transcript, on_message)
        self.connection.on(LiveTranscriptionEvents.Error, on_error)
        self.connection.on(LiveTranscriptionEvents.Close, on_close)

        # Configure live transcription options
        options = LiveOptions(
            model="nova-3",  # Using latest model for best accuracy
            language="en-US",
            smart_format=True,
            encoding="linear16",
            channels=1,
            sample_rate=16000,  # Deepgram requires 16kHz sample rate
            interim_results=True,
            endpointing=200,  # 200ms of silence to consider an utterance complete
        )

        # Start the connection
        connection_result = self.connection.start(options)
        if not connection_result:
            logger.error("Failed to start Deepgram connection")
            return ""

        # Audio sender thread function
        def send_audio():
            try:
                while not self.exit_event.is_set():
                    try:
                        # Get audio data from queue with timeout to check for exit periodically
                        data = audio_queue.get(timeout=0.1)
                        logger.debug(
                            f"Sending audio data to Deepgram: {len(data)} bytes"
                        )
                        if self.connection and not self.exit_event.is_set():
                            try:
                                self.connection.send(data)
                            except Exception as e:
                                logger.error(f"Error sending audio data: {e}")
                                break
                    except queue.Empty:
                        # No data available, continue
                        continue

                # Gracefully close the connection when done
                if self.connection:
                    try:
                        logger.info("Closing Deepgram connection from sender thread")
                        self.connection.finish()
                    except Exception as e:
                        logger.error(f"Error closing connection: {e}")

            except Exception as e:
                logger.error(f"Error in audio sender thread: {e}")
            finally:
                logger.info("Audio sender thread exiting")

        # Start audio sender thread
        sender_thread = Thread(target=send_audio)
        sender_thread.daemon = True
        sender_thread.start()

        try:
            # Wait for transcription to complete or timeout
            max_silence_count = 40
            silence_count = 0

            while not self.finished and silence_count < max_silence_count:
                # Wait for new transcript with timeout
                got_new_transcript = self.transcript_event.wait(timeout=0.5)
                self.transcript_event.clear()

                if not got_new_transcript:
                    # No new transcription received - increment silence counter
                    silence_count += 1
                    logger.debug(
                        f"No new transcript: silence count {silence_count}/{max_silence_count}"
                    )
                else:
                    # Reset silence counter when we get new transcription
                    silence_count = 0

            # If we've reached here, either we've finished or timed out
            self.exit_event.set()

            # Give the sender thread time to exit
            import time

            time.sleep(0.5)

            # Don't try to close the connection here - it can cause threading issues
            # The connection will be closed by normal websocket teardown

            # Clean up UI
            sys.stdout.write(" " * 79 + "\r")
            sys.stdout.flush()

            return self.transcript

        except Exception as e:
            logger.error(f"Error in Deepgram transcription: {e}")
            return self.transcript if self.transcript else ""
        finally:
            # Ensure resources are cleaned up
            self.exit_event.set()
            # Don't try to finish the connection here either
