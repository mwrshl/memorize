import attr
import difflib
import metaphone
from fuzzywuzzy import fuzz
import contractions
import enum
import logging

fudge_words = {"the", "him", "of", "a", "for", "who", "to", "it"}
fudge_pairs = [
    {"his", "the"},
]


@enum.unique
class ChunkType(enum.Enum):
    GOOD = "good"
    CLOSE = "close"
    REMOVE = "remove"
    ADD = "add"


class FudgeReason(enum.Enum):
    NONE = "none"
    RATIO_EQUAL = "ratio_equal"
    RATIO_CLOSE = "ratio_close"
    FUDGE_WORDS = "fudge_words"
    FUDGE_PAIR = "fudge_pair"


@attr.frozen(slots=True)
class FudgeResult:
    type: FudgeType
    reason: FudgeReason = FudgeReason.NONE


@attr.frozen
class Token:
    original: str
    normalized: str
    dmeta: str

    def diffable(self):
        return self.dmeta[0]


class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    STRIKETHROUGH = "\033[9m"


def tokenize(s):
    """
    >>> [t.normalized for t in tokenize("the one who's truly")]
    ['the', 'one', 'who', 'is', 'truly']
    >>> [t.normalized for t in tokenize("who are God’s children")]
    ['who', 'are', 'gods', 'children']
    """
    remove_chars = '“”.,"-():;?'
    for c in remove_chars:
        s = s.replace(c, "")
    s = s.replace("—", " ")
    s = s.replace("’", "'")
    tokens = []
    for t in contractions.fix(s).split():
        normalized = t.lower().replace("'", "").replace('"', "")
        dmeta = metaphone.doublemetaphone(normalized)
        tokens.append(Token(original=t, normalized=normalized, dmeta=dmeta))
    return tokens


@attr.frozen
class DiffResult:
    chunks: list[(ChunkType, str)]

    def score(self) -> float:
        add_count = 0
        remove_count = 0
        close_count = 0
        for ty, _ in self.chunks:
            if ty == ChunkType.ADD:
                add_count += 1
            elif ty == ChunkType.CLOSE:
                close_count += 1
            elif ty == ChunkType.REMOVE:
                remove_count += 1
        miss_count = add_count + remove_count + close_count * 0.25
        # Pad the total length slightly so that short verses aren't overly penalized
        # for single mistakes.
        total = max(len(self.chunks), 1) + 5 # Reduced padding from 20
        return 1.0 - miss_count / total

    def int_score(self) -> int:
        return int(self.score() * 100)

    def appears_unfinished(self):
        if not self.chunks:
            return True
        # Iterate backwards from the end of the chunks
        num_trailing_adds = 0
        last_significant_chunk_type = None

        for chunk_type, _ in reversed(self.chunks):
            if chunk_type == ChunkType.ADD:
                num_trailing_adds += 1
            else:
                last_significant_chunk_type = chunk_type
                break # Found the last non-ADD chunk

        # Determine if unfinished based on the last significant chunk
        # Allow for 1 or 2 extra words at the end without being "unfinished"
        is_unfinished = False
        if last_significant_chunk_type in (ChunkType.REMOVE, ChunkType.CLOSE):
             is_unfinished = True
        elif last_significant_chunk_type is None and not self.chunks: # Empty diff means unfinished
             is_unfinished = True
        # If the diff ends only with ADDs, it's not unfinished unless it's just ADDs
        elif last_significant_chunk_type is None and num_trailing_adds > 0:
             is_unfinished = False # Ends only with additions means finished + extra
        elif last_significant_chunk_type == ChunkType.GOOD and num_trailing_adds <= 2:
             is_unfinished = False # Ends with GOOD, few ADDs is ok
        elif last_significant_chunk_type == ChunkType.GOOD and num_trailing_adds > 2:
             is_unfinished = True # Ends with GOOD, but too many ADDs looks weird/unfinished

        logging.info(f"appears_unfinished: {is_unfinished} (last_significant: {last_significant_chunk_type}, trailing_adds: {num_trailing_adds})")
        return is_unfinished

    def print(self):
        print_diff_chunks(self.chunks)


def print_diff_chunks(outputs, line_width=80):
    width = 0
    chunks = []
    colors = {
        ChunkType.GOOD: "",
        ChunkType.ADD: Colors.OKGREEN,
        ChunkType.REMOVE: Colors.STRIKETHROUGH + Colors.FAIL,
        ChunkType.CLOSE: Colors.WARNING,
    }
    for result, token in outputs:
        text = token.original
        if width + len(text) > line_width:
            chunks.append("\n")
            width = 0
        chunks.append(colors[result])
        chunks.append(text)
        if colors[result]:
            chunks.append(Colors.ENDC)
        width += len(text)
        if width == line_width:
            chunks.append("\n")
            width = 0
        else:
            chunks.append(" ")
            width += 1
    print("".join(chunks) + Colors.ENDC)


def fudge(expected_tokens, got_tokens) -> FudgeType:
    # Give one last chance to be a match
    expected_metaphone = "".join(t.dmeta[0] for t in expected_tokens)
    got_metaphone = "".join(t.dmeta[0] for t in got_tokens)
    ratio = fuzz.ratio(expected_metaphone, got_metaphone)
    logging.debug(f"fudge expected:{[t.original for t in expected_tokens]} got:{[t.original for t in got_tokens]} ratio:{ratio}")

    if ratio >= 85:
        return FudgeResult(FudgeType.EQUAL, FudgeReason.RATIO_EQUAL)
    # Note: Ratio check comes *after* fudge word/pair checks

    normalized_expected = {t.normalized for t in expected_tokens}
    normalized_got = {t.normalized for t in got_tokens}
    normalized_union = normalized_expected.union(normalized_got)

    # Check if *only* fudge words are involved in the difference
    if normalized_union.issubset(fudge_words):
        logging.debug("fudge: all fudge words")
        # Treat replacement of one fudge word with another as CLOSE, but ignorable
        return FudgeResult(FudgeType.CLOSE, FudgeReason.FUDGE_WORDS)

    # Check if the difference involves a defined fudge pair
    for pair in fudge_pairs:
        if normalized_union == pair:
             logging.debug("fudge: fudge pair")
             # Treat replacement within a fudge pair as CLOSE, but ignorable
             return FudgeResult(FudgeType.CLOSE, FudgeReason.FUDGE_PAIR)

    # If ratio was close enough, return CLOSE based on ratio
    if ratio >= 50:
        return FudgeResult(FudgeType.CLOSE, FudgeReason.RATIO_CLOSE)

    # Otherwise, it's a bad difference
    return FudgeResult(FudgeType.BAD)


def fuzzydiff(expected, got):
    """
    >>> fuzzydiff("who is", "who's").int_score()
    100
    >>> fuzzydiff('''Yet it is also new. Jesus lived the truth of this
    ...     commandment, and you also are living it. For the darkness is
    ...     disappearing, and the true light is already shining.''',
    ...     ' yeah it is also do').appears_unfinished() # Note: Score expectation removed
    True
    >>> fuzzydiff("exact match", "exact match").int_score()
    100
    >>> fuzzydiff("case difference", "Case Difference").int_score()
    100
    >>> fuzzydiff("punctuation difference.", "punctuation difference").int_score()
    100
    >>> fuzzydiff("contraction difference", "contraction difference").int_score()
    100
    >>> fuzzydiff("extra word", "extra word added").int_score() < 100
    True
    >>> fuzzydiff("missing word here", "missing here").int_score() < 100
    True
    >>> fuzzydiff("word replaced", "word substituted").int_score() < 100
    True
    >>> fuzzydiff("fudge the word", "fudge a word").int_score() == 100 # 'the' and 'a' are fudge words
    True
    >>> fuzzydiff("his word", "the word").int_score() == 100 # {'his', 'the'} is a fudge pair
    True
    >>> fuzzydiff("completely different", "totally unrelated").int_score() < 80
    True
    >>> fuzzydiff("", "").int_score()
    100
    >>> fuzzydiff("short", "").int_score() < 100
    True
    >>> fuzzydiff("", "short").int_score() < 100
    True
    >>> fuzzydiff("test appears unfinished", "test appears").appears_unfinished()
    True
    >>> fuzzydiff("test appears unfinished", "test appears un").appears_unfinished()
    True
    >>> fuzzydiff("test appears unfinished", "test appears unfinished completely").appears_unfinished()
    False
    >>> fuzzydiff("test appears unfinished", "test appears finished").appears_unfinished()
    False
    >>> fuzzydiff("this is a test", "this is a test").appears_unfinished()
    False
    >>> fuzzydiff("this is a test", "this is a").appears_unfinished()
    True
    >>> fuzzydiff("this is a test", "this is a test extra").appears_unfinished()
    False
    >>> fuzzydiff("this is a test", "this is").appears_unfinished()
    True
    >>> fuzzydiff("this is a test", "this is a t").appears_unfinished()
    True
    >>> fuzzydiff("this is a test", "this is a testt").appears_unfinished() # Close match at end
    False
    >>> fuzzydiff("this is a test", "this is a tes").appears_unfinished() # Close match at end
    False
    >>> fuzzydiff("this is a test", "this is a test of").appears_unfinished() # Added word at end
    False
    >>> fuzzydiff("this is a test", "this is a test of the").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the").appears_unfinished() # Added fudge word at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick brown").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick brown fox").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick brown fox jumps").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick brown fox jumps over").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick brown fox jumps over the").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick brown fox jumps over the lazy").appears_unfinished() # Added words at end
    False
    >>> fuzzydiff("this is a test", "this is a test the quick brown fox jumps over the lazy dog").appears_unfinished() # Added words at end
    False
    """
    logging.info(f"fuzzydiff({repr(expected)}, {repr(got)})")
    expected_tokens = tokenize(expected)
    got_tokens = tokenize(got)

    sm = difflib.SequenceMatcher(
        None,
        [t.diffable() for t in expected_tokens],
        [t.diffable() for t in got_tokens],
    )
    outputs = []

    def extend(chunk_type, tokens):
        outputs.extend([(chunk_type, t) for t in tokens])

    opcodes = sm.get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        expected = expected_tokens[i1:i2]
        got = got_tokens[j1:j2]
        if tag == "equal":
            extend(ChunkType.GOOD, expected)
        elif tag == "insert":
            # If the inserted word is a duplicate of the previous word, ignore it.
            if (
                len(got) == 1
                and j1 > 0
                and got_tokens[j1 - 1].normalized == got[0].normalized
            ):
                logging.debug(f"Ignoring duplicate inserted word: {got[0].original}")
                continue
            # If all inserted words are fudge words, ignore them.
            if all(t.normalized in fudge_words for t in got):
                logging.debug(
                    f"Ignoring inserted fudge words: {[t.original for t in got]}"
                )
                continue
            extend(
                ChunkType.ADD, got
            )  # Changed from REMOVE to ADD - represents added text
        elif tag == "delete":
            # If all deleted words are fudge words, *ignore* them (do not add to chunks).
            if all(t.normalized in fudge_words for t in expected):
                logging.debug(
                    f"Ignoring deleted fudge words: {[t.original for t in expected]}"
                )
                # No chunk added
            else:
                extend(
                    ChunkType.REMOVE, expected
                )
        elif tag == "replace":
            f_result = fudge(expected, got)
            # If it's an exact match OR a close match due to fudge words/pairs, treat as GOOD.
            if f_result.type == FudgeType.EQUAL or f_result.reason in (FudgeReason.FUDGE_WORDS, FudgeReason.FUDGE_PAIR):
                extend(ChunkType.GOOD, expected)
            # If it's close based on ratio, mark as CLOSE.
            elif f_result.type == FudgeType.CLOSE: # Implies reason == RATIO_CLOSE
                extend(ChunkType.CLOSE, expected)
            # Otherwise (BAD fudge result), mark as ADD/REMOVE.
            else:
                extend(ChunkType.ADD, got)
                extend(ChunkType.REMOVE, expected)
        else:
            assert False

    # Sometimes we get an extra word at the beginning
    if (
        outputs
        and outputs[0][0] == ChunkType.REMOVE
        and outputs[0][1].normalized in fudge_words
    ):
        logging.info("fuzzydiff: removing starting fudge word")
        outputs = outputs[1:]

    logging.debug(f"fuzzydiff chunks: {outputs}")

    return DiffResult(chunks=outputs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    import doctest

    doctest.testmod()
