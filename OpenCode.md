# OpenCode Guidelines for Bible Verse Memorization Tool

## Commands
- Run application: `python -m memorize --count 20`
- Run with Deepgram: `python -m memorize --count 20 --engine deepgram`
- Lint code: `./lint.sh` (runs ruff format and ruff check)
- Run tests: `python -m doctest memorize/diff.py`

## Code Style
- Use Python type hints with `attr.frozen` for immutable data classes
- Follow PEP 8 naming: snake_case for functions/variables, CamelCase for classes
- Imports: group standard library, then third-party, then local imports
- Error handling: use logging for errors, exceptions for unrecoverable issues
- Prefer immutable data structures (frozenset, attr.frozen)
- Use enums for fixed sets of values (ReviewResult, ChunkType)
- Document functions with docstrings that include doctests
- Use pendulum for date/time handling instead of datetime

## Project Structure
- Core functionality in memorize/ package
- Database: SQLite with peewee ORM
- Speech recognition: Vosk (local) or Deepgram (cloud API)
- Configuration in YAML files (verses.yaml, verses-meta.yaml)