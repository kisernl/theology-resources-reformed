#!/usr/bin/env python3
"""Download Project Gutenberg plain-text sources for corpus works that
exist on PG, replacing the CCEL-derived sources/*.txt files.

DOC -> [ebook numbers]. Multi-entry lists (e.g. Summa's four parts) are
concatenated into the single source file with a blank-line join.

Usage:
    python3 tools/fetch_gutenberg.py            # download all
    python3 tools/fetch_gutenberg.py SLUG ...   # specific sources
"""
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / 'sources'

MAP = {
    # ---- commentaries: Expositor's Bible & others ----
    'maclaren-expositor-s-bible-colossians-and-philemon': [37345],
    'maclaren-expositor-s-bible-the-psalms-volume-i': [42445],
    'maclaren-expositor-s-bible-the-psalms-volume-ii': [42488],
    'maclaren-expositor-s-bible-the-psalms-volume-iii': [44027],
    'plummer-expositor-s-bible-the-general-epistles-of-st-james-and-st-jude': [47337],
    'plummer-expositor-s-bible-the-pastoral-epistles': [39628],
    'harper-expositor-s-bible-the-book-of-deuteronomy': [49045],
    'ball-expositor-s-bible-the-prophecies-of-jeremiah-volume-i': [42601],
    'farrar-expositor-s-bible-the-book-of-daniel': [44103],
    'farrar-expositor-s-bible-the-first-book-of-kings': [42891],
    'farrar-expositor-s-bible-the-second-book-of-kings': [42027],
    'chadwick-expositor-s-bible-the-book-of-exodus': [33420],
    'chadwick-expositor-s-bible-the-gospel-according-to-st-mark': [37120],
    'smith_ga-expositor-s-bible-the-book-of-isaiah-volume-i': [39767],
    'smith_ga-expositor-s-bible-the-book-of-isaiah-volume-ii': [43672],
    'smith_ga-expositor-s-bible-the-book-of-the-twelve-prophets-volume-i': [43847],
    'findlay-expositor-s-bible-the-epistle-to-the-ephesians': [39196],
    'findlay-expositor-s-bible-the-epistle-to-the-galatians': [42645],
    'stokes-expositor-s-bible-the-acts-of-the-apostles-volume-i': [42258],
    'stokes-expositor-s-bible-the-acts-of-the-apostles-volume-ii': [42303],
    'moule-expositor-s-bible-the-epistle-of-st-paul-to-the-romans': [48858],
    'burton-expositor-s-bible-the-gospel-according-to-st-luke': [39856],
    'denney-expositor-s-bible-the-epistles-to-the-thessalonians': [42753],
    'denney-expositor-s-bible-the-second-epistle-to-the-corinthians': [41850],
    'skinner-expositor-s-bible-the-book-of-ezekiel': [46975],
    'gibson-expositor-s-bible-the-gospel-of-st-matthew': [40811],
    'lumby-expositor-s-bible-the-epistles-of-st-peter': [42273],
    'dods-expositor-s-bible-the-book-of-genesis': [39395],
    'dods-expositor-s-bible-the-first-epistle-to-the-corinthians': [42354],
    'dods-expositor-s-bible-the-gospel-of-st-john-volume-i': [33151],
    'dods-expositor-s-bible-the-gospel-of-st-john-volume-ii': [33288],
    'luther-commentary-on-st-paul-s-epistle-to-the-galatians': [1549],
    'watson_ra-expositor-s-bible-judges-and-ruth': [39727],
    'watson_ra-expositor-s-bible-the-book-of-job': [40470],
    'watson_ra-expositor-s-bible-the-book-of-numbers': [42639],
    'horton-expositor-s-bible-the-book-of-proverbs': [42189],
    'rainy-expositor-s-bible-the-epistle-to-the-philippians': [39788],
    'kellogg-expositor-s-bible-the-book-of-leviticus': [42334],
    'cox-expositor-s-bible-the-book-of-ecclesiastes': [39913],
    'edwards_tc-expositor-s-bible-the-epistle-to-the-hebrews': [32968],
    'blaikie-expositor-s-bible-the-first-book-of-samuel': [39394],
    'blaikie-expositor-s-bible-the-book-of-joshua': [42319],
    'blaikie-expositor-s-bible-the-second-book-of-samuel': [44619],
    'adeney-expositor-s-bible-the-song-of-solomon-and-the-lamentations-of-jeremiah': [39941],
    'alexander-expositor-s-bible-the-epistles-of-st-john': [40775],
    'bennett-expositor-s-bible-the-book-of-jeremiah-volume-ii': [41893],
    'bennett-expositor-s-bible-the-books-of-chronicles': [40235],
    'milligan-expositor-s-bible-the-book-of-revelation': [42251],
    # ---- Maclaren Expositions (sermons) ----
    'maclaren-expositions-of-holy-scripture-deuteronomy-joshua-judges-ruth-and-first-book-of-samuel-second-samuel-first-kings-and-second-kings-chapters': [8068],
    'maclaren-expositions-of-holy-scripture-ezekiel-daniel-and-the-minor-prophets-and-matthew-chaps-i-to-viii': [15836],
    'maclaren-expositions-of-holy-scripture-genesis-exodus-leviticus-and-numbers': [7069],
    'maclaren-expositions-of-holy-scripture-isaiah-and-jeremiah': [8069],
    'maclaren-expositions-of-holy-scripture-luke': [8200],
    'maclaren-expositions-of-holy-scripture-mark': [8071],
    'maclaren-expositions-of-holy-scripture-psalms': [7925],
    'maclaren-expositions-of-holy-scripture-romans-and-corinthians': [13601],
    'maclaren-expositions-of-holy-scripture-st-john-ch-i-to-xiv': [8070],
    'maclaren-expositions-of-holy-scripture-st-john-chs-xv-to-xxi': [8381],
    'maclaren-expositions-of-holy-scripture-the-acts': [8397],
    'maclaren-expositions-of-the-holy-scriptures-second-kings-from-chap-viii-and-chronicles-ezra-and-nehemiah-esther-job-proverbs-and-ecclesiastes': [7883],
    # ---- systematic ----
    'aquinas-summa-theologica': [17611, 17897, 18755, 19950],
    # 'calvin-institutes': already a Gutenberg source (45001 + 64392)
    # ---- treatises ----
    'boethius-theological-tractates': [13316],
    'burgon-causes-of-the-corruption-of-the-traditional-text-of-the-holy-gospels': [21112],
    'burgon-last-twelve-verses-of-the-gospel-according-to-s-mark-vindicated-against-recent-critical-objectors-and-established': [26134],
    'daubney-three-additions-to-daniel-a-study': [12420],
    # ---- apologetics ----
    'pascal-pensees': [18269],
    'chesterton-heretics': [470],
    # ---- devotional ----
    'taylor_jh-union-and-communion': [26172],
    # ---- biography ----
    'augustine-confessions': [3296],
    # ---- histories ----
    'harnack-history-of-dogma-volume-i': [19612],
    'harnack-history-of-dogma-volume-ii': [19613],
}


def fetch(no):
    """Return decoded text for ebook N, trying the usual URL patterns."""
    urls = [
        f'https://www.gutenberg.org/cache/epub/{no}/pg{no}.txt',
        f'https://www.gutenberg.org/files/{no}/{no}-0.txt',
        f'https://www.gutenberg.org/files/{no}/{no}.txt',
        f'https://www.gutenberg.org/ebooks/{no}.txt.utf-8',
    ]
    for u in urls:
        r = subprocess.run(['curl', '-sL', '--fail', '-o', '-', u],
                           capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 10000 \
                and b'Project Gutenberg' in r.stdout[:5000]:
            for enc in ('utf-8', 'latin-1'):
                try:
                    return r.stdout.decode(enc)
                except UnicodeDecodeError:
                    continue
            return r.stdout.decode('utf-8', errors='replace')
        time.sleep(0.3)
    return None


def main():
    only = set(sys.argv[1:])
    ok, fail = [], []
    for slug, nos in MAP.items():
        if only and slug not in only:
            continue
        parts = []
        for no in nos:
            t = fetch(no)
            if t is None:
                fail.append(f'{slug}: ebook {no} download failed')
                break
            parts.append(t)
            time.sleep(0.3)
        else:
            out = '\n\n'.join(parts)
            (SRC / f'{slug}.txt').write_text(out, encoding='utf-8')
            ok.append(slug)
            print(f'{slug}: {len(out):,} chars <- {nos}')
    print(f'\n{len(ok)} downloaded, {len(fail)} failed')
    for f in fail:
        print('FAIL:', f)


if __name__ == '__main__':
    main()
