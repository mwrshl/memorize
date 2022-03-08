import attr
import cattr
import cattr.preconf.json
import re
import os.path
import yaml
import enum
import pendulum
from typing import FrozenSet
import peewee


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

deprecated_text_prompts = {
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
            # Assumes that the min is not deprecated
            while text_prompt_levels[index] in deprecated_text_prompts:
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
            while text_prompt_levels[index] in deprecated_text_prompts:
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


@attr.frozen(order=True)
class Review:
    reference: Reference
    date: pendulum.DateTime
    prompt: FrozenSet[ReviewPrompAspect]
    response: FrozenSet[ReviewResponseAspect]
    result: ReviewResult


converter = cattr.preconf.json.make_converter()
converter.register_structure_hook(
    Reference, lambda s, _: Reference.parse(s))
converter.register_unstructure_hook(Reference, lambda r: str(r))


def load_yaml():
    if not os.path.exists("reviews.yaml"):
        return []
    reviews_yaml = yaml.load(open("reviews.yaml"), Loader=yaml.SafeLoader)
    if reviews_yaml:
        reviews = converter.structure(reviews_yaml, list[Review])
        reviews.sort(key=lambda r: r.date)
    else:
        reviews = []
    return reviews


yaml_reviews = load_yaml()


db = peewee.SqliteDatabase("reviews.db")


class ReferenceModel(peewee.Model):
    book = peewee.CharField()
    chapter = peewee.IntegerField()
    verse = peewee.IntegerField()
    verse_end = peewee.IntegerField()

    class Meta:
        database = db

    def to_reference(self):
        return Reference(self.book, self.chapter, self.verse, self.verse_end)


class ReviewModel(peewee.Model):
    reference = peewee.ForeignKeyField(ReferenceModel, backref="reviews")
    date = peewee.DateTimeField()
    prompt = peewee.CharField()
    response = peewee.CharField()
    result = peewee.CharField()

    class Meta:
        database = db

    def to_review(self):
        return Review(self.reference.to_reference(),
                      pendulum.parse(self.date),
                      frozenset(ReviewPrompAspect(s)
                                for s in self.prompt.split(",")),
                      frozenset(ReviewResponseAspect(s)
                                for s in self.response.split(",")),
                      ReviewResult(self.result))


db.connect()
db.create_tables([ReferenceModel, ReviewModel])


def load_sqlite():
    for m in ReviewModel.select():
        yield m.to_review()


def save_review_sqlite(r):
    reference, created = ReferenceModel.get_or_create(
        book=r.reference.book,
        chapter=r.reference.chapter,
        verse=r.reference.verse,
        verse_end=r.reference.verse_end)
    m = ReviewModel.create(
        reference=reference,
        date=str(r.date),
        prompt=",".join(e.value for e in r.prompt),
        response=",".join(e.value for e in r.response),
        result=r.result.value)
    m.save()


sqlite_reviews = set(load_sqlite())

for r in yaml_reviews:
    if r not in sqlite_reviews:
        print("saving to sqlite")
        save_review_sqlite(r)
        sqlite_reviews.add(r)

all_reviews = list(sqlite_reviews)
all_reviews.sort(key=lambda r: r.date)


def save():
    with open("reviews.yaml", "wt") as f:
        yaml.dump(converter.unstructure(all_reviews), f)


def save_review(r):
    save_review_sqlite(r)
    all_reviews.append(r)
    # save()
