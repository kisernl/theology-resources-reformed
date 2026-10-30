#!/usr/bin/env python3
"""Project Gutenberg plain-text -> RAG markdown converter.

PG format: "*** START/END OF THE PROJECT GUTENBERG EBOOK ***" wrappers,
title pages + CONTENTS regions up front, wrapped paragraphs, footnotes
either inline ([Footnote: ...] / [Footnote N: ...]) or as trailing
"FOOTNOTES:" definition blocks keyed by [N] in-text refs.

Heading detection: LONE front-matter words -> ##; MARKER keyword lines
(CHAPTER/PART/BOOK/PSALM/SERMON/...) -> level per keyword; bare roman
numeral lines followed by a title block (Expositor's Bible style) -> ##;
standalone all-caps blocks -> OVERRIDES['caps_level'].

Front matter is preserved verbatim from the existing docs/<slug>.md —
only the `source:` line is rewritten to the PG ebook URL(s).

Usage:
    python3 tools/convert_gutenberg.py --report        # heading map only
    python3 tools/convert_gutenberg.py [SLUG ...]      # convert
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_DIR = REPO / 'sources'
DOC_DIR = REPO / 'docs'

from fetch_gutenberg import MAP as PG_MAP  # noqa: E402

START_RE = re.compile(r'^\s*\*\*\*\s*START OF (?:THE|THIS) PROJECT '
                      r'GUTENBERG EBOOK')
END_RE = re.compile(r'^\s*\*\*\*\s*END OF (?:THE|THIS) PROJECT '
                    r'GUTENBERG EBOOK')
TRANSCRIBER = re.compile(r'^\s*(?:\[?Transcriber\'?s?|Transcriber\'?s?'
                         r' Note)', re.I)
ILLUS = re.compile(r'^\s*\[Illustration[^\]]*\]\s*$')

LEVEL2_KW = {'PART', 'BOOK', 'TRACTATE', 'DIVISION', 'VOLUME', 'SECTION'}
LEVEL3_KW = {'CHAPTER', 'CHAP', 'LECTURE', 'SERMON', 'DISCOURSE',
             'QUESTION', 'LETTER', 'HOMILY', 'ORATION', 'DISSERTATION',
             'REPLY', 'PSALM', 'STUDY', 'VERSE', 'CANTICLE', 'EPISTLE',
             'CHAPTER'}
LEVEL4_KW = {'ARTICLE', 'POINT', 'OBJECTION'}
MARKERS = {**{k: 2 for k in LEVEL2_KW},
           **{k: 3 for k in LEVEL3_KW},
           **{k: 4 for k in LEVEL4_KW}}

LONE = {
    'PREFACE': 2, 'INTRODUCTION': 2, 'APPENDIX': 2, 'DEDICATION': 2,
    'CONCLUSION': 2, 'PROLOGUE': 2, 'EPILOGUE': 2, 'ADVERTISEMENT': 2,
    'POSTSCRIPT': 2, 'MEMOIR': 2, 'FOREWORD': 2, 'PREFATORY NOTE': 2,
    'PREFATORY REMARKS': 2, 'PREFACE TO THE READER': 2, 'TO THE READER': 2,
    'INTRODUCTORY NOTE': 2, 'INTRODUCTORY ESSAY': 2, 'BIBLIOGRAPHY': 2,
    "EDITOR'S PREFACE": 2, "EDITOR'S NOTE": 2, 'NOTE ON THE TEXT': 2,
    "TRANSLATOR'S PREFACE": 2, "TRANSLATOR'S NOTE": 2,
    "TRANSLATOR'S INTRODUCTION": 2, "PUBLISHER'S NOTE": 2,
    'GENERAL PREFACE': 2, 'GLOSSARY': 2, 'EXPLANATORY NOTES': 2,
    'NOTES': 2, 'EXCURSUS': 2, 'CHRONOLOGICAL TABLE': 2,
}
DROP_LONE = {'INDEX', 'CONTENTS', 'INDEX OF PROPER NAMES',
             'INDEX OF SCRIPTURE TEXTS', 'INDEX OF AUTHORS',
             'GENERAL INDEX', 'INDEX OF SUBJECTS', 'TABLE OF CONTENTS'}

CONTENTS_WORDS = {'CONTENTS', 'TABLE OF CONTENTS', 'CONTENTS.'}

TRAIL_HEAD = re.compile(
    r'^\s*(INDEX(\.|\s+[IVXLC]{1,4}\.?)?|TRANSCRIBER.?S?\s+NOTES?)', re.I)
FN_HEAD = re.compile(r'^\s*FOOTNOTES:?\s*$')
END_ANYWAY = re.compile(
    r'^\s*(THE END\.?\s*$|END OF THE PROJECT|START: FULL LICENSE'
    r'|End of the Project Gutenberg|End of Project Gutenberg)')

CAPS_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s.,;:'\"!?()&§\-–—/\[\]]*$")
NUM_RE = re.compile(r'^\s*([0-9IVXLC]{1,8})\.\s*$')
BARE_RE = re.compile(r'^\s*([IVXLC]{1,8})\s*$')
ROMAN_LINE_RE = re.compile(r'^\s*([IVXLC]{1,8})\.\s*(.*\S)?\s*$')
WIDE_NUM = re.compile(r'\s{2,}\d{1,4}\s*$')
NUMTITLE_RE = re.compile(r'^\s*(\d{1,3})\.\s+(\S.*)$')
MARKER_RE = re.compile(
    r'^\s*(CHAPTER|CHAP\.?|PART|BOOK|SECTION|SERMON|LECTURE|PSALM|ARTICLE'
    r'|QUESTION|LETTER|HOMILY|ORATION|DISSERTATION|REPLY|STUDY|VERSE'
    r'|CANTICLE|EPISTLE|TRACTATE|DIVISION|VOLUME|POINT|OBJECTION|APPENDIX)'
    r'\s+([0-9IVXLC]+(?:\s*[-–—]\s*[0-9IVXLC]+)?)\.?\s*(.*)$')

# per-file tweaks
# 'caps_level': level for standalone all-caps blocks (default None=off)
# 'roman_level': level for bare 'N.' marker lines (default None=off)
# 'numtitle_level': level for 'N. Title' lines (default None=off)
# 'head_res': [(regex, level)] evaluated on first line of a block
# 'lone': extra LONE words
# 'drop_res': [regex] blocks to drop entirely
# 'keep_transcriber': keep PG/transcriber forewords
OVERRIDES = {
    # Expositor's Bible vols: bare roman numeral -> ## "N — Title"
    **{s: {'roman_level': 2} for s in (
        'dods-expositor-s-bible-the-book-of-genesis',
        'dods-expositor-s-bible-the-gospel-of-st-john-volume-i',
        'dods-expositor-s-bible-the-gospel-of-st-john-volume-ii',
        'dods-expositor-s-bible-the-first-epistle-to-the-corinthians',
        'ball-expositor-s-bible-the-prophecies-of-jeremiah-volume-i',
        'bennett-expositor-s-bible-the-book-of-jeremiah-volume-ii',
        'gibson-expositor-s-bible-the-gospel-of-st-matthew',
        'maclaren-expositor-s-bible-colossians-and-philemon',
        'maclaren-expositor-s-bible-the-psalms-volume-i',
        'maclaren-expositor-s-bible-the-psalms-volume-ii',
        'maclaren-expositor-s-bible-the-psalms-volume-iii',
        'watson_ra-expositor-s-bible-judges-and-ruth',
        'watson_ra-expositor-s-bible-the-book-of-job',
        'watson_ra-expositor-s-bible-the-book-of-numbers',
        'harper-expositor-s-bible-the-book-of-deuteronomy',
        'farrar-expositor-s-bible-the-book-of-daniel',
        'farrar-expositor-s-bible-the-first-book-of-kings',
        'farrar-expositor-s-bible-the-second-book-of-kings',
        'chadwick-expositor-s-bible-the-book-of-exodus',
        'chadwick-expositor-s-bible-the-gospel-according-to-st-mark',
        'smith_ga-expositor-s-bible-the-book-of-isaiah-volume-i',
        'smith_ga-expositor-s-bible-the-book-of-isaiah-volume-ii',
        'smith_ga-expositor-s-bible-the-book-of-the-twelve-prophets-volume-i',
        'findlay-expositor-s-bible-the-epistle-to-the-ephesians',
        'findlay-expositor-s-bible-the-epistle-to-the-galatians',
        'stokes-expositor-s-bible-the-acts-of-the-apostles-volume-i',
        'stokes-expositor-s-bible-the-acts-of-the-apostles-volume-ii',
        'moule-expositor-s-bible-the-epistle-of-st-paul-to-the-romans',
        'burton-expositor-s-bible-the-gospel-according-to-st-luke',
        'denney-expositor-s-bible-the-epistles-to-the-thessalonians',
        'denney-expositor-s-bible-the-second-epistle-to-the-corinthians',
        'skinner-expositor-s-bible-the-book-of-ezekiel',
        'lumby-expositor-s-bible-the-epistles-of-st-peter',
        'horton-expositor-s-bible-the-book-of-proverbs',
        'rainy-expositor-s-bible-the-epistle-to-the-philippians',
        'kellogg-expositor-s-bible-the-book-of-leviticus',
        'cox-expositor-s-bible-the-book-of-ecclesiastes',
        'edwards_tc-expositor-s-bible-the-epistle-to-the-hebrews',
        'blaikie-expositor-s-bible-the-first-book-of-samuel',
        'blaikie-expositor-s-bible-the-book-of-joshua',
        'blaikie-expositor-s-bible-the-second-book-of-samuel',
        'adeney-expositor-s-bible-the-song-of-solomon-and-the-lamentations-of-jeremiah',
        'alexander-expositor-s-bible-the-epistles-of-st-john',
        'plummer-expositor-s-bible-the-general-epistles-of-st-james-and-st-jude',
        'plummer-expositor-s-bible-the-pastoral-epistles',
        'milligan-expositor-s-bible-the-book-of-revelation',
    )},
    # Maclaren Expositions: caps sermon titles -> ##
    **{s: {'caps_level': 2,
           'drop_before_contents': True,
           'drop_res': [
               r'^END OF VOL', r'^\s*EXPOSITIONS OF HOLY SCRIPTURE',
               r'^\s*ALEXANDER MACLAREN', r'^\s*CHAPS?\.',
               r'^\s*(GENESIS|EXODUS|LEVITICUS|NUMBERS|DEUTERONOMY|JOSHUA'
               r'|JUDGES|RUTH|SAMUEL|KINGS|CHRONICLES|EZRA|NEHEMIAH|ESTHER'
               r'|JOB|PROVERBS|ECCLESIASTES|PSALMS?|ISAIAH|JEREMIAH'
               r'|EZEKIEL|DANIEL|MATTHEW|MARK|LUKE|JOHN|THE ACTS|ACTS'
               r'|ROMANS|CORINTHIANS|ST\. JOHN|ST\. LUKE|ST\. MARK'
               r'|ST\. MATTHEW)\.?\s*$']}
       for s in (
        'maclaren-expositions-of-holy-scripture-deuteronomy-joshua-judges-ruth-and-first-book-of-samuel-second-samuel-first-kings-and-second-kings-chapters',
        'maclaren-expositions-of-holy-scripture-ezekiel-daniel-and-the-minor-prophets-and-matthew-chaps-i-to-viii',
        'maclaren-expositions-of-holy-scripture-genesis-exodus-leviticus-and-numbers',
        'maclaren-expositions-of-holy-scripture-isaiah-and-jeremiah',
        'maclaren-expositions-of-holy-scripture-luke',
        'maclaren-expositions-of-holy-scripture-mark',
        'maclaren-expositions-of-holy-scripture-psalms',
        'maclaren-expositions-of-holy-scripture-romans-and-corinthians',
        'maclaren-expositions-of-holy-scripture-st-john-ch-i-to-xiv',
        'maclaren-expositions-of-holy-scripture-st-john-chs-xv-to-xxi',
        'maclaren-expositions-of-holy-scripture-the-acts',
        'maclaren-expositions-of-the-holy-scriptures-second-kings-from-chap-viii-and-chronicles-ezra-and-nehemiah-esther-job-proverbs-and-ecclesiastes',
    )},
    'maclaren-expositions-of-the-holy-scriptures-second-kings-from-chap-viii-and-chronicles-ezra-and-nehemiah-esther-job-proverbs-and-ecclesiastes': {
        'caps_level': 2,
        'no_end_anyway': True,
        'drop_res': [
            r'^END OF VOL', r'^\s*EXPOSITIONS OF HOLY SCRIPTURE',
            r'^\s*ALEXANDER MACLAREN', r'^\s*CHAPS?\.',
            r'^\s*(GENESIS|EXODUS|LEVITICUS|NUMBERS|DEUTERONOMY|JOSHUA'
            r'|JUDGES|RUTH|SAMUEL|KINGS|CHRONICLES|EZRA|NEHEMIAH|ESTHER'
            r'|JOB|PROVERBS|ECCLESIASTES|PSALMS?|ISAIAH|JEREMIAH'
            r'|EZEKIEL|DANIEL|MATTHEW|MARK|LUKE|JOHN|THE ACTS|ACTS'
            r'|ROMANS|CORINTHIANS|ST\. JOHN|ST\. LUKE|ST\. MARK'
            r'|ST\. MATTHEW)\.?\s*$'],
    },
    'aquinas-summa-theologica': {
        'level_map': {'QUESTION': 4},
        'drop_before_contents': True,
        'body_anchor': r'^(FIRST|SECOND|THIRD) PART'
                       r'( OF THE SECOND PART)?\s*$',
        'drop_res': [r'^\s*\[".*"\]\s*$', r'^\s*_{3,}\s*$'],
        'head_res': [
            (r'^\s*(FIRST|SECOND|THIRD|SUPPLEMENT\w*)\s+PART\b', 2),
            (r'^\s*TREATISE\b', 3),
            (r'^\s*(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH'
             r'|NINTH|TENTH|ELEVENTH|TWELFTH)\s+ARTICLE', 5)],
    },
    'maclaren-expositor-s-bible-the-psalms-volume-i': {
        'roman_level': None,
        'head_res': [(r'^\s*PSALM\s+[IVXLC]+\.?\s*$', 2)],
    },
    'maclaren-expositor-s-bible-the-psalms-volume-ii': {
        'roman_level': None,
        'head_res': [(r'^\s*PSALM\s+[IVXLC]+\.?\s*$', 2)],
    },
    'maclaren-expositor-s-bible-the-psalms-volume-iii': {
        'roman_level': None,
        'head_res': [(r'^\s*PSALM\s+[IVXLC]+\.?\s*$', 2)],
    },
    'chesterton-heretics': {
        'numtitle_level': None,
        'head_res': [(r'^\s*[IVXLC]+\.\s+\S', 2)],
    },
    'taylor_jh-union-and-communion': {
        'head_res': [(r'^\s*SECTION\s+[IVXLC]+\.?\s*$', 2)],
    },
    'pascal-pensees': {
        'head_res': [(r'^\s*SECTION\s+[IVXLC]+\.?\s*$', 2),
                     (r'^\s*(NOTES|INDEX)\b', 2)],
    },
    'augustine-confessions': {
        'head_res': [(r'^\s*BOOK\s+[IVXLC]+\.?\s*$', 2)],
    },
    'boethius-theological-tractates': {
        'caps_level': 2,
        'roman_level': 3,
        'drop_before_contents': True,
        'end_marker': r'^\s*PHILOSOPHIAE CONSOLATIONIS',
        # Loeb interleaves each tractate's Latin text before its English
        # translation: drop Latin spans up to the English title block
        'drop_spans': [(
            r'^\s*(ANICII MANLII|ITEM EIVSDEM|QVOMODO S[VZ]BSTANTIAE'
            r'|DE FIDE CATHOLICA|DOMINO SANCTO|VTRVM PATER)',
            r'^\s*(THE TRINITY IS ONE|WHETHER FATHER|HOW SUBSTANCES'
            r'|ON THE CATHOLIC|A TREATISE AGAINST)')],
        'drop_res': [
            r'^\s*BOETHIUS\s*$', r'^\s*INCIPIT LIBER', r'^\s*EXPLICIT',
            r'^\s*V\.C\. ET INL', r'^\s*TO HIS ',
            r'^\s*A TREATISE BY', r'^\s*BY ANICIUS', r'^\s*MOST HONOURABLE',
            r'^\s*FROM THE SAME', r'^\s*[A-Z]\.([A-Z]\.)+\s*$',
            r'^\s*THE CONSOLATION OF PHILOSOPHY',
            r'^\s*THE THEOLOGICAL TRACTATES AND THE CONSOLATION'],
    },
    'burgon-causes-of-the-corruption-of-the-traditional-text-of-the-holy-gospels': {
        'body_anchor': r'^CHAPTER I\.?\s*$',
        'anchor_nth': 2,
        'head_res': [(r'^\s*CHAPTER\s+[IVXLC]+\.?\s*$', 2)],
    },
    'burgon-last-twelve-verses-of-the-gospel-according-to-s-mark-vindicated-against-recent-critical-objectors-and-established': {
        'drop_res': [r'^\s*The Codex Dedication'],
        'head_res': [(r'^\s*Chapter\s+[IVXLC]+\.', 3),
                     (r'^\s*APPENDIX \([A-H]\)\.?\s*$', 3)],
    },
    'daubney-three-additions-to-daniel-a-study': {
        'head_res': [(r'^\s*PART\s+[IVXLC]+\.?\s*$', 2)],
    },
    'luther-commentary-on-st-paul-s-epistle-to-the-galatians': {
        'head_res': [(r'^\s*CHAPTER\s+\d+\.?\s*$', 2),
                     (r'^\s*VERSE\s+\d+\.?\s*', 3)],
    },
    # analytical TOC without page numbers: end at first bare 'CHAPTER I'
    'bennett-expositor-s-bible-the-books-of-chronicles': {
        'loose_toc': True,
        'body_anchor': r'^Preface\.?$',
        'head_res': [(r'^\s*Chapter\s+[IVXLC]+\.', 3)],
    },
    'harnack-history-of-dogma-volume-i': {'caps_level': 3,
                                        'drop_before_contents': True,
                                        'loose_toc': True,
                                        'body_anchor': r'^CHAPTER I\.?\s*$'},
    'harnack-history-of-dogma-volume-ii': {'caps_level': 3,
                                         'drop_before_contents': True,
                                         'loose_toc': True,
                                         'body_anchor': r'^CHAPTER I\.?\s*$'},
}


def segments(lines):
    """Yield the inner line-ranges of each PG part."""
    cur = None
    for i, l in enumerate(lines):
        if START_RE.match(l):
            cur = i + 1
        elif END_RE.match(l) and cur is not None:
            yield lines[cur:i]
            cur = None
    if cur is not None:
        yield lines[cur:]


def blocks_of(lines):
    elems, cur = [], []
    for l in lines:
        if not l.strip():
            if cur:
                elems.append(cur)
                cur = []
        else:
            cur.append(l)
    if cur:
        elems.append(cur)
    return elems


def joined(lines):
    out = ''
    for l in lines:
        s = l.strip()
        if out and out.endswith('-') and not out.endswith(' -') \
                and out[-2:-1].isalpha():
            out = out[:-1] + s
        else:
            out = (out + ' ' + s).strip()
    return re.sub(r'\s+', ' ', out)


def is_caps(s):
    s = s.strip()
    return bool(s) and len(s) <= 110 and bool(re.search(r'[A-Z]', s)) \
        and s == s.upper()


def titlecase(s):
    """Title-case, preserving roman numerals, digits, and mixed case."""
    small = {'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in', 'nor',
             'of', 'on', 'or', 'the', 'to', 'up', 'with', 'from', 'into',
             'unto', 'upon'}
    out = []
    for i, w in enumerate(s.split()):
        core = w.strip('.,;:!?()')
        if re.fullmatch(r'[IVXLC]+', core) or re.search(r'\d', core) \
                or (w != w.upper() and w != w.lower()):
            out.append(w)
            continue
        lw = w.lower()
        out.append(lw if (i and lw in small) else lw[:1].upper() + lw[1:])
    return ' '.join(out)


REF_LINE = re.compile(
    r"^[A-Za-z.'&\- ]{2,}?\s+[ivxlcdm0-9][ivxlcdm0-9:.,–—\s\-]*\.?$")


def is_ref_line(s):
    """'GENESIS iii.' / 'Acts i. 1-14.' — book + chapter/verse ref."""
    s = s.strip().strip('_')
    return bool(REF_LINE.match(s)) and ' ' in s


def is_title_like(b):
    """Block usable as a heading title: caps/_caps_ short lines, not refs."""
    if sum(len(x.strip()) for x in b) > 110:
        return False
    for x in b:
        s = x.strip().strip('_').rstrip('.')
        if is_ref_line(s):
            return False
        if not (is_caps(s)
                or re.match(r"^[A-Z][a-zA-Z ,;'&\-?:]*$", s)):
            return False
    return True


def toc_entry(b):
    """All lines of the block look like table-of-contents entries."""
    for x in b:
        xs = x.strip()
        if len(xs) >= 80:
            return False
        if re.search(r'\d+\s*$', xs) or xs.endswith(')') \
                or MARKER_RE.match(xs) or NUM_RE.match(xs) \
                or re.search(r'\.{3,}', x) or is_caps(xs) \
                or re.match(r'^\d+\.\s+\S', xs) \
                or re.search(r'\([^)]*[ivx0-9][^)]*\)\s*$', xs) \
                or x != xs:
            continue
        return False
    return True


def parse_footnotes(blocks):
    """Return (defs, def_block_ids) — defs: n -> text."""
    defs = {}
    def_ids = set()
    in_fn = False
    for i, b in enumerate(blocks):
        first = b[0].strip()
        if re.match(r'^FOOTNOTES:?', first):
            in_fn = True
            def_ids.add(i)
            continue
        m = re.match(r'^\[(\d+)\]\s*(.*)$', joined(b))
        if m:
            def_ids.add(i)
            defs[int(m.group(1))] = m.group(2).strip()
            in_fn = True
            continue
        if in_fn:
            in_fn = False
    return defs, def_ids


def load_frontmatter(slug):
    doc = DOC_DIR / f'{slug}.md'
    if not doc.exists():
        return None, None
    text = doc.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    fm = m.group(1) if m else ''
    title = re.search(r'^title:\s*"(.*)"', fm, re.M)
    author = re.search(r'^author:\s*"(.*)"', fm, re.M)
    return fm, (title.group(1) if title else slug,
                author.group(1) if author else '')


def convert(slug, report_only=False):
    nos = PG_MAP[slug]
    ov = OVERRIDES.get(slug, {})
    src = SRC_DIR / f'{slug}.txt'
    lines = src.read_text(encoding='utf-8').split('\n')

    out_heads = []
    head_pos = []
    body_out = []
    toc_entries = []
    word_count = [0]

    lone = dict(LONE)
    for w in ov.get('lone', ()):
        lone[w] = 2
    drop_res = [re.compile(r) for r in ov.get('drop_res', ())]
    head_res = [(re.compile(r), lv) for r, lv in ov.get('head_res', ())]
    caps_level = ov.get('caps_level')
    roman_level = ov.get('roman_level')
    numtitle_level = ov.get('numtitle_level')

    index_words = {w for w in DROP_LONE if 'INDEX' in w}

    def emit_para(b, fn_defs):
        def fn_sub(mo):
            nn = int(mo.group(1))
            if nn in fn_defs:
                txt = fn_defs[nn].replace('[', '\\[').replace(']', '\\]')
                return ' [fn. %d: %s]' % (nn, txt)
            return mo.group(0)

        def fn_named(mo):
            txt = mo.group(2).replace('[', '\\[').replace(']', '\\]')
            return ' [fn. %s: %s]' % (mo.group(1) or '?', txt.strip())

        indents = sum(1 for x in b if x.startswith('   '))
        short = sum(1 for x in b if len(x.strip()) < 58)
        verse = len(b) >= 3 and indents >= len(b) * 0.7 \
            and short >= len(b) * 0.7
        if verse:
            for x in b:
                s = x.strip()
                word_count[0] += len(s.split())
                s = s.replace('[', '\\[').replace(']', '\\]')
                s = re.sub(r'\\\[Footnote(?:\s*(\d+))?:\s*(.*?)\\\]',
                           fn_named, s)
                s = re.sub(r'\\\[(\d+)\\\]', fn_sub, s)
                body_out.append(s + '  ')
            body_out.append('')
        else:
            para = joined(b)
            word_count[0] += len(para.split())
            if len(b) <= 2 and all(is_ref_line(x) for x in b):
                para = titlecase(para)
            para = para.replace('[', '\\[').replace(']', '\\]')
            para = re.sub(r'\\\[Footnote(?:\s*(\d+))?:\s*(.*?)\\\]',
                          fn_named, para)
            para = re.sub(r'\\\[(\d+)\\\]', fn_sub, para)
            para = re.sub(r'^([IVXLC]{1,6}|\d{1,3})\.(\s)',
                          r'**\1.**\2', para)
            body_out.append(para)
            body_out.append('')

    def emit_head(lv, txt):
        # consecutive duplicate (parallel-text editions repeat section
        # numerals) or a title-page repeat within ~120 words
        if out_heads and out_heads[-1] == (lv, txt):
            return
        for (plv, ptxt), pos in zip(out_heads[-6:], head_pos[-6:]):
            if (plv, ptxt) == (lv, txt) \
                    and word_count[0] - pos < 120:
                return
        out_heads.append((lv, txt))
        head_pos.append(word_count[0])
        body_out.append('#' * lv + ' ' + txt)
        body_out.append('')

    for seg in segments(lines):
        blocks = blocks_of(seg)
        fn_defs, fn_ids = parse_footnotes(blocks)

        # trailer = INDEX/END block or file-specific end marker, but only
        # once the contents region is past (TOC pages list INDEX entries)
        end_mark = re.compile(ov['end_marker']) if 'end_marker' in ov else None
        trailer = len(blocks)

        def is_trailer(b):
            t0 = b[0].strip()
            if b[0] != t0:
                return False  # indented lines are TOC entries
            return TRAIL_HEAD.match(t0) \
                or (not ov.get('no_end_anyway') and END_ANYWAY.match(t0)) \
                or t0.upper().rstrip('.:') in index_words \
                or (end_mark and end_mark.match(t0))

        def merge_titles(title, i):
            """Absorb following title-like blocks into the heading."""
            j = i + 1
            while j < trailer and is_title_like(blocks[j]) \
                    and not body_form(blocks[j]):
                extra = joined(blocks[j]).strip('_').rstrip('.')
                extra = extra.lstrip('-— ').strip()
                extra = re.sub(r'\[\d+\]', '', extra).strip()
                if extra and extra.lower() not in title.lower():
                    title += ' — ' + (titlecase(extra)
                                      if extra == extra.upper() else extra)
                j += 1
            return title, j - i

        def body_form(b):
            t0 = b[0].strip()
            if roman_level is not None and len(b) == 1 \
                    and (NUM_RE.fullmatch(t0) or BARE_RE.fullmatch(t0)):
                return True
            if b[0] != t0:  # indented lines are TOC entries, not headings
                return False
            if any(r.match(t0) for r, _ in head_res) \
                    and not re.search(r'\d+\s*$', t0):
                return True
            if numtitle_level is not None and NUMTITLE_RE.match(t0):
                return True
            if caps_level and all(is_caps(x.strip()) for x in b) \
                    and not joined(b).rstrip().endswith(')'):
                return True
            if caps_level and len(b) >= 2 and is_caps(b[0].strip()) \
                    and is_ref_line(b[1]):
                return True
            if ov.get('marker_body') and MARKER_RE.match(t0) \
                    and not re.search(r'\d+\s*$', t0):
                return True
            return False

        def head_like(b):
            """Block shaped like a body heading (may still be a TOC line)."""
            if body_form(b):
                return True
            t0 = b[0].strip()
            return (roman_level is not None or ov.get('marker_body')) \
                and MARKER_RE.match(t0) \
                and not re.search(r'\d+\s*$', joined(b))

        anchor = (re.compile(ov['body_anchor'])
                  if 'body_anchor' in ov else None)
        anchor_left = ov.get('anchor_nth', 1)

        # skip title pages/ads: advance to CONTENTS word or first heading
        i = 0
        in_contents = False
        while i < trailer:
            t0 = blocks[i][0].strip()
            u = t0.upper().rstrip('.:')
            if u in CONTENTS_WORDS:
                in_contents = True
                i += 1
                break
            if anchor and anchor.fullmatch(t0):
                break
            if not ov.get('drop_before_contents') \
                    and (body_form(blocks[i]) or u in lone
                         or MARKER_RE.match(t0)):
                break
            i += 1

        drop_spans = [(re.compile(a), re.compile(z))
                      for a, z in ov.get('drop_spans', ())]
        in_span = None

        while i < trailer:
            b = blocks[i]
            t0 = b[0].strip()
            jtxt = joined(b)

            if not in_contents and is_trailer(b):
                trailer = i
                break

            if in_span is not None:
                if in_span.match(t0):
                    in_span = None
                else:
                    i += 1
                    continue
            else:
                for a, z in drop_spans:
                    if a.match(t0):
                        in_span = z
                        break
                if in_span is not None:
                    i += 1
                    continue

            if i in fn_ids or TRANSCRIBER.match(t0) or ILLUS.match(t0) \
                    or FN_HEAD.match(t0) \
                    or any(r.match(t0) for r in drop_res):
                i += 1
                continue

            u = t0.upper().rstrip('.:')
            if u in CONTENTS_WORDS:
                in_contents = True
                i += 1
                continue
            if in_contents and anchor:
                if anchor.fullmatch(t0):
                    anchor_left -= 1
                    if not anchor_left:
                        in_contents = False
                        continue
                i += 1
                continue
            if in_contents:
                # A heading-shaped block is a TOC entry when a page-number
                # line ('TITLE          42') sits within the next 2 blocks;
                # otherwise it is the first real body heading.
                nxt_has_pagenum = any(
                    WIDE_NUM.search(x)
                    for nb in blocks[i + 1:i + 3] for x in nb)
                if head_like(b) and nxt_has_pagenum:
                    i += 1
                    continue
                if head_like(b):
                    in_contents = False
                elif MARKER_RE.match(t0) \
                        and re.search(r'\s+\d{1,4}\s*$', joined(b)):
                    i += 1
                    continue
                elif toc_entry(b) \
                        or (ov.get('loose_toc')
                            and all(len(x.strip()) < 80 for x in b)):
                    i += 1
                    continue
                else:
                    in_contents = False

            # heading rules -------------------------------------------------
            advance = 1
            emitted = False
            for r, lv in head_res:
                if r.match(t0):
                    txt = jtxt.rstrip('.')
                    txt = re.sub(r'\s*\[".*"\]\s*', ' ', txt)
                    txt = re.sub(r'\s*_{3,}\s*', ' ', txt)
                    txt = re.sub(r'\s+\d{1,4}$', '', txt).strip()
                    if txt == txt.upper():
                        txt = titlecase(txt)
                    else:
                        txt = ' '.join(
                            titlecase(w) if w == w.upper()
                            and re.search(r'[A-Z]', w) else w
                            for w in txt.split())
                    if re.fullmatch(r'[A-Za-z]+\s+[IVXLC0-9]+', txt) \
                            or txt.endswith(']'):
                        txt, advance = merge_titles(txt, i)
                    emit_head(lv, txt)
                    emitted = True
                    break
            if not emitted and u in lone:
                title = titlecase(t0).rstrip('.')
                title, advance = merge_titles(title, i)
                emit_head(lone[u], title)
                emitted = True
            if not emitted and roman_level is not None and len(b) == 1:
                mnum = NUM_RE.match(t0) or BARE_RE.match(t0)
                if mnum:
                    title, advance = merge_titles(mnum.group(1), i)
                    emit_head(roman_level, title)
                    emitted = True
            if not emitted:
                m = MARKER_RE.match(t0)
                if m:
                    kw = m.group(1).upper().rstrip('.')
                    lv = ov.get('level_map', {}).get(kw,
                                                     MARKERS.get(kw, 3))
                    rest = (m.group(3) or '').strip().rstrip('.')
                    rest = rest.lstrip('-— ').strip()
                    rest = re.sub(r'\s{2,}\d{1,4}\s*$', '', rest)
                    rest = re.sub(r'\[\d+\]', '', rest).strip()
                    num = m.group(2).strip()
                    title = f'{titlecase(kw)} {num}'
                    if rest and not re.fullmatch(r'[\d\s.,;:]*', rest):
                        title += ' — ' + (titlecase(rest)
                                          if rest == rest.upper() else rest)
                    if len(b) > 1 and is_caps(b[1].strip().strip('_')):
                        extra = joined(b[1:]).strip('_').rstrip('.')
                        cont = extra.startswith('--')
                        extra = extra.lstrip('-— ').strip()
                        extra = re.sub(r'\s{2,}\d{1,4}\s*$', '', extra)
                        if extra and extra.upper() != t0.upper():
                            title += (' ' if cont else ' — ') \
                                + titlecase(extra.lower())
                    else:
                        title, adv = merge_titles(title, i)
                        if adv > 1:
                            advance = adv
                    emit_head(lv, title)
                    emitted = True
            if not emitted and numtitle_level is not None \
                    and NUMTITLE_RE.match(t0):
                m = NUMTITLE_RE.match(t0)
                emit_head(numtitle_level,
                          f"{m.group(1)}. {m.group(2).rstrip('.')}")
                emitted = True
            if not emitted and caps_level:
                k = 0
                while k < len(b) and is_caps(b[k].strip().strip('_')):
                    k += 1
                if k and (k == len(b)
                          or all(is_ref_line(x) for x in b[k:])) \
                        and sum(len(x) for x in b[:k]) <= 200:
                    htxt = joined(b[:k])
                    htxt = re.sub(r'\[\d+\]', '', htxt)
                    htxt = titlecase(htxt.strip('_').rstrip('.')).strip()
                    emit_head(caps_level, htxt)
                    emitted = True
                    if k < len(b):
                        emit_para(b[k:], fn_defs)
            if emitted:
                i += advance
                continue

            emit_para(b, fn_defs)
            i += 1

    # ---- assemble ----
    fm, (title, author) = load_frontmatter(slug)
    nos_url = ' '.join(f'https://www.gutenberg.org/ebooks/{n}' for n in nos)
    if fm:
        if re.search(r'^source:.*$', fm, re.M):
            fm_new = re.sub(r'^source:.*$',
                            f'source: "{nos_url}"', fm, count=1, flags=re.M)
        else:
            fm_new = fm + f'\nsource: "{nos_url}"'
    else:
        fm_new = f'title: "{title}"\nauthor: "{author}"\nsource: "{nos_url}"'

    src_txt = (f'Project Gutenberg ebook {nos[0]}'
               if len(nos) == 1 else
               'Project Gutenberg ebooks ' +
               ', '.join(str(n) for n in nos))

    toc = ['- ' * 1 + ' ' * (lv - 2) * 2 + t if False else
           '  ' * (lv - 2) + '- ' + t for lv, t in out_heads]

    doc = ['---', fm_new, '---', '',
           f'# {title}', '',
           f'*{author}*', '',
           f'> Source: {src_txt}. Public domain.', '',
           '## Contents']
    doc += toc
    doc.append('')
    doc += body_out

    if report_only:
        return out_heads
    (DOC_DIR / f'{slug}.md').write_text('\n'.join(doc) + '\n',
                                        encoding='utf-8')
    return out_heads


def main():
    args = sys.argv[1:]
    report = '--report' in args
    args = [a for a in args if not a.startswith('--')]
    slugs = args or sorted(PG_MAP)
    for slug in slugs:
        if slug not in PG_MAP:
            print(f'{slug}: not in PG_MAP')
            continue
        heads = convert(slug, report_only=report)
        print(f'{slug}: {len(heads)} headings')
        if report:
            for lv, t in heads[:60]:
                print('   ' + '#' * lv + ' ' + t)
            if len(heads) > 60:
                print(f'   ... +{len(heads)-60} more')


if __name__ == '__main__':
    main()
