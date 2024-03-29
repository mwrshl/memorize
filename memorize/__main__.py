import pendulum
import click
import collections
import time
from pendulum import Duration, DateTime
import logging
import readchar

from . diff import fuzzydiff
from . audio import get_audio


from . reviews import (verses, ReviewPrompAspect,
                       Review, Reference, ReviewResponseAspect, ReviewResult,
                       step_up_difficulty, step_down_difficulty,
                       deprecated_text_prompts,
                       all_reviews, save_review)

from . prompt import show_prompt, image_exists


class ReviewScore:
    def __init__(self, reference, reviews):
        self.reference = reference
        self.score = 1
        self.review_bucket = 0
        self.due = pendulum.now() - Duration(seconds=1)
        self.frequency = Duration(hours=0)
        self.last_easy = None
        self.last_hard_or_failed = None
        self.fails_in_a_row = 0
        self.previous_easy = None
        self.purgatory_countdown = 0
        self.prompt = None
        reviews.sort(key=lambda r: r.date)
        prev = None
        for r in reviews:
            self.feed(r, prev)
            prev = r
            if reference == Reference("Rom", 8, 13, 13):
                print(r.result, self.frequency, self.prompt)
        self.finalize(reviews)

    def feed(self, review, previous_review):
        if review.result == ReviewResult.FAIL:
            self.fails_in_a_row += 1
            if self.purgatory_countdown:
                self.purgatory_countdown = 5
            elif self.fails_in_a_row == 2:
                self.purgatory_countdown = 5
        else:
            self.fails_in_a_row = 0
        if review.result == ReviewResult.EASY:
            if self.purgatory_countdown:
                self.purgatory_countdown -= 1
        if self.purgatory_countdown:
            self.prompt = {ReviewPrompAspect.REFERENCE,
                           ReviewPrompAspect.FIRST_LETTERS}
            self.frequency = Duration(hours=6)
        else:
            self.prompt = review.prompt

        if self.frequency < Duration(hours=6):
            self.frequency = Duration(hours=6)
        if review.result == ReviewResult.FAIL:
            self.last_hard_or_failed = review
            self.frequency -= Duration(hours=6)
            if self.frequency > Duration(days=1):
                self.frequency *= .3
        elif review.result == ReviewResult.HARD:
            self.last_hard_or_failed = review
            self.frequency -= Duration(hours=4)
            if self.frequency > Duration(days=1):
                self.frequency *= .7
        elif review.result == ReviewResult.EASY:
            self.last_easy = review
            if self.previous_easy and (review.date - self.previous_easy.date) < Duration(hours=4):
                self.previous_easy = review
                return
            self.previous_easy = review
            if ReviewPrompAspect.BLIND in review.prompt:
                self.frequency += Duration(hours=24)
                if previous_review and previous_review.result == ReviewResult.EASY:
                    a = pendulum.instance(previous_review.date)
                    b = pendulum.instance(review.date)
                    d = b.diff(a) * 1.32
                    if d > self.frequency:
                        self.frequency = d
            elif ReviewPrompAspect.FIRST_WORD in review.prompt:
                self.frequency += Duration(hours=12)
            elif ReviewPrompAspect.FIRST_LETTERS in review.prompt:
                self.frequency = Duration(hours=6)
            elif ReviewPrompAspect.ENDING_UNDERSCORE in review.prompt:
                self.frequency = Duration(hours=6)

    def finalize(self, reviews):
        self.review_bucket = 5
        if self.frequency < Duration(days=3):
            self.review_bucket = 2
        elif self.frequency < Duration(weeks=1):
            self.review_bucket = 3
        elif self.frequency < Duration(weeks=3):
            self.review_bucket = 4
        if self.last_easy:
            self.due_date = self.last_easy.date + self.frequency
        else:
            self.score = 1
            self.review_bucket = 1
            self.due_date = pendulum.now() - Duration(seconds=1)
            return
        if self.last_hard_or_failed:
            min_due_date = self.last_hard_or_failed.date + Duration(hours=2)
            if min_due_date > self.due_date:
                self.due_date = min_due_date
            if self.last_easy and self.last_easy.date < self.last_hard_or_failed.date:
                self.review_bucket = 1
        now = pendulum.now()
        if self.last_easy:
            self.ratio = (now - self.last_easy.date) / \
                (self.due_date - self.last_easy.date)
        else:
            self.review_bucket = 0
            self.ratio = 0
        if now > self.due_date:
            self.score = 10 + (now - self.due_date).days
        else:
            self.score = 0


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


def print_review_buckets(scores: list[ReviewScore]):
    by_bucket = collections.defaultdict(list)
    for s in scores:
        by_bucket[s.review_bucket].append(s)
    for (b, scores) in sorted(by_bucket.items()):
        print(f"{b}:")
        for s in scores:
            print(f"   {s.reference}")


def review_candidates():
    reviews_by_reference = {}
    for reference in verses:
        reviews_by_reference[reference] = []

    for review in all_reviews:
        try:
            reviews_by_reference[review.reference].append(review)
        except KeyError:
            pass

    scores_by_reference = {}
    results = []
    due_dates = []
    frequencies = {}
    for reference, reviews in reviews_by_reference.items():
        reviews.sort(key=lambda r: r.date)
        score = ReviewScore(reference, reviews)
        frequencies[reference] = score.frequency
        due_dates.append(score.due_date)
        scores_by_reference[reference] = score
        if score.score:
            results.append(score)
    print_frequencies(frequencies)
    print_date_histogram(due_dates)
    # results.sort(key=lambda s: (-s.score, s.reference))
    results.sort(key=lambda s: (s.review_bucket, s.reference))
    print_review_buckets(results)
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


def do_review(ref, prompt, save=True):
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
    if save:
        save_review(r)

    original_res = res

    while res != ReviewResult.EASY:
        time.sleep(2)
        res = get_audio_with_result(ref)

    return original_res


def do_increasing_difficulty_review(score: ReviewScore):
    if score.prompt:
        prompt = set(score.prompt)
        # Always show the reference for the moment
        prompt.add(ReviewPrompAspect.REFERENCE)
    else:
        prompt = {ReviewPrompAspect.REFERENCE,
                  ReviewPrompAspect.FULL_TEXT,
                  ReviewPrompAspect.IMAGE, }
    if prompt.intersection(deprecated_text_prompts):
        prompt = step_down_difficulty(prompt)

    ref = score.reference

    if not image_exists(ref):
        prompt.discard(ReviewPrompAspect.IMAGE)

    for i in range(2):
        res = do_review(ref, prompt, save=i <= 1)
        if res != ReviewResult.EASY:
            break
        if score.purgatory_countdown != 0:
            break
        new_prompt = step_up_difficulty(prompt)
        if new_prompt == prompt:
            break
        prompt = new_prompt


@ click.command()
@ click.option("--count", default=20)
def review(count: int):
    candidates = review_candidates()
    num_due = 0
    num_new = 0
    for score in candidates:
        if score.score > 1:
            num_due += 1
        elif score.score == 1:
            num_new += 1
    print(
        f"Reviewing {min(count, num_due)} of {num_due} due and {num_new} new")
    candidates = candidates[:count]
    for i, score in enumerate(candidates):
        print("#"*i + "-"*(len(candidates)-i))
        do_increasing_difficulty_review(score)


if __name__ == "__main__":
    logging.basicConfig(filename="mem.log",
                        encoding="utf-8", level=logging.INFO)
    review()
