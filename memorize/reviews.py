import re
import attr
import yaml
import enum
import pendulum
from typing import Set


@attr.frozen(order=True)
class Reference:
    book: str
    chapter: int
    verse: int
    verse_end: int

    @classmethod
    def parse(cls, s):
        m = re.match(r"(\d?\s?\w+)\s+(\d+):(\d+)-(\d+)", s)
        if m:
            book, chapter, verse, verse_end = m.groups()
            return Reference(book, int(chapter), int(verse), int(verse_end))
        else:
            m = re.match(r"(\d?\s?\w+)\s+(\d+):(\d+)", s)
            book, chapter, verse = m.groups()
            return Reference(book, int(chapter), int(verse), int(verse))

    def __str__(self):
        if self.verse != self.verse_end:
            return f"{self.book} {self.chapter}:{self.verse}-{self.verse_end}"
        else:
            return f"{self.book} {self.chapter}:{self.verse}"


verses = dict((Reference.parse(k), v) for k, v in yaml.load(
    open("verses.yaml"), Loader=yaml.SafeLoader).items())


@enum.unique
class ReviewPrompAspect(enum.Enum):
    REFERENCE = "reference"
    IMAGE = "image"
    FULL_TEXT = "full-text"
    MIDDLE_UNDERSCORE = "middle-underscore"
    ENDING_UNDERSCORE = "ending-underscore"
    FIRST_LETTERS = "first-letters"
    FIRST_LETTERS_EVERY_OTHER_1 = "first-letters-1"
    FIRST_LETTERS_EVERY_OTHER_2 = "first-letters-2"
    FIRST_WORD = "first-word"
    BLIND = "blind"


text_prompt_levels = [
    ReviewPrompAspect.FULL_TEXT,
    # ReviewPrompAspect.MIDDLE_UNDERSCORE,
    ReviewPrompAspect.ENDING_UNDERSCORE,
    ReviewPrompAspect.FIRST_LETTERS,
    ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_1,
    ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_2,
    ReviewPrompAspect.FIRST_WORD,
    ReviewPrompAspect.BLIND,
]


def step_up_difficulty(aspects):
    new_aspects = set()
    # First, find the text prompt
    text_level_maxed = False
    text_level_found = False
    non_text_prompt_aspects = set()
    for a in aspects:
        if a in text_prompt_levels:
            text_level_found = True
            index = text_prompt_levels.index(a)
            index += 1
            if index >= len(text_prompt_levels):
                index = len(text_prompt_levels) - 1
                text_level_maxed = True
            new_aspects.add(text_prompt_levels[index])
        else:
            non_text_prompt_aspects.add(a)
    if not text_level_found:
        new_aspects.add(text_prompt_levels[0])
    new_aspects.add(ReviewPrompAspect.REFERENCE)
    new_aspects.update(non_text_prompt_aspects)
    if text_level_maxed:
        new_aspects.discard(ReviewPrompAspect.IMAGE)
    return new_aspects


@enum.unique
class ReviewResponseAspect(enum.Enum):
    READ_ALOUD = "read-aloud"


@enum.unique
class ReviewResult(enum.Enum):
    FAIL = "fail"
    HARD = "hard"
    EASY = "easy"


@attr.define
class Review:
    reference: Reference
    date: pendulum.DateTime
    prompt: Set[ReviewPrompAspect]
    response: Set[ReviewResponseAspect]
    result: ReviewResult