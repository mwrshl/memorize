import yaml
import pendulum
import cattr
import cattr.preconf.json
import click
import time
from pendulum import Duration, DateTime
import logging
import readchar

from . diff import fuzzydiff
from . audio import get_audio


from . reviews import (Reference, verses, ReviewPrompAspect,
                       Review, ReviewResponseAspect, ReviewResult,
                       step_up_difficulty)

from . prompt import show_prompt, image_exists

converter = cattr.preconf.json.make_converter()
converter.register_structure_hook(Reference, lambda s, _: Reference.parse(s))
converter.register_unstructure_hook(Reference, lambda r: str(r))

reviews_yaml = yaml.load(open("reviews.yaml"), Loader=yaml.SafeLoader)
if reviews_yaml:
    all_reviews = converter.structure(reviews_yaml, list[Review])
else:
    all_reviews = []


def save():
    with open("reviews.yaml", "wt") as f:
        yaml.dump(converter.unstructure(all_reviews), f)


def score_review_priority(reviews) -> int:
    if not reviews:
        return (1, (pendulum.now() - Duration(seconds=1)), Duration(hours=0))
    reviews.sort(key=lambda r: r.date)
    frequency = Duration(hours=6)
    last_easy = None
    last_hard_or_failed = None
    previous_easy = None
    for r in reviews:
        if frequency < Duration(hours=6):
            frequency = Duration(hours=6)
        if r.result == ReviewResult.FAIL:
            last_hard_or_failed = r
            frequency -= Duration(hours=6)
        elif r.result == ReviewResult.HARD:
            last_hard_or_failed = r
            frequency -= Duration(hours=4)
        elif r.result == ReviewResult.EASY:
            last_easy = r
            if previous_easy and (r.date - previous_easy.date) < Duration(hours=4):
                previous_easy = r
                continue
            previous_easy = r
            if ReviewPrompAspect.BLIND in r.prompt:
                frequency += Duration(hours=24)
            elif ReviewPrompAspect.FIRST_WORD in r.prompt:
                frequency += Duration(hours=12)
            elif ReviewPrompAspect.FIRST_LETTERS in r.prompt:
                frequency += Duration(hours=6)
            elif ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_1 in r.prompt:
                frequency += Duration(hours=6)
            elif ReviewPrompAspect.FIRST_LETTERS_EVERY_OTHER_2 in r.prompt:
                frequency += Duration(hours=6)
            elif ReviewPrompAspect.ENDING_UNDERSCORE in r.prompt:
                frequency += Duration(hours=6)
    if (len(reviews) > 2
            and reviews[-1].result == ReviewResult.EASY
            and reviews[-2].result == ReviewResult.EASY):
        a = pendulum.instance(reviews[-2].date)
        b = pendulum.instance(reviews[-1].date)
        d = b.diff(a) * 1.5
        if d > frequency:
            frequency = d
    if last_easy:
        due_date = last_easy.date + frequency
    else:
        due_date = pendulum.now() - Duration(seconds=1)
    if last_hard_or_failed:
        min_due_date = last_hard_or_failed.date + Duration(hours=2)
        if min_due_date > due_date:
            due_date = min_due_date
    now = pendulum.now()
    if now > due_date:
        return (10 + (now - due_date).days, due_date, frequency)
    else:
        return (0, due_date, frequency)


def print_frequencies(frequencies):
    for reference, frequency in sorted(frequencies.items()):
        print(reference, frequency.days, "days,", frequency.hours, "hours")


def print_date_histogram(dates: list[DateTime]):
    import collections
    by_date = collections.defaultdict(lambda: 0)
    for d in dates:
        by_date[d.date()] += 1
    for date, count in sorted(by_date.items()):
        print(date, count)


def review_candidates():
    reviews_by_reference = {}
    for reference in verses:
        reviews_by_reference[reference] = []

    for review in all_reviews:
        reviews_by_reference[review.reference].append(review)

    results = []
    due_dates = []
    frequencies = {}
    for reference, reviews in reviews_by_reference.items():
        reviews.sort(key=lambda r: r.date)
        if reviews:
            last_review = reviews[-1]
        else:
            last_review = None
        score, due_date, frequency = score_review_priority(reviews)
        frequencies[reference] = frequency
        due_dates.append(due_date)
        if score:
            results.append((score, reference, last_review))
    print_frequencies(frequencies)
    print_date_histogram(due_dates)
    results.sort(key=lambda prio_ref: (-prio_ref[0], prio_ref[1]))
    return results


def do_override_prompt(result):
    print("Override? (1:EASY, 2:HARD, 3:FAIL, Any other key: no change)")
    keys = {
        '1': ReviewResult.EASY,
        '2': ReviewResult.HARD,
        '3': ReviewResult.FAIL,
    }
    c = readchar.readchar()
    if c in keys:
        res = keys[c]
        print(f"changing to {res}")
        logging.info(
            f"do_override_prompt Overriding result from {result} to {res}")
        return res
    else:
        logging.info(f"do_override_prompt Keeping result {result}")
        return result


def get_audio_with_result(ref):
    def test(text):
        diffres = fuzzydiff(verses[ref], text)
        return not diffres.appears_unfinished()

    audio_res = get_audio(test)

    diffres = fuzzydiff(verses[ref], audio_res)

    diffres.print()

    score = diffres.score()
    if score > 0.96:
        res = ReviewResult.EASY
    elif score > 0.92:
        res = ReviewResult.HARD
    else:
        res = ReviewResult.FAIL

    logging.info(f"score: {score} result: {res}")
    print(res)

    if res != ReviewResult.EASY:
        res = do_override_prompt(res)

    return res


def do_review(ref, prompt):
    print("")

    show_prompt(ref, prompt)

    res = get_audio_with_result(ref)

    r = Review(
        reference=ref,
        date=pendulum.now(),
        prompt=prompt,
        response={ReviewResponseAspect.READ_ALOUD},
        result=res
    )
    all_reviews.append(r)
    save()

    original_res = res

    while res != ReviewResult.EASY:
        time.sleep(2)
        res = get_audio_with_result(ref)

    return original_res


def do_increasing_difficulty_review(ref, last_review):
    if last_review:
        prompt = last_review.prompt.copy()
        # Always show the reference for the moment
        prompt.add(ReviewPrompAspect.REFERENCE)
    else:
        prompt = {ReviewPrompAspect.REFERENCE,
                  ReviewPrompAspect.FULL_TEXT,
                  ReviewPrompAspect.IMAGE, }
    if not image_exists(ref):
        prompt.discard(ReviewPrompAspect.IMAGE)
    res = do_review(ref, prompt)
    if res == ReviewResult.EASY:
        new_prompt = step_up_difficulty(prompt)
        if new_prompt != prompt:
            do_review(ref, new_prompt)


@ click.command()
@ click.option("--count", default=20)
def review(count: int):
    candidates = review_candidates()
    num_due = 0
    num_new = 0
    for prio, ref, last_review in candidates:
        if prio > 1:
            num_due += 1
        elif prio == 1:
            num_new += 1
    print(
        f"Reviewing {min(count, num_due)} of {num_due} due and {num_new} new")
    for prio, ref, last_review in candidates[:count]:
        do_increasing_difficulty_review(ref, last_review)


if __name__ == "__main__":
    logging.basicConfig(filename="mem.log",
                        encoding="utf-8", level=logging.INFO)
    review()
