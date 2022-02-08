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

    def verse_count(self):
        return self.verse_end - self.verse + 1


verses = dict((Reference.parse(k), v) for k, v in yaml.load(
    open("verses.yaml"), Loader=yaml.SafeLoader).items())

verse_count = sum(r.verse_count() for r in verses)
print(f"Loaded {verse_count} verses")


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
    FIRST_LETTERS_EVERY_4 = "first-letters-4"
    FIRST_WORD = "first-word"
    BLIND = "blind"


text_prompt_levels = [
    ReviewPrompAspect.FULL_TEXT,
    ReviewPrompAspect.ENDING_UNDERSCORE,
    ReviewPrompAspect.FIRST_LETTERS,
    ReviewPrompAspect.FIRST_LETTERS_EVERY_4,
    ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_1,
    ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_2,
    ReviewPrompAspect.FIRST_WORD,
    ReviewPrompAspect.BLIND,
]

depricated_text_prompts = {
    ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_1,
    ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_2,
}


def step_down_difficulty(aspects):
    new_aspects = set()
    non_text_prompt_aspects = set()
    text_level_found = False
    for a in aspects:
        if a in text_prompt_levels:
            text_level_found = True
            index = text_prompt_levels.index(a)
            index -= 1
            if index < 0:
                index = 0
            # Assumes that the min is not depricated
            while text_prompt_levels[index] in depricated_text_prompts:
                index -= 1
            new_aspects.add(text_prompt_levels[index])
        else:
            non_text_prompt_aspects.add(a)
    if not text_level_found:
        new_aspects.add(text_prompt_levels[0])
    new_aspects.update(non_text_prompt_aspects)
    return new_aspects


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
            # Assumes that that the max is not depricated
            while text_prompt_levels[index] in depricated_text_prompts:
                index += 1
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
