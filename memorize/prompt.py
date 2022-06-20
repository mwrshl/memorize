import time
import textwrap
import subprocess
from nltk.tokenize import word_tokenize
from nltk.tokenize.treebank import TreebankWordDetokenizer
import os.path

from . reviews import ReviewPrompAspect, verses


def _ending_underscore(text):
    """
    >>> _ending_underscore("And God said that it was good.")
    And God s___ t___ it was g___.
    >>> _ending_underscore('now we call him, "Abba, Father"')
    now we c___ him, "A___, F_____"
    >>> _ending_underscore(
    ... 'in the earth below—indeed, nothing in all creation')
    in the e____ b____ — i_____, n______ in all c_______
    >>> _ending_underscore('were saved. (If we')
    w___ s____ . (If we
    """
    for c in "“”":
        text = text.replace(c, '"')
    text = text.replace("—", " — ")

    def underscore_ending(word):
        if len(word) > 3:
            return word[0] + "_" * (len(word)-1)
        else:
            return word
    tokens = word_tokenize(text)
    tokens = [underscore_ending(word) for word in tokens]
    text = TreebankWordDetokenizer().detokenize(tokens)
    print('\n'.join(textwrap.wrap(text)))


def _first_letters(text, should_show=lambda idx: True):
    """
    >>> _first_letters("And God said that it was good.")
    A G s t i w g
    >>> _first_letters('now we call him, "Abba, Father"')
    n w c h A F
    >>> _first_letters("Every Other Word", lambda i: i%2)
    _ O _
    >>> _first_letters("And God said that it was good.",
    ...                lambda i: not (i//4)%2)
    A G s t _ _ _
    """
    for c in "\"“”.,?!—":
        text = text.replace(c, " ")
    tokens = text.split()
    tokens = [(word[0] if should_show(i) else '_')
              for (i, word) in enumerate(tokens)]
    text = " ".join(tokens)
    print('\n'.join(textwrap.wrap(text)))


def image_file(ref):
    return f"images/{ref}.jpg"


def image_exists(ref):
    return os.path.exists(image_file(ref))


def show_prompt(ref, prompt):
    print("-"*80)
    if ReviewPrompAspect.REFERENCE in prompt:
        print(f"{ref}")
        time.sleep(2)
    if ReviewPrompAspect.IMAGE in prompt:
        subprocess.run(["eog", image_file(ref)])

    text = verses[ref]

    if ReviewPrompAspect.FULL_TEXT in prompt:
        print('\n'.join(textwrap.wrap(text)))

    if ReviewPrompAspect.ENDING_UNDERSCORE in prompt:
        _ending_underscore(text)

    if ReviewPrompAspect.FIRST_LETTERS in prompt:
        _first_letters(text, lambda idx: True)

    if ReviewPrompAspect.FIRST_LETTERS_1 in prompt:
        _first_letters(text, lambda idx: (idx % 5) < 4)

    if ReviewPrompAspect.FIRST_LETTERS_2 in prompt:
        _first_letters(text, lambda idx: (idx % 5) < 3)

    if ReviewPrompAspect.FIRST_LETTERS_3 in prompt:
        _first_letters(text, lambda idx: (idx % 5) < 2)

    if ReviewPrompAspect.FIRST_LETTERS_4 in prompt:
        _first_letters(text, lambda idx: (idx % 5) < 1)

    if ReviewPrompAspect.FIRST_LETTERS_5 in prompt:
        _first_letters(text, lambda idx: ((idx//5) % 2) == 0)

    if ReviewPrompAspect.FIRST_WORD in prompt:
        tokens = word_tokenize(text)
        print(tokens[0], "...")

    if ReviewPrompAspect.BLIND in prompt:
        print("...")


if __name__ == "__main__":
    import doctest
    doctest.testmod()
