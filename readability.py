"""A Python port of arc90's Readability.js

http://lab.arc90.com/experiments/readability/

This is hacky, minimally tested, and not yet optimized for speed.  But it gets
the job done.  Much of it is a line-by-line translation of arc90's js code to
python.  Caveat Utor.


example call:
import readability
text = readability.get_text(html)
title = readability.get_title(html)

Related:
  * Nirmal Patel's readability python port: http://nirmalpatel.com/fcgi/hn.py
    (less powerful but works decently)
  * Bonus approach:  http://stackoverflow.com/questions/2921237/is-there-anything-for-python-that-is-like-readability-js/2934186#2934186

TODO:
  * clean up title processing
  * get some external reviewers/cleanup
  * look at readability site for more improvements
  * get rid of unused stuff
  * profile for speed
  * more formally test on an assembled corpus.
"""

import re
import sys

from BeautifulSoup import BeautifulSoup, Comment

DEBUG = False

def dbg(text):
  """Poor-man's logging."""
  if DEBUG:
    sys.stderr.write('%s\n', text)


UNLIKELY_CANDIDATES_RE = re.compile(
    'combx|comment|disqus|foot|header|menu|rss|shoutbox|sidebar|sponsor|ad-break')
OK_MAYBE_ITS_A_CANDIDATE_RE = re.compile('and|article|body|column|main')

POSITIVE_RE = re.compile(
    'article|body|content|entry|hentry|page|pagination|post|text|blog')
NEGATIVE_RE = re.compile(    'combx|comment|contact|foot|footer|footnote|link|masthead|media|meta|promo|related|scroll|shoutbox|sponsor|tags|widget')
DIV_TO_P_ELEMENTS_RE = re.compile(
    '<(a|blockquote|dl|div|img|ol|p|pre|table|ul)')
REPLACE_BRS_RE_2 = re.compile('<br */? *>[ \r\n]*<br */? *>')
# REPLACE_BRS_RE = re.compile('(<br[^>]*>[ \n\r\t]*){2,}')
# REPLACE_FONTS_RE = re.compile('<(\/?)font[^>]*>')
# TRIM_RE = re.compile('^\s+|\s+$')
# NORMALIZE_RE = re.compile('\s{2,}')
# KILL_BREAKS_RE = re.compile('(<br\s*\/?>(\s|&nbsp;?)*){1,}')
# VIDEO_RE = re.compile('http:\/\/(www\.)?(youtube|vimeo)\.com')
# SKIP_FOOTNOTE_LINK_RE = re.compile(
#     '^\s*(\[?[a-z0-9]{1,2}\]?|^|edit|citation needed)\s*$')

GOOD_NAMES = re.compile('div')
OK_NAMES = re.compile('pre|td|blockquote')
BAD_NAMES = re.compile('address|ol|ul|dl|dd|dt|li|form')
HORRIBLE_NAMES = re.compile('h1|h2|h3|h4|h5|h6|th')


def _textify(soup, html=False):
  """Grab the plaintext from a node."""
  if not html:
    retval = [t.strip(' ') for t in soup.findAll(text=True) if t.strip()]
    retval = ''.join(retval)
    retval = re.sub('[ \t]+', ' ', retval)
    retval = re.sub('[\n\f\v]+', '\n', retval)
    return retval.strip()
  return soup.prettify()


def get_title(soup):
  """Get the title from a soup-parsed web page."""
  try:
    orig_title = soup.findAll('title')[0]
  except:
    orig_title = ''
  title = orig_title
  # TODO: take care of titles like foo-bar, foo|bar, and foo: bar
  """
  if ' | ' in orig_title or ' - ' in orig_title:
    title = re.sub('(.*)- .*', '\1', orig_title)
    if title.count(' ') < 3:
      title = re.sub('[^\|\-]*[\|\-](.*)', '\1', orig_title)
  """

  if len(title) > 150 or len(title) < 15:
    h1s = list(soup.findAll('h1'))
    if len(h1s) == 1:
      title = h1s[0]
  return _textify(title)


def get_text(html):
  """Get the contentful text from a soup-parsed web page.

  This is the meat of the script."""
  html = re.sub(REPLACE_BRS_RE_2, "</p><p>", html)
  try:
    soup = BeautifulSoup(html)
  except HTMLParser.HTMLParseError:
    return ''

  for node in get_bad_nodes(soup):
    node.extract()
  
  candidates = get_candidates(soup)
  if not candidates:
    return ''

  best = None
  for candidate in get_candidates(soup):
    score = rank(candidate)
    if not best or best.score < score:
      best = candidate

  candidates = sorted([[c.score, c] for c in candidates])
  best = candidates[0][1]
  # TODO: later, only do this if it doesn't hurt length too much.
  strip_junk_tags(best)  
  return _textify(best)


def get_bad_nodes(soup):
  """Return the nodes that are bad.  All script nodes, also cruddy ones."""
  for node in soup.findAll('script'):
    yield node
  for node in soup.findAll('link', attrs={"type" : "text/css"}):
    yield node
  for node in soup.findAll('style'):
    yield node
  # Get rid of html comments.
  for node in soup.findAll(text=lambda text:isinstance(text, Comment)):
    yield node
  #for node in soup.findAll('object'):
  #  yield node

  for node in soup.findAll():
    classid = node.get('id', '') + node.get('class', '')
    if node.name == 'body':
      continue
    if UNLIKELY_CANDIDATES_RE.match(classid):
      if not OK_MAYBE_ITS_A_CANDIDATE_RE.match(classid):
        dbg('removing: %s, %s' % (node.name, classid))
        yield node


def get_candidates(soup):
  """Get candidate nodes for ranking."""
  candidates = []
  for tag in ('p', 'td', 'pre'):
    for n in soup.findAll(tag):
      p = n.parent
      if not p in candidates:
        if len(_textify(n)) >= 25:
          candidates.append(p)

  # also look for divs where used inappropriately
  # (as in, where they contain no other block level elements.)
  """
  for n in soup.findAll('div'):
    p = n.parent
    if not p in candidates:
      inner_html = n.renderContents()
      if not DIV_TO_P_ELEMENTS_RE.search(inner_html):
        candidates.append(n.parent)
  """
  return candidates
 

def rank(soup):
  """Rank a soup node and its descendants."""
  score = 0
  score += rank_from_tagname(soup)
  score += rank_from_textlengths(soup)
  score += rank_from_classweight(soup)
  score *= rank_by_link_density(soup)
  dbg('Ranked: %s' % score)
  return score


def rank_from_tagname(soup):
  """Given credit to a class depending on its tag name."""
  name = soup.name
  if GOOD_NAMES.match(name):
    return 5
  elif OK_NAMES.match(name):
    return 3
  elif BAD_NAMES.match(name):
    return -3
  elif HORRIBLE_NAMES.match(name):
    return -5
  return 0


def rank_from_classweight(soup):
  """Give credit if class or id matches different sets."""
  score = 0
  for css_type in ('class', 'id'):
    if css_type in soup:
      val = soup[css_type]
      if NEGATIVE_RE.match(val):
        score -= 50
      elif POSITIVE_RE.match(val):
        score += 25
  return score


def rank_from_textlengths(soup):
  """Rank by length of paragraph blocks and length of text."""
  score = 0
  for p in soup.findAll('p'):
    text = p.renderContents()
    score += text.count(',')
    if len(text) > 10:
      score += 1
  return score


def rank_by_link_density(soup):
  """Get density of links as percentage of the content.
  1 - (amount of text that is inside a link)/(total text in the node).
  """
  link_length = 0
  for a in soup.findAll('a'):
    link_length += len(_textify(a))

  if not link_length:
    return 1
  total_length = float(len(_textify(soup)))
  retval = 1 - link_length/total_length
  dbg('density: %s' % retval)
  return retval


def strip_junk_tags(soup):
  """Remove all elements that look fishy."""
  for tag in 'table', 'ul', 'div':
    for node in soup.findAll(tag):
      if is_fishy(node):
        node.extract()

def is_fishy(soup):
  """Return true if a node probably shouldn't be included."""

  # Look at score and classweight first.
  score = soup.__dict__.get('score', 0)
  classweight = rank_from_classweight(soup)
  if score + classweight < 0:
    return True

  # Next look at counts of text, images, etc.
  # If there are not very many commas, and the number of
  # non-paragraph elements is more than paragraphs or other ominous signs
  # remove the element.
  text = _textify(soup)
  if text.count(',') > 10:
    return False

  text_length = len(text)
  p_count = len(soup.findAll('p'))
  img_count = len(soup.findAll('img'))
  li_count = len(soup.findAll('li')) - 100
  input_count = len(soup.findAll('input'))
  link_density = 1.0 - rank_by_link_density(soup)

  if img_count > p_count:
    return True
  if li_count > p_count and soup.name not in ['ul', 'ol']:
    return True
  if input_count > p_count / 3:
    return True
  if text_length < 25 and (img_count == 0 or img_count > 2):
    return True
  if classweight < 25 and link_density > 0.2:
    return True
  if classweight >= 25 and link_density > 0.5:
    return True

  return False


if __name__ == '__main__':
  data = open(
      'testdata/onion-stephen_hawking_robotic_exoskeleton.html', 'r').read()
  print get_text(data)
  

