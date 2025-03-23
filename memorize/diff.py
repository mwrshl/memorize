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


@enum.unique
class FudgeType(enum.Enum):
    EQUAL = "equal"
    CLOSE = "close"
    BAD = "bad"


@attr.frozen
class Token:
    original: str
    normalized: str
    dmeta: str

    def diffable(self):
        return self.dmeta[0]


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    STRIKETHROUGH = '\033[9m'


def tokenize(s):
    """
    >>> [t.normalized for t in tokenize("the one who's truly")]
    ['the', 'one', 'who', 'is', 'truly']
    >>> [t.normalized for t in tokenize("who are God’s children")]
    ['who', 'are', 'gods', 'children']
    """
    remove_chars = "“”.,\"-():;?"
    for c in remove_chars:
        s = s.replace(c, "")
    s = s.replace("—", " ")
    s = s.replace("’", "'")
    tokens = []
    for t in contractions.fix(s).split():
        normalized = t.lower().replace("'", '').replace('\"', '')
        dmeta = metaphone.doublemetaphone(normalized)
        tokens.append(Token(original=t,
                            normalized=normalized,
                            dmeta=dmeta))
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
        miss_count = add_count + remove_count + close_count * .25
        # Pad the total length so that short verses aren't scored too low when
        # they have a single mistake.
        total = len(self.chunks) + 20
        return 1. - miss_count / total

    def int_score(self) -> int:
        return int(self.score() * 100)

    def appears_unfinished(self):
        if not self.chunks:
            return True
        add_count = 0
        remove_count = 0
        itr = reversed(self.chunks)
        for ty, _ in itr:
            if ty == ChunkType.ADD:
                add_count += 1
            elif ty == ChunkType.REMOVE:
                remove_count += 1
                break
            else:
                break
        for ty, _ in itr:
            if ty == ChunkType.REMOVE:
                remove_count += 1
            else:
                break

        res = False
        if remove_count > 1:
            res = False
        elif remove_count == 1 and add_count > 2:
            res = True
        elif add_count > 1:
            res = True
        logging.info(f"appears_unfinished: {res} {remove_count} {add_count}")
        return res

    def print(self):
        print_diff_chunks(self.chunks)


def print_diff_chunks(outputs, line_width=80):
    width = 0
    chunks = []
    colors = {
        ChunkType.GOOD: '',
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
    logging.info(
        f"fudge expected:{expected_tokens} got:{got_tokens} ratio:{ratio}")

    if ratio >= 85:
        return FudgeType.EQUAL
    if ratio >= 50:
        return FudgeType.CLOSE

    normalized = {t.normalized for t in expected_tokens + got_tokens}

    if normalized.issubset(fudge_words):
        logging.info("all fudge words")
        return FudgeType.CLOSE

    if normalized in fudge_pairs:
        logging.info("fudge pair")
        return FudgeType.CLOSE

    return FudgeType.BAD


def fuzzydiff(expected, got):
    """
    >>> fuzzydiff("who is", "who's").int_score()
    100
    >>> fuzzydiff('''Yet it is also new. Jesus lived the truth of this
    ...     commandment, and you also are living it. For the darkness is
    ...     disappearing, and the true light is already shining.''',
    ...     ' yeah it is also do').appears_unfinished()
    True
    >>> fuzzydiff("i want all of you to share",
    ...     "i want all of you you too  share").int_score()
    100
    """
    logging.info(f"fuzzydiff({repr(expected)}, {repr(got)})")
    expected_tokens = tokenize(expected)
    got_tokens = tokenize(got)

    sm = difflib.SequenceMatcher(None,
                                 [t.diffable() for t in expected_tokens],
                                 [t.diffable() for t in got_tokens])
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
            if len(got) == 1 and j1 > 0 and got_tokens[j1-1] == got[0]:
                # ignore duplicate word
                continue
            if all(t.normalized in fudge_words for t in got):
                continue
            extend(ChunkType.REMOVE, got)
        elif tag == "delete":
            if all(t.normalized in fudge_words for t in expected):
                extend(ChunkType.CLOSE, expected)
            else:
                extend(ChunkType.ADD, expected)
        elif tag == "replace":
            f = fudge(expected, got)
            if f == FudgeType.EQUAL:
                extend(ChunkType.GOOD, expected)
            elif f == FudgeType.CLOSE:
                extend(ChunkType.CLOSE, expected)
            else:
                extend(ChunkType.REMOVE, got)
                extend(ChunkType.ADD, expected)
        else:
            assert(False)

    # Sometimes we get an extra word at the beginning
    if (outputs
            and outputs[0][0] == ChunkType.REMOVE
            and outputs[0][1].normalized in fudge_words):
        logging.info("fuzzydiff: removing starting fudge word")
        outputs = outputs[1:]

    logging.debug(f"fuzzydiff chunks: {outputs}")

    return DiffResult(chunks=outputs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    import doctest
    doctest.testmod()
