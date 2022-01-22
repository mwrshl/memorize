import vosk
import sounddevice as sd
import sys
import queue
import json
import logging

model = vosk.Model("model")

device_info = sd.query_devices(None, 'input')
# soundfile expects an int, sounddevice provides a float:
samplerate = int(device_info['default_samplerate'])


def get_audio(test_finished):
    q = queue.Queue()
    so_far = []

    def callback(indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(status, file=sys.stderr)
        q.put(bytes(indata))

    with sd.RawInputStream(samplerate=samplerate, blocksize=8000,
                           dtype='int16',
                           channels=1, callback=callback):
        sys.stdout.write("\n")
        sys.stdout.write("listening...\r")
        sys.stdout.flush()
        rec = vosk.KaldiRecognizer(model, samplerate)
        rec.SetMaxAlternatives(5)
        empty_partial_count = 0
        while True:
            data = q.get()
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
                if so_far and not partial:
                    empty_partial_count += 1
                    if empty_partial_count > 20:
                        break
                # if partial:
                # sys.stdout.write(f"{partial[-79:]}\r")
                # sys.stdout.flush()
        sys.stdout.write(" " * 79 + "\r")
        sys.stdout.flush()
        return " ".join(so_far)
