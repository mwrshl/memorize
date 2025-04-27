
# Bible Verse Memorization Tool

A tool to help memorize Bible verses using spaced repetition and speech recognition.

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Download NLTK data:
```python
>>> import nltk
>>> nltk.download('punkt')
```

3. For Deepgram speech recognition (optional, but recommended):
   - Create an account at [Deepgram](https://deepgram.com/) to get an API key
   - Set your API key as an environment variable:
   ```
   export DEEPGRAM_API_KEY=your_api_key_here
   ```
   - Deepgram provides real-time streaming transcription with higher accuracy than the local Vosk model

## Usage

Run with default settings (Vosk speech recognition):
```
python -m memorize --count 20
```

Run with Deepgram speech recognition:
```
python -m memorize --count 20 --engine deepgram
```

Run with daily review limit:
```
python -m memorize --daily-limit 10
```

## Configuration

You can configure the application using a `config.yaml` file:

```yaml
reviews:
  daily_limit: 20  # Maximum reviews per day
  count: 20        # Default number of verses to review
speech:
  engine: vosk     # Default speech recognition engine (vosk or deepgram)
```

You can also specify a custom config file location:
```
python -m memorize --config /path/to/custom-config.yaml
```

## Options

- `--count`: Number of verses to review (default: 20)
- `--engine`: Speech recognition engine to use:
  - `vosk`: Uses local Vosk model (default)
  - `deepgram`: Uses Deepgram cloud API (requires API key)
- `--daily-limit`: Maximum number of reviews per day (default: 20)
- `--config`: Path to custom configuration file

## Environment Variables

- `MEMORIZE_SPEECH_ENGINE`: Set default speech engine (vosk or deepgram)
- `DEEPGRAM_API_KEY`: Required if using Deepgram engine
- `MEMORIZE_DAILY_LIMIT`: Set maximum number of reviews per day
