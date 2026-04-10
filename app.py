import streamlit as st
import feedparser
import re
from datetime import datetime, timezone, timedelta
import urllib.parse
from typing import List, Dict, Optional, Tuple
import concurrent.futures
import requests
from bs4 import BeautifulSoup

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="뉴스 랭킹",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

KST = timezone(timedelta(hours=9))

# ── Custom CSS (라이트 테마) ──────────────────────────────────────────────────
st.markdown("""
<style>
    .main { padding-top: 1rem; }

    /* 카드 */
    .news-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        transition: box-shadow 0.2s, border-color 0.2s;
    }
    .news-card:hover { border-color: #2563eb; box-shadow: 0 2px 10px rgba(37,99,235,0.1); }

    /* 조합 카드 */
    .combo-card {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 10px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.6rem;
    }
    .combo-header {
        font-size: 0.9rem;
        font-weight: 800;
        color: #111827;
        margin-bottom: 0.7rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid #e2e8f0;
    }
    .combo-angle {
        font-size: 0.72rem;
        color: #059669;
        font-weight: 700;
        letter-spacing: 0.03em;
        margin-bottom: 0.25rem;
    }

    /* 순위 숫자 */
    .news-rank {
        font-size: 1.5rem;
        font-weight: 900;
        color: #2563eb;
        min-width: 2.5rem;
        display: inline-block;
    }

    /* 제목 링크 */
    .news-title {
        font-size: 1.02rem;
        font-weight: 600;
        color: #111827;
        text-decoration: none;
        line-height: 1.45;
    }
    .news-title:hover { color: #2563eb; text-decoration: underline; }

    .combo-title {
        font-size: 0.87rem;
        font-weight: 600;
        color: #1e293b;
        text-decoration: none;
        line-height: 1.4;
    }
    .combo-title:hover { color: #059669; text-decoration: underline; }

    /* 메타 / 요약 */
    .news-meta    { font-size: 0.8rem;  color: #6b7280; margin-top: 0.3rem; }
    .news-summary { font-size: 0.88rem; color: #374151; margin-top: 0.4rem; line-height: 1.55; }
    .press-hint   { font-size: 0.75rem; color: #92400e; margin-top: 0.25rem; font-style: italic; }

    /* 뱃지 */
    .badge {
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        margin-right: 0.35rem;
    }
    .badge-source  { background: #ede9fe; color: #5b21b6; }
    .badge-score   { background: #dcfce7; color: #166534; }
    .badge-rel     { background: #dbeafe; color: #1e40af; }
    .badge-new     { background: #fee2e2; color: #991b1b; }
    .badge-press   { background: #fff7ed; color: #9a3412; border: 1px solid #fed7aa; }
    .badge-article { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }

    /* 점수 바 */
    .score-bar-wrap { background: #f1f5f9; border-radius: 4px; height: 5px; margin-top: 0.6rem; }
    .score-bar      { height: 5px; border-radius: 4px; background: linear-gradient(90deg, #2563eb, #7c3aed); }

    /* 메트릭 */
    div[data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.6rem 1rem;
    }
    div[data-testid="stMetricLabel"] p,
    div[data-testid="stMetricLabel"] { color: #374151 !important; font-size: 0.82rem !important; }
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] > div { color: #111827 !important; font-size: 1.4rem !important; }

    /* 사이드바 헤더 */
    .filter-header {
        color: #2563eb;
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.4rem;
    }
</style>
""", unsafe_allow_html=True)

# ── RSS Source definitions ────────────────────────────────────────────────────
STATIC_SOURCES = {
    "연합뉴스":  "https://www.yonhapnews.co.kr/rss/newsflash.xml",
    "한겨레":    "https://www.hani.co.kr/rss/",
    "KBS":       "https://news.kbs.co.kr/rss/rss.xml",
    "SBS":       "https://news.sbs.co.kr/news/rss.do?plink=RSSREADER",
    "MBC":       "https://imnews.imbc.com/rss/news/news_00.xml",
    "조선일보":  "https://www.chosun.com/arc/outboundfeeds/rss/",
    "중앙일보":  "https://rss.joins.com/joins_news_list.xml",
    "경향신문":  "https://www.khan.co.kr/rss/rssdata/total_news.xml",
    "국민일보":  "https://rss.kmib.co.kr/data/kmibRssAll.xml",
    "매일경제":  "https://www.mk.co.kr/rss/30000001/",
    "한국경제":  "https://www.hankyung.com/feed/all-news",
}

# 출처 신뢰도 (originality 선택 시 우선순위)
SOURCE_AUTHORITY = {
    "KBS": 10, "MBC": 10, "SBS": 10,
    "한겨레": 9, "경향신문": 9,
    "조선일보": 8, "중앙일보": 8,
    "연합뉴스": 7, "국민일보": 7,
    "매일경제": 6, "한국경제": 6,
    "Google News": 4,
    "Naver News": 5,
}

NAVER_CLIENT_ID     = "kbhC5JejwrgqDv6RV8EI"
NAVER_CLIENT_SECRET = "qNJTlKcJYj"

def fetch_naver_news(keyword: str, limit: int = 100) -> List[Dict]:
    """네이버 뉴스 검색 API로 기사 수집."""
    try:
        enc = urllib.parse.quote(keyword)
        url = f"https://openapi.naver.com/v1/search/news.json?query={enc}&display={limit}&sort=sim"
        resp = requests.get(url, headers={
            "X-Naver-Client-Id":     NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        }, timeout=8)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        articles = []
        for item in items:
            title   = strip_html(item.get("title",       "") or "")
            summary = strip_html(item.get("description", "") or "")
            link    = item.get("originallink") or item.get("link", "")
            pub_str = item.get("pubDate", "")
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(pub_str).astimezone(timezone.utc).replace(tzinfo=timezone.utc)
            except Exception:
                date = None
            rel    = relevance_score(title, summary, keyword)
            rec    = recency_score(date)
            tq     = title_quality_score(title)
            purity = topic_purity_score(title, keyword)
            domain = domain_trust_score(link)
            art_type, pr_score = classify_article(title, summary, "Naver News")
            articles.append({
                "title":    title,
                "link":     link,
                "summary":  summary[:1000] if summary else "",
                "date":     date,
                "source":   "Naver News",
                "rel":      rel,
                "rec":      rec,
                "tq":       tq,
                "purity":   purity,
                "domain":   domain,
                "score":    round(total_score(rel, rec, tq, purity, 0.5, art_type) * domain, 4),
                "art_type": art_type,
                "pr_score": pr_score,
            })
        return articles
    except Exception:
        return []

def get_google_news_url(keyword: str) -> str:
    enc = urllib.parse.quote(keyword)
    return f"https://news.google.com/rss/search?q={enc}&hl=ko&gl=KR&ceid=KR:ko"

# ── Date helpers ──────────────────────────────────────────────────────────────
def parse_date(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def today_start_utc() -> datetime:
    """오늘 KST 00:00 를 UTC로 변환."""
    now_kst = datetime.now(KST)
    start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_kst.astimezone(timezone.utc)

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()

# ── Scoring ───────────────────────────────────────────────────────────────────
def relevance_score(title: str, summary: str, keyword: str) -> float:
    if not keyword:
        return 0.5
    kws = [k.strip().lower() for k in keyword.split() if k.strip()]
    if not kws:
        return 0.5

    full_text = (title + " " + summary).lower()

    # ── 필수 조건: 모든 키워드가 제목+요약 어딘가에 있어야 함 ──
    if not all(k in full_text for k in kws):
        return 0.0  # 하나라도 없으면 완전 제외

    def hits(text: str) -> float:
        t = text.lower()
        return sum(1 for k in kws if k in t) / len(kws)

    # … 가 따옴표 안에 있는지 판별 (인용구 줄임표 vs 제목 이어쓰기)
    # ex) "미처 헤아리지 못해…부동산 차익" → 인용구 안  → 강한 패널티
    # ex) 대출 절반 이하로...부동산 규제 → 제목 이어쓰기 → 약한 패널티
    in_quote_ellipsis = bool(re.search(r'[""""][^"""]*[…\.]{2,}', title))

    has_ellipsis = "…" in title or "..." in title
    if has_ellipsis:
        main_title = re.split(r"[…]|\.{2,}", title)[0]
    else:
        main_title = title

    main_hit  = hits(main_title)
    total_hit = hits(title)

    if main_hit > 0:
        title_score = main_hit * 0.70            # 주요부에 있음 → 정상
    elif total_hit > 0:
        if in_quote_ellipsis:
            title_score = total_hit * 0.08       # 인용구 안 줄임표 → 강한 패널티
        else:
            title_score = total_hit * 0.50       # 제목 이어쓰기 → 약한 패널티만
    else:
        title_score = 0.0

    # 요약 앞 60자에 없으면 감점
    if hits(summary[:60]) > 0:
        summary_score = hits(summary) * 0.30
    else:
        summary_score = hits(summary) * 0.12

    return round(title_score + summary_score, 4)

def recency_score(pub_date: Optional[datetime]) -> float:
    if not pub_date:
        return 0.25
    hours = (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600
    if hours < 1:   return 1.00
    if hours < 3:   return 0.90
    if hours < 6:   return 0.80
    if hours < 12:  return 0.70
    if hours < 24:  return 0.60
    if hours < 48:  return 0.45
    if hours < 72:  return 0.35
    if hours < 168: return 0.20
    return 0.10

_BROADCAST_PREFIX_RE = re.compile(r"^\[.{1,15}\]")   # [퇴근길머니], [단신], [브리핑]
_MULTI_TOPIC_RE      = re.compile(r"[…·＆&]{1}|/{1}")  # 복합 주제 구분자

# 주요 한국 언론 도메인 (신뢰 출처)
_TRUSTED_DOMAINS = {
    "yonhapnews.co.kr", "yna.co.kr", "hani.co.kr", "kbs.co.kr", "mbc.co.kr",
    "sbs.co.kr", "chosun.com", "joongang.co.kr", "joins.com", "khan.co.kr",
    "kmib.co.kr", "mk.co.kr", "hankyung.com", "donga.com", "hankookilbo.com",
    "newsis.com", "news1.kr", "ohmynews.com", "pressian.com", "mediatoday.co.kr",
    "sisain.co.kr", "ytn.co.kr", "mbn.co.kr", "jtbc.co.kr", "tvchosun.com",
    "edaily.co.kr", "etoday.co.kr", "fnnews.com", "sedaily.com", "etnews.com",
    "dt.co.kr", "inews24.com", "zdnet.co.kr", "bloter.net",
}

def title_quality_score(title: str) -> float:
    if not title:
        return 0.0
    n = len(title)
    score = 0.5

    # 길이 점수
    if 15 <= n <= 65:      score += 0.3
    elif n < 8 or n > 90:  score -= 0.3

    # 구체성 (숫자 포함)
    if re.search(r"\d", title):         score += 0.1
    if re.search(r'["""\'「」]', title): score += 0.05

    # 전부 대문자
    if title == title.upper() and n > 5: score -= 0.2

    # 방송 코너/프로그램 접두사 → 방송 스크립트일 가능성 높음
    if _BROADCAST_PREFIX_RE.match(title): score -= 0.35

    # … 으로 여러 주제를 묶은 제목 (뉴스레터/라디오 형식)
    ellipsis_count = title.count("…")
    if ellipsis_count >= 1: score -= 0.25 * ellipsis_count

    return max(0.0, min(1.0, score))

def topic_purity_score(title: str, keyword: str) -> float:
    """
    제목이 키워드에 얼마나 집중되어 있는지.
    …, ·, & 등으로 여러 주제가 섞이면 purity 하락.
    """
    if not title or not keyword:
        return 0.5
    kws = [k.strip().lower() for k in keyword.split() if k.strip()]

    # 복합 구분자로 분리
    segments = re.split(r"[…·/＆&]", title)
    if len(segments) <= 1:
        return 1.0  # 단일 주제

    relevant = sum(1 for s in segments if any(k in s.lower() for k in kws))
    purity = relevant / len(segments)

    # 3개 이상 세그먼트는 추가 패널티
    if len(segments) >= 3:
        purity *= 0.6

    return round(purity, 3)

def domain_trust_score(link: str) -> float:
    """주요 언론 도메인이면 1.0, 미확인 출처면 0.70."""
    try:
        netloc = urllib.parse.urlparse(link).netloc.lower()
        netloc = re.sub(r"^www\.", "", netloc)
        if any(td in netloc for td in _TRUSTED_DOMAINS):
            return 1.0
    except Exception:
        pass
    return 0.70

def total_score(rel: float, rec: float, tq: float, purity: float,
                content_q: float = 0.5, art_type: str = "보도자료") -> float:
    base = (rel * 0.35 + rec * 0.25 + tq * 0.10
            + purity * 0.15 + content_q * 0.15)
    multiplier = 1.0 if art_type == "기사" else 0.70
    return round(base * multiplier, 4)

# ── 본문 수집 & 품질 분석 ─────────────────────────────────────────────────────
# 언론사별 본문 CSS 셀렉터 (우선순위 순)
_ARTICLE_SELECTORS = [
    "article", ".article-body", ".article_body", ".article-content",
    ".article-txt", ".article_content", ".news-article-body",
    "#articleBodyContents", "#article-view-content-div",
    ".par", ".story-news-article", ".view_con", "main article",
]

def fetch_article_text(url: str, timeout: int = 5) -> str:
    """기사 URL에서 본문 텍스트를 추출. 실패 시 빈 문자열."""
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; NewsRanker/1.0)"},
                         allow_redirects=True)
        if r.status_code != 200:
            return ""
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        # 불필요한 태그 제거
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "figure", "iframe", "form"]):
            tag.decompose()
        # 언론사 전용 셀렉터 시도
        for sel in _ARTICLE_SELECTORS:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 300:
                    return text[:4000]
        # 폴백: <p> 태그 전체
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paras if len(p) > 40)
        return text[:4000]
    except Exception:
        return ""

def content_relevance(text: str, keyword: str) -> float:
    """
    본문에서 키워드 밀도를 측정.
    1000자당 등장 횟수 기준으로 점수화.
    제목에서 스치듯 언급된 키워드가 본문에도 없으면 낮은 점수.
    """
    if not text or not keyword:
        return 0.5  # 본문 없으면 중립
    kws = [k.strip().lower() for k in keyword.split() if k.strip()]
    text_lower = text.lower()
    count = sum(text_lower.count(k) for k in kws)
    density = count / (max(len(text), 1) / 1000)  # 1000자당 등장 횟수

    if density >= 6:   return 1.00
    if density >= 3:   return 0.85
    if density >= 1.5: return 0.70
    if density >= 0.5: return 0.45
    return 0.15  # 본문에 거의 없음 → 주제 아님

def content_quality_score(text: str) -> float:
    """
    본문 텍스트로 기사 품질을 측정.
    - 길이: 기사다운 분량인지
    - 인용: 다수 출처 인용 여부
    - 데이터: 숫자·통계 풍부도
    - 구조: 문단 수 (단순 나열 vs 구조적 서술)
    """
    if not text:
        return 0.5   # 본문 수집 실패 → 중립

    score = 0.5
    n = len(text)

    # 길이 (글자 수 기준)
    if n > 2000:   score += 0.20
    elif n > 1000: score += 0.12
    elif n > 500:  score += 0.05
    elif n < 200:  score -= 0.20

    # 인용 풍부도 (따옴표·인용동사)
    quote_chars = text.count('"') + text.count('"') + text.count('"')
    quote_verbs = len(re.findall(r"(말했|밝혔|전했|지적했|설명했|강조했|주장했)", text))
    quote_total = quote_chars // 2 + quote_verbs
    if quote_total >= 5:   score += 0.12
    elif quote_total >= 2: score += 0.06

    # 데이터·숫자 밀도
    num_matches = len(re.findall(r"\d[\d,\.]*\s*(%|원|명|건|개|배|위|년|월|일)", text))
    if num_matches >= 8:   score += 0.10
    elif num_matches >= 4: score += 0.05

    # 복수 출처 언급
    source_markers = len(re.findall(
        r"(에 따르면|관계자|전문가|교수|연구원|분석가|애널리스트)", text))
    if source_markers >= 3: score += 0.08
    elif source_markers >= 1: score += 0.03

    return round(max(0.0, min(1.0, score)), 3)

def enrich_with_content(articles: List[Dict], keyword: str, top_n: int = 10) -> None:
    """
    상위 N개 기사의 본문을 병렬로 가져와 in-place 업데이트.
    - content_q  : 본문 품질 (길이·인용·데이터 밀도)
    - content_rel: 본문 내 키워드 밀도 → 제목 관련도와 합산해 최종 rel 재계산
    """
    targets = articles[:top_n]

    def _fetch(art: Dict):
        text = fetch_article_text(art["link"])
        art["content_text"] = text
        art["content_q"]    = content_quality_score(text)
        art["content_rel"]  = content_relevance(text, keyword)

        # 최종 관련도: 제목 기반 40% + 본문 기반 60%
        final_rel = art["rel"] * 0.40 + art["content_rel"] * 0.60
        art["final_rel"] = round(final_rel, 4)

        art["score"] = round(
            total_score(final_rel, art["rec"], art["tq"],
                        art["purity"], art["content_q"], art["art_type"])
            * art["domain"], 4
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(_fetch, targets))

# ── 보도자료 vs 기사 분류 ─────────────────────────────────────────────────────
_PR_TITLE_RE = [re.compile(p) for p in [
    r"^[\(\[]?[A-Za-z가-힣\s·]+[\)\]]?\s*,\s+.{2,}(출시|발표|론칭|공개|선보|출범|체결|협약|MOU|채용|모집|수상|선정|달성|돌파|기록|확보|투자|인수|합병)",
    r"(출시|론칭|새롭게 선보|공식 출시|정식 출시|새 버전|업데이트 출시)",
    r"(MOU|업무협약|협약 체결|양해각서)\s*(체결|맺어|서명)",
    r"(모집|채용|지원)\s*(공고|안내|시작)",
    r"(수상|선정|인증|인정받|선발)\s*(됐|됩|했|합)",
    r"(억\s*원|조\s*원).{0,10}(투자|유치|조달|펀딩)",
    r"(보도자료|뉴스와이어|PRNewswire|Business Wire)",
    # 금융회사 홍보형 패턴
    r"(혜택|캐시백|적립|할인|이벤트|프로모션).{0,15}(출시|선보|시작|제공|강화)",
    r"(신규|새|새로운)\s*.{0,10}(카드|상품|서비스|혜택|기능)\s*(출시|선보|공개|출시)",
    r"(제휴|파트너십|협력)\s*.{0,10}(체결|강화|확대|맺)",
    r"(한도|연회비|금리|수수료).{0,15}(인하|인상|혜택|면제|우대)",
]]
_PR_SUMMARY_RE = [re.compile(p) for p in [
    r"(대표(이사)?|CEO|부사장|전무|상무|이사)\s*[는은]\s*.{2,40}(말했|밝혔|전했|강조했)",
    r"(관계자)\s*[는은]\s*.{2,40}(말했|밝혔|전했)",
    r"(주요\s*기능|특징\s*[은는이가]|장점\s*[은는이가])",
    r"(보도자료|뉴스와이어|연락처\s*:|문의\s*:)",
    r"(홈페이지|공식\s*사이트|www\.|http).{0,30}(참고|참조|방문)",
]]
_NEWS_TITLE_RE = [re.compile(p) for p in [
    r"(단독|특종|취재|탐사|심층|분석|추적|인터뷰|현장)",
    r"[?？]$",
    r"(논란|비판|지적|우려|문제|갈등|충돌|파문|의혹|수사|조사|고발|제보)",
    r"(전문가|학자|교수|연구원).{0,10}(분석|평가|전망|지적|경고)",
    r"(왜|어떻게|무엇이|누가).{2,}(됐|됩|일까|인가)",
]]
_NEWS_SUMMARY_RE = [re.compile(p) for p in [
    r"(취재\s*결과|확인한\s*결과|조사\s*결과)",
    r"(복수의\s*(관계자|소식통|전문가)|여러\s*(전문가|관계자))",
    r"(반면|그러나|하지만).{3,}(지적|우려|비판)",
    r"(정부|당국|수사기관).{0,10}(조사|수사|점검|제재)",
]]
_SOURCE_BIAS = {
    "한겨레": +0.15, "경향신문": +0.15,
    "KBS": +0.10, "MBC": +0.10, "SBS": +0.10,
    "조선일보": +0.05, "중앙일보": +0.05,
    "연합뉴스": 0.0, "국민일보": 0.0,
    "매일경제": -0.05, "한국경제": -0.05,
    "Google News": 0.0,
    "Naver News":  0.0,
}

def classify_article(title: str, summary: str, source: str) -> Tuple[str, float]:
    pr_score = news_score = 0.0
    for pat in _PR_TITLE_RE:
        if pat.search(title): pr_score += 0.25
    for pat in _NEWS_TITLE_RE:
        if pat.search(title): news_score += 0.25
    for pat in _PR_SUMMARY_RE:
        if pat.search(summary): pr_score += 0.20
    for pat in _NEWS_SUMMARY_RE:
        if pat.search(summary): news_score += 0.20
    bias = _SOURCE_BIAS.get(source, 0.0)
    pr_score   = max(0.0, min(1.0, pr_score - bias))
    news_score = max(0.0, min(1.0, news_score + bias))
    label = "기사" if (pr_score - news_score) < -0.15 else "보도자료"
    return label, round(pr_score, 2)

# ── 유사도 & 원본 선택 ────────────────────────────────────────────────────────
_KR_PARTICLES   = {"과","와","이","가","을","를","의","에","로","은","는","도","만","서","랑","이랑"}
_KR_PARTICLES_2 = {"으로","에서","과의","와의","에게","한테","에도","로의","이라"}

def _strip_particle(token: str) -> str:
    if len(token) <= 2:
        return token
    if len(token) > 3 and token[-2:] in _KR_PARTICLES_2:
        return token[:-2]
    if token[-1] in _KR_PARTICLES:
        return token[:-1]
    return token

def title_tokens(title: str) -> set:
    """관련도·점수용 토큰."""
    raw = re.findall(r"[가-힣]{2,}|[A-Za-z0-9]+", title.lower())
    return {_strip_particle(t) for t in raw}

def _dedup_tokens(title: str) -> set:
    """
    중복 탐지 전용 토큰.
    - 끝의 ' - 출처명' 제거
    - [섹션명] 제거
    - 3자 이상 토큰만 사용 (단어 노이즈 감소)
    """
    t = re.sub(r"\s*[-–]\s*\S+$", "", title)   # ' - 파이낸셜뉴스' 등 제거
    t = re.sub(r"\[.{1,20}\]", "", t)           # '[fn마켓워치]' 등 제거
    t = re.sub(r"[''""\"\']+", "", t)           # 따옴표 제거
    raw = re.findall(r"[가-힣]{3,}|[A-Za-z]{3,}|[0-9]+", t.lower())
    return {_strip_particle(tok) for tok in raw}

def jaccard(t1: str, t2: str) -> float:
    a, b = _dedup_tokens(t1), _dedup_tokens(t2)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def pick_original(group: List[Dict]) -> Dict:
    """유사 기사 그룹에서 가장 원본에 가까운 기사를 선택."""
    def originality_key(a: Dict):
        authority  = SOURCE_AUTHORITY.get(a["source"], 4)
        type_bonus = 5 if a["art_type"] == "기사" else 0
        # 같은 그룹 내에서는 먼저 나온 기사가 원본
        time_score = -a["date"].timestamp() if a["date"] else 0
        detail     = len(a.get("summary", "")) / 50
        return -(authority + type_bonus + detail), time_score  # 낮을수록 우선

    return sorted(group, key=originality_key)[0]

def deduplicate_by_originality(articles: List[Dict], threshold: float = 0.40) -> List[Dict]:
    """유사 기사를 그룹화하고 각 그룹의 원본만 남긴다."""
    assigned = [False] * len(articles)
    result = []
    for i, a in enumerate(articles):
        if assigned[i]:
            continue
        group = [a]
        assigned[i] = True
        for j in range(i + 1, len(articles)):
            if not assigned[j] and jaccard(a["title"], articles[j]["title"]) >= threshold:
                group.append(articles[j])
                assigned[j] = True
        result.append(pick_original(group))
    return result

# ── 조합추천 ──────────────────────────────────────────────────────────────────
# 제목에서 각도(angle)를 대표하는 키워드 추출
_ANGLE_KEYWORDS = {
    "정책/규제": r"(정부|규제|법|정책|국회|입법|행정|당국|부처)",
    "시장/경제": r"(시장|주가|매출|실적|수익|투자|경쟁|점유율|성장)",
    "기술/혁신": r"(기술|AI|인공지능|개발|출시|혁신|특허|연구)",
    "사회/여론": r"(논란|여론|반응|시민|소비자|비판|우려|찬반)",
    "국제/외교": r"(미국|중국|일본|글로벌|수출|무역|외교|협력)",
    "기업/산업": r"(기업|업계|산업|회사|대기업|스타트업|공장|생산)",
    "인물/동향": r"(대표|CEO|임원|인터뷰|발언|행보|동향)",
    "사건/사고": r"(사건|사고|화재|피해|부상|사망|수사|조사)",
}
_ANGLE_RE = {k: re.compile(v) for k, v in _ANGLE_KEYWORDS.items()}

def detect_angle(title: str, summary: str) -> str:
    text = title + " " + summary
    for angle, pat in _ANGLE_RE.items():
        if pat.search(text):
            return angle
    return "기타"

def find_combo_candidates(articles: List[Dict], max_combo: int = 5) -> List[Dict]:
    """
    서로 다른 각도를 가진 기사 2~5개를 찾아 조합추천으로 반환.
    - 기사 유형 우선, 없으면 보도자료도 포함
    - 상호 Jaccard 유사도 < 0.50 (서로 다른 내용)
    - 각도(angle)가 다양할수록 우선 선택, 단 조건 미충족 시 같은 각도도 허용
    """
    priority  = [a for a in articles if a["art_type"] == "기사"]
    fallback  = [a for a in articles if a["art_type"] != "기사"]
    candidates = priority + fallback
    if len(candidates) < 2:
        return []

    for a in candidates:
        if "angle" not in a:
            a["angle"] = detect_angle(a["title"], a["summary"])

    selected: List[Dict] = []

    for a in sorted(candidates, key=lambda x: x["score"], reverse=True):
        if len(selected) >= max_combo:
            break
        too_similar = any(jaccard(a["title"], s["title"]) >= 0.50 for s in selected)
        if too_similar:
            continue
        angle_count = sum(1 for s in selected if s["angle"] == a["angle"])
        if angle_count >= 2:
            continue
        selected.append(a)

    return selected if len(selected) >= 2 else []


# 스토리 단계 매핑: 각도 → (순서, 단계 라벨, 이모지)
_STORY_STAGES = {
    "정책/규제":  (1, "배경", "📋"),
    "국제/외교":  (1, "배경", "📋"),
    "기업/산업":  (2, "현황", "📊"),
    "시장/경제":  (2, "현황", "📊"),
    "기술/혁신":  (2, "현황", "📊"),
    "사건/사고":  (3, "쟁점", "⚡"),
    "사회/여론":  (3, "쟁점", "⚡"),
    "인물/동향":  (4, "전망", "🔭"),
    "기타":       (4, "전망", "🔭"),
}

def build_storyboard(combo: List[Dict]) -> List[Dict]:
    """조합추천 기사를 배경→현황→쟁점→전망 순으로 정렬."""
    def stage_order(a):
        return _STORY_STAGES.get(a.get("angle", "기타"), (4, "전망", "🔭"))[0]
    return sorted(combo, key=stage_order)

def _clean_sentence(text: str, max_len: int = 60) -> str:
    """요약/제목에서 첫 의미 단위를 추출."""
    text = re.sub(r"\s*[-–]\s*\S{2,}$", "", text)   # '- 출처명' 제거
    text = re.sub(r"\[.{1,20}\]", "", text).strip()  # '[섹션]' 제거
    # 첫 문장(마침표·줄바꿈) 추출
    sent = re.split(r"[.。\n]", text)[0].strip()
    if len(sent) > max_len:
        return sent[:max_len] + "…"
    return sent

def synthesize_story(combo: List[Dict]) -> tuple:
    """
    스토리보드 기사들을 엮어 짧은 요약 단락과 출처 목록을 반환.
    각 단계별로 요약 첫 문장을 추출해 연결.
    """
    storyboard = build_storyboard(combo)

    # 단계별로 첫 번째 기사만 사용
    stage_items: dict = {}
    for a in storyboard:
        angle = a.get("angle", "기타")
        order, label, emoji = _STORY_STAGES.get(angle, (4, "전망", "🔭"))
        if order not in stage_items:
            raw = (a.get("summary") or a["title"]).strip()
            stage_items[order] = {
                "label":   label,
                "emoji":   emoji,
                "sent":    _clean_sentence(raw),
                "source":  a["source"],
                "link":    a["link"],
            }

    if not stage_items:
        return "", []

    # 단계 순으로 문장 연결
    orders = sorted(stage_items)
    parts = []
    for i, order in enumerate(orders):
        item = stage_items[order]
        sent = item["sent"]
        is_last = (i == len(orders) - 1)
        # 마지막 문장은 마침표, 나머지는 쉼표
        parts.append(sent + ("." if is_last else ","))

    paragraph = " ".join(parts)
    sources = list(dict.fromkeys(stage_items[o]["source"] for o in orders))  # 순서 유지 중복 제거
    return paragraph, sources

# ── 리서치 분석 함수 ──────────────────────────────────────────────────────────
from collections import Counter

# 너무 흔해서 의미 없는 불용어
_STOPWORDS = {
    "이어", "위해", "대해", "통해", "으로", "에서", "에게", "지만", "하지", "하고",
    "있어", "없어", "이번", "지난", "올해", "내년", "오늘", "어제", "최근", "현재",
    "관련", "대한", "따른", "한편", "이후", "이전", "이상", "이하", "이날", "같은",
    "모든", "각각", "일부", "전체", "해당", "기자", "뉴스", "기사", "발표", "공개",
}

def extract_top_keywords(articles: List[Dict], keyword: str, top_n: int = 18) -> List[tuple]:
    """제목+요약에서 자주 등장하는 의미 있는 단어 추출."""
    exclude = set(keyword.lower().split()) | _STOPWORDS
    counter: Counter = Counter()
    for a in articles:
        tokens = re.findall(r"[가-힣]{2,4}", a["title"] + " " + a["summary"])
        for t in tokens:
            if t not in exclude:
                counter[t] += 1
    return [(w, c) for w, c in counter.most_common(top_n) if c >= 2]

def tag_angles(articles: List[Dict]) -> None:
    """articles에 angle 필드를 in-place로 태깅."""
    for a in articles:
        if "angle" not in a:
            a["angle"] = detect_angle(a["title"], a["summary"])

def coverage_analysis(articles: List[Dict]) -> tuple:
    """커버된 각도와 빠진 각도를 반환."""
    covered = {a.get("angle", "기타") for a in articles} - {"기타"}
    all_angles = set(_ANGLE_KEYWORDS.keys())
    missing = sorted(all_angles - covered)
    return sorted(covered), missing

def suggest_searches(top_kw: List[tuple], keyword: str, n: int = 6) -> List[str]:
    """핵심 키워드 + 원본 검색어 조합으로 추가 리서치 검색어 제안."""
    base_tokens = set(keyword.split())
    suggestions = []
    for w, _ in top_kw:
        if w not in keyword:
            suggestions.append(f"{keyword} {w}")
        if len(suggestions) >= n:
            break
    return suggestions

# ── Fetching ──────────────────────────────────────────────────────────────────
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewsRanker/1.0)"}

def fetch_feed(url: str, source: str, keyword: str, limit: int = 40) -> List[Dict]:
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        articles = []
        for entry in feed.entries[:limit]:
            title   = strip_html(getattr(entry, "title",   "") or "")
            summary = strip_html(getattr(entry, "summary", "") or "")
            link    = getattr(entry, "link", "") or ""
            date    = parse_date(entry)
            rel = relevance_score(title, summary, keyword)
            if rel == 0.0 and source != "Google News":
                continue
            rec     = recency_score(date)
            tq      = title_quality_score(title)
            purity  = topic_purity_score(title, keyword)
            domain  = domain_trust_score(link)
            art_type, pr_score = classify_article(title, summary, source)
            articles.append({
                "title":    title,
                "link":     link,
                "summary":  summary[:1000] if summary else "",
                "date":     date,
                "source":   source,
                "rel":      rel,
                "rec":      rec,
                "tq":       tq,
                "purity":   purity,
                "domain":   domain,
                "score":    round(total_score(rel, rec, tq, purity, 0.5, art_type) * domain, 4),
                "art_type": art_type,
                "pr_score": pr_score,
            })
        return articles
    except Exception:
        return []

def fetch_all(keyword: str, selected_sources: List[str]) -> List[Dict]:
    tasks = {"Google News": get_google_news_url(keyword)}
    for src in selected_sources:
        if src in STATIC_SOURCES:
            tasks[src] = STATIC_SOURCES[src]
    all_articles: List[Dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
        futures = {ex.submit(fetch_feed, url, src, keyword): src
                   for src, url in tasks.items()}
        naver_future = ex.submit(fetch_naver_news, keyword)
        for f in concurrent.futures.as_completed(futures):
            all_articles.extend(f.result())
        all_articles.extend(naver_future.result())
    return all_articles

# ── 출처 판별 ─────────────────────────────────────────────────────────────────
# Google News 제목 끝 " - 출처명" 에서 출처명이 한국 주요 언론사인지 확인하기 위한 목록
_MAJOR_KR_OUTLET_NAMES = {
    "연합뉴스", "뉴시스", "뉴스1", "kbs", "mbc", "sbs", "ytn", "mbn", "jtbc",
    "tv조선", "채널a", "조선일보", "조선비즈", "중앙일보", "중앙선데이", "동아일보",
    "한겨레", "경향신문", "국민일보", "서울신문", "한국일보", "세계일보",
    "매일경제", "한국경제", "파이낸셜뉴스", "서울경제", "이데일리", "머니투데이",
    "아시아경제", "헤럴드경제", "비즈니스워치", "이투데이", "데일리안",
    "오마이뉴스", "프레시안", "미디어오늘", "시사인", "블로터",
    "전자신문", "디지털타임스", "zdnet", "지디넷",
}

def is_major_korean(a: dict) -> bool:
    """주요 국내 언론사 기사인지 판별."""
    # 직접 등록된 RSS 소스 또는 네이버는 무조건 통과
    if a["source"] in STATIC_SOURCES or a["source"] == "Naver News":
        return True

    # 도메인이 신뢰 목록에 있으면 통과
    try:
        netloc = urllib.parse.urlparse(a["link"]).netloc.lower()
        netloc = re.sub(r"^www\.", "", netloc)
        if not netloc.startswith("news.google"):  # Google News 외 직접 링크
            return any(td in netloc for td in _TRUSTED_DOMAINS)
    except Exception:
        pass

    # Google News 기사: 제목 끝 " - 출처명" 파싱
    outlet_match = re.search(r"\s+-\s+([^-|]+)$", a["title"])
    if outlet_match:
        outlet = outlet_match.group(1).strip().lower()
        # 알려진 주요 한국 언론사 이름과 비교
        if any(name in outlet for name in _MAJOR_KR_OUTLET_NAMES):
            return True
        # 출처명에 한국어가 있으면 일단 국내 언론사 (소규모 포함될 수 있음)
        # → 주요 언론사 모드에서는 허용하지 않음
        return False

    # 출처명을 알 수 없으면 제목 한국어 비율만으로 판단 (느슨하게)
    korean_ratio = len(re.findall(r"[가-힣]", a["title"])) / max(len(a["title"]), 1)
    return korean_ratio >= 0.5

# ── 국내 기사 판별 ────────────────────────────────────────────────────────────
# 알려진 외국 출처 키워드 (Google News 제목 끝 " - 출처명" 패턴용)
_FOREIGN_OUTLET_RE = re.compile(
    r"(benzinga|reuters|bloomberg|cnbc|bbc|cnn|guardian|nytimes|wsj|"
    r"coindesk|cointelegraph|decrypt|theblock|techcrunch|forbes|"
    r"vietnam|viet|xinhua|kyodo|ap news|afp|ft\.com|"
    r"marketwatch|investing\.com|seeking alpha|motley fool)",
    re.IGNORECASE,
)

def is_korean_article(link: str, title: str, source: str) -> bool:
    """국내 언론사 기사인지 판별."""
    # 직접 등록된 국내 소스면 무조건 통과
    if source in STATIC_SOURCES:
        return True

    # 도메인 체크
    try:
        netloc = urllib.parse.urlparse(link).netloc.lower()
        netloc = re.sub(r"^www\.", "", netloc)
        if netloc.endswith(".kr"):
            return True
        if any(td in netloc for td in _TRUSTED_DOMAINS):
            return True
    except Exception:
        pass

    # Google News 기사: 제목 끝 " - 출처명" 추출 후 판별
    outlet_match = re.search(r"\s+-\s+(.+)$", title)
    if outlet_match:
        outlet = outlet_match.group(1).strip()
        if _FOREIGN_OUTLET_RE.search(outlet):
            return False
        # 영문자로만 된 출처명 → 외국 언론사로 간주
        if re.match(r"^[A-Za-z0-9\s\.\-]+$", outlet):
            return False

    # 제목 한국어 비율이 30% 미만이면 번역/외국 기사
    korean_ratio = len(re.findall(r"[가-힣]", title)) / max(len(title.strip()), 1)
    return korean_ratio >= 0.30

# ── Time formatting ───────────────────────────────────────────────────────────
def time_ago(dt: Optional[datetime]) -> str:
    if not dt:
        return "시간 불명"
    secs = (datetime.now(timezone.utc) - dt).total_seconds()
    if secs < 60:    return f"{int(secs)}초 전"
    if secs < 3600:  return f"{int(secs/60)}분 전"
    if secs < 86400: return f"{int(secs/3600)}시간 전"
    return f"{int(secs/86400)}일 전"

def is_recent(dt: Optional[datetime], hours: int = 3) -> bool:
    if not dt:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() < hours * 3600

# ── 카테고리 정의 ─────────────────────────────────────────────────────────────
CATEGORIES: Dict[str, List[str]] = {
    "은행": [
        "KB국민은행", "신한은행", "하나은행", "우리은행", "NH농협은행",
        "IBK기업은행", "카카오뱅크", "케이뱅크", "토스뱅크", "SC제일은행", "수협은행",
    ],
    "카드": [
        "신한카드", "삼성카드", "KB국민카드", "현대카드", "롯데카드",
        "하나카드", "우리카드", "BC카드", "NH농협카드", "카카오페이",
    ],
    "증권": [
        "미래에셋증권", "한국투자증권", "NH투자증권", "삼성증권", "KB증권",
        "신한투자증권", "키움증권", "하나증권", "메리츠증권", "대신증권",
    ],
    "보험": [
        "삼성생명", "한화생명", "교보생명", "신한라이프", "흥국생명",
        "삼성화재", "현대해상", "KB손해보험", "DB손해보험", "메리츠화재",
    ],
    "게임": [
        "넥슨", "넷마블", "엔씨소프트", "크래프톤", "펄어비스",
        "카카오게임즈", "컴투스", "위메이드", "스마일게이트", "시프트업",
    ],
    "조선": [
        "HD현대중공업", "삼성중공업", "한화오션", "HD현대미포조선", "HD현대삼호중공업",
    ],
    "건설": [
        "현대건설", "GS건설", "대우건설", "HDC현대산업개발",
        "DL이앤씨", "롯데건설", "SK에코플랜트", "포스코이앤씨", "호반건설",
    ],
    "반도체": [
        "삼성전자", "SK하이닉스", "한미반도체", "DB하이텍", "리노공업",
        "원익IPS", "동진쎄미켐", "솔브레인", "피에스케이", "에스앤에스텍",
    ],
    "제약": [
        "삼성바이오로직스", "셀트리온", "유한양행", "한미약품", "종근당",
        "대웅제약", "동아에스티", "녹십자", "일동제약",
    ],
    "배터리": [
        "LG에너지솔루션", "삼성SDI", "SK온", "에코프로비엠", "에코프로",
        "포스코퓨처엠", "엘앤에프", "천보", "솔루스첨단소재", "코스모신소재",
    ],
    "대기업": [
        "삼성", "SK", "LG", "현대차", "롯데", "CJ", "두산", "포스코",
    ],
}

# 보도자료 수집에 강한 소스 (RSS URL)
PR_SOURCES: Dict[str, str] = {
    "뉴스와이어":   "https://www.newswire.co.kr/rss/news.rss",
    "이데일리":     "https://rss.edaily.co.kr/rss/companies.xml",
    "머니투데이":   "https://rss.mt.co.kr/mt_list_rss.xml",
}

def get_pr_google_news_url(keyword: str) -> str:
    """카테고리 모드: '기업명,' 형식으로 검색 (보도자료 특징)."""
    enc = urllib.parse.quote(f"{keyword},")
    return f"https://news.google.com/rss/search?q={enc}&hl=ko&gl=KR&ceid=KR:ko"

_CAT_SKIP_RE = re.compile(
    r"^\s*[\[【\(]?\s*(사설|포토|영상|만화|칼럼|오피니언|카툰|인포그래픽|포토뉴스|사진|동영상)"
    r"|\[포토\]|\[영상\]|\[사설\]|\[칼럼\]|\[만화\]"
    # 저널리즘/분석 prefix
    r"|\[단독\]|\[기고\]|\[분석\]|\[인터뷰\]|\[탐사\]|\[심층\]"
    # 증권 리포트/묶음
    r"|\[리포트\s*브리핑\]|\[.*?톡톡\]|\[.*?이모저모\]|\[.*?브리핑\]"
    # 분석/회고성 bracket (IPO, 사태, 논란, 분석, 그래픽 등)
    r"|\[.*?(IPO|사태|논란|갈등|10년|분쟁|부결|PICK|특징주|압박|분석|이사회|그래픽|현장).*?\]"
    # 기획 시리즈 번호 (①②③ 등)
    r"|\][①②③④⑤⑥⑦⑧⑨⑩]"
    # 스포츠 키워드
    r"|(PO|플레이오프|챔피언결정전|챔프전).{0,10}(1차전|2차전|3차전|격파|진출|탈락|제압|기선)"
    # 주가/증시 기사
    r"|(목표가|주가|강세|약세|상승률|하락률|신고가|신저가|52주).{0,10}(%|원|강세|약세|경신)"
    r"|\d+\.\d+%.{0,5}(강세|약세|상승|하락)"
    r"|(코스피|코스닥).{0,10}(상승|하락|출발|마감|보합)"
    # 증권사 투자의견 리포트
    r"(,\s*(BUY|SELL|매수|매도|중립|보유)\s*$)"
    # 딜링룸 (포토/현장 기사)
    r"|딜링룸"
    # 물음표 또는 의문형 어미로 끝나는 제목
    r"|[?？]\s*$"
    r"|(이룰까|할까|인가|일까|볼까|될까)\s*$"
    # 증권사 타사 분석 리포트 (증권사명 뒤 바로 따옴표)
    r"|(증권|은행|자산운용)\s+[""\"'].+[""\"']"
    # 따옴표로 시작하는 전망/분석
    r'|^[""\'"].+[""\'"].{0,5}$'
    # 노사갈등/사태
    r"|(임단협|파업|노조|갈등|부결|사태).{0,10}(장기화|가나|우려|촉구)"
    # TV/유튜브 쇼·종목 추천 코너
    r"|\[핫종목\]|\[핫스톡.*?\]|\[여의도\s*클라쓰\]|\[.*?클라쓰\]"
    r"|\[.*?현미경\]|\[.*?종목\s*추천\]|\[.*?픽\]"
    # 기관 매매 동향 묶음
    r"|\[(코스피|코스닥)\s*(기관|외국인|개인)\]"
    # 업계 전반 동향 묶음 기사
    r"|업계\s+[''\"'].{2,20}[''\"']\s*(집중|확대|가속|강화|확산)"
    # 전망·바닥·분기 전망 분석 기사
    r"|(전망|바닥\s*다지|2Q|3Q|4Q|1분기|2분기|3분기|4분기).{0,15}(전망|기대|건다|간다)\s*$"
    # 파업/쟁의 단독 언급
    r"|(파업|쟁의행위).{0,20}(열리나|가처분|심리|돌입|예고)",
    re.IGNORECASE,
)

# 묶음 기사 판별: 제목에 중점(·) 2개 이상
_ROUNDUP_RE = re.compile(r"(·.*){2,}")

def fetch_pr_keyword(keyword: str, per_kw: int = 5) -> List[Dict]:
    """
    카테고리 모드 전용 fetch.
    - Google News + PR_SOURCES 수집
    - 24시간 이내 기사만
    - 사설·포토·영상·칼럼 제외
    - 보도자료 점수 우선 정렬
    - 중복 제거 후 per_kw개 반환
    """
    tasks: Dict[str, str] = {"Google News": get_pr_google_news_url(keyword)}
    tasks.update(PR_SOURCES)

    all_arts: List[Dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as ex:
        futures = {ex.submit(fetch_feed, url, src, keyword): src
                   for src, url in tasks.items()}
        naver_future = ex.submit(fetch_naver_news, keyword)
        for f in concurrent.futures.as_completed(futures):
            all_arts.extend(f.result())
        all_arts.extend(naver_future.result())

    if not all_arts:
        return []

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    # 국내 + 24시간 이내 + 사설/포토/분석/묶음/짧은제목 제외
    all_arts = [
        a for a in all_arts
        if is_korean_article(a["link"], a["title"], a["source"])
        and a["date"] and a["date"] >= since_24h
        and not _CAT_SKIP_RE.search(a["title"])
        and not _ROUNDUP_RE.search(a["title"])
        and len(a["title"].strip()) >= 15
    ]

    # 중복 제거
    all_arts = deduplicate_by_originality(all_arts)
    all_arts.sort(key=lambda a: a["rec"], reverse=True)

    # summary에서 "밝혔다" 패턴 체크 (1000자로 확장된 summary 활용)
    _PR_BODY_RE = re.compile(r"(밝혔다|발표했다|선보였다|출시했다|밝혔습니다|발표했습니다)")

    passed = [a for a in all_arts if _PR_BODY_RE.search(a.get("summary", ""))]

    if not passed:
        return all_arts[:per_kw]

    passed.sort(key=lambda a: a["rec"], reverse=True)
    return passed[:per_kw]


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("📰 뉴스 랭킹")
st.caption("키워드 관련도 · 최신순 · 제목 품질 · 유사 기사 중 원본 우선 표시")

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ 필터 설정")

    st.markdown('<p class="filter-header">언론사 선택</p>', unsafe_allow_html=True)
    selected_sources = st.multiselect(
        "추가 언론사",
        options=list(STATIC_SOURCES.keys()),
        default=["연합뉴스", "한겨레", "KBS", "매일경제"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown('<p class="filter-header">결과 설정</p>', unsafe_allow_html=True)
    max_results = st.slider("최대 표시 기사 수", 5, 50, 20, 5)
    weight_rel  = st.slider("관련도 가중치",    0.0, 1.0, 0.50, 0.05)
    weight_rec  = st.slider("최신성 가중치",    0.0, 1.0, 0.35, 0.05)
    weight_tq   = st.slider("제목 품질 가중치", 0.0, 1.0, 0.15, 0.05)

    st.markdown("---")
    st.markdown('<p class="filter-header">정렬 기준</p>', unsafe_allow_html=True)
    sort_by = st.radio("정렬", ["종합 점수", "최신순", "관련도"], label_visibility="collapsed")

    st.markdown("---")
    st.markdown('<p class="filter-header">기간 필터</p>', unsafe_allow_html=True)
    time_filter = st.selectbox(
        "기간",
        ["오늘 (KST 00:00~)", "1시간 이내", "6시간 이내", "24시간 이내", "3일 이내", "7일 이내", "전체"],
        index=0,   # 기본값: 오늘
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown('<p class="filter-header">기사 유형 필터</p>', unsafe_allow_html=True)
    type_filter = st.multiselect(
        "유형", options=["기사", "보도자료"],
        default=["기사", "보도자료"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown('<p class="filter-header">출처 필터</p>', unsafe_allow_html=True)
    source_filter = st.radio(
        "출처 범위",
        ["주요 언론사만", "국내 전체", "전체 (외국 포함)"],
        index=0,
        label_visibility="collapsed",
    )
    if source_filter == "주요 언론사만":
        st.caption("KBS·조선·한겨레·연합 등 검증된 주요 매체만 표시합니다.")
    elif source_filter == "국내 전체":
        st.caption("외국·번역 기사를 제외한 국내 기사를 표시합니다.")

# ── 모드 선택 ─────────────────────────────────────────────────────────────────
mode = st.radio(
    "모드",
    ["🔍 키워드 검색", "📂 카테고리"],
    horizontal=True,
    label_visibility="collapsed",
)
st.markdown("<div style='margin-bottom:0.5rem'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 카테고리 모드
# ══════════════════════════════════════════════════════════════════════════════
if mode == "📂 카테고리":
    cat_tabs = st.tabs(list(CATEGORIES.keys()))

    for tab, cat_name in zip(cat_tabs, CATEGORIES.keys()):
        with tab:
            keywords_in_cat = CATEGORIES[cat_name]
            st.markdown(
                f'<div style="font-size:0.82rem;color:#6b7280;margin-bottom:1rem;">'
                f'수집 키워드: {" · ".join(keywords_in_cat)}</div>',
                unsafe_allow_html=True,
            )

            for kw in keywords_in_cat:
                # 키워드 섹션 헤더
                st.markdown(
                    f'<div style="font-size:1rem;font-weight:800;color:#111827;'
                    f'padding:6px 0 4px;border-bottom:2px solid #2563eb;'
                    f'margin:1.2rem 0 0.8rem;">{kw}</div>',
                    unsafe_allow_html=True,
                )

                with st.spinner(f"{kw} 수집 중..."):
                    kw_arts = fetch_pr_keyword(kw, per_kw=3)

                if not kw_arts:
                    st.caption("수집된 기사가 없습니다.")
                    continue

                for art in kw_arts:
                    rec_label = time_ago(art["date"])
                    pr_label = (
                        '<span style="font-size:0.68rem;color:#9a3412;'
                        'background:#fff7ed;border:1px solid #fed7aa;'
                        'padding:1px 6px;border-radius:999px;margin-left:4px;">보도자료</span>'
                        if art["art_type"] == "보도자료" else ""
                    )
                    st.markdown(f"""
<div class="news-card">
  <div>
    <span style="color:#6b7280;font-size:0.82rem;">{art['source']}</span>{pr_label}
  </div>
  <div style="margin-top:0.4rem;">
    <a class="news-title" href="{art['link']}" target="_blank">{art['title']}</a>
  </div>
  <div class="news-meta">🕐 {rec_label}</div>
</div>
""", unsafe_allow_html=True)

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# 키워드 검색 모드
# ══════════════════════════════════════════════════════════════════════════════
# Search bar
col_input, col_btn = st.columns([5, 1])
with col_input:
    keyword = st.text_input(
        "키워드 입력",
        placeholder="예: 인공지능, 삼성전자, 부동산...",
        label_visibility="collapsed",
    )
with col_btn:
    st.button("검색", use_container_width=True, type="primary")

# ── Search & display ──────────────────────────────────────────────────────────
if keyword:
    with st.spinner(f"**{keyword}** 관련 뉴스를 수집 중..."):
        raw = fetch_all(keyword, selected_sources)

    if not raw:
        st.warning("검색 결과가 없습니다. 키워드를 바꿔보세요.")
        st.stop()

    # 출처 필터
    if source_filter == "주요 언론사만":
        raw = [a for a in raw if is_major_korean(a)]
    elif source_filter == "국내 전체":
        raw = [a for a in raw if is_korean_article(a["link"], a["title"], a["source"])]

    if not raw:
        st.warning("해당 조건의 기사가 없습니다. 출처 필터나 기간을 조정해보세요.")
        st.stop()

    # 가중치 재적용
    for a in raw:
        base = a["rel"] * weight_rel + a["rec"] * weight_rec + a["tq"] * weight_tq
        base = base * 0.80 + a["purity"] * 0.20
        multiplier = 1.0 if a["art_type"] == "기사" else 0.70
        a["score"] = round(base * multiplier * a["domain"], 4)

    # 유사 기사 중 원본만 남기기
    articles = deduplicate_by_originality(raw)

    # 기간 필터
    time_map = {
        "오늘 (KST 00:00~)": today_start_utc(),
        "1시간 이내":  datetime.now(timezone.utc) - timedelta(hours=1),
        "6시간 이내":  datetime.now(timezone.utc) - timedelta(hours=6),
        "24시간 이내": datetime.now(timezone.utc) - timedelta(hours=24),
        "3일 이내":    datetime.now(timezone.utc) - timedelta(days=3),
        "7일 이내":    datetime.now(timezone.utc) - timedelta(days=7),
        "전체": None,
    }
    since = time_map[time_filter]
    if since:
        articles = [a for a in articles if a["date"] and a["date"] >= since]

    # 유형 필터
    if type_filter:
        articles = [a for a in articles if a["art_type"] in type_filter]

    # 정렬 (본문 분석 전 1차 정렬)
    if sort_by == "최신순":
        articles.sort(key=lambda x: x["date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    elif sort_by == "관련도":
        articles.sort(key=lambda x: x["rel"], reverse=True)
    else:
        articles.sort(key=lambda x: x["score"], reverse=True)

    # 본문 분석 — 항상 상위 10개 적용 후 재정렬
    for a in articles:
        a.setdefault("content_q", 0.5)
        a.setdefault("content_text", "")

    with st.spinner("상위 기사 본문 분석 중..."):
        enrich_with_content(articles, keyword=keyword, top_n=10)

    # 본문까지 분석했는데도 관련도가 0.30 미만이면 제거
    articles = [a for a in articles
                if a.get("final_rel", a["rel"]) >= 0.30]

    if sort_by == "종합 점수":
        articles.sort(key=lambda x: x["score"], reverse=True)

    # 각도 태깅 (커버리지·조합추천 공통)
    tag_angles(articles)

    # 리서치 분석 (max_results 자르기 전 전체 대상)
    top_kw        = extract_top_keywords(articles, keyword)
    covered, missing = coverage_analysis(articles)
    search_suggestions = suggest_searches(top_kw, keyword)
    combo_candidates   = find_combo_candidates(articles)

    articles = articles[:max_results]

    # Metrics
    pr_cnt      = sum(1 for a in articles if a["art_type"] == "보도자료")
    article_cnt = sum(1 for a in articles if a["art_type"] == "기사")

    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("수집 기사", f"{len(raw):,}건")
    m2.metric("원본 추출 후", f"{len(deduplicate_by_originality(raw)):,}건")
    m3.metric("✏️ 기사", f"{article_cnt}건")
    m4.metric("📢 보도자료", f"{pr_cnt}건")
    st.markdown("---")

    # 2-column layout: 기사 목록 | 리서치 패널
    col_main, col_side = st.columns([3, 1])

    with col_main:
        if not articles:
            st.info("해당 조건에 기사가 없습니다. 기간 필터를 넓혀보세요.")
        for rank, art in enumerate(articles, 1):
            score_pct = int(art["score"] * 100)
            rel_pct   = int(art.get("final_rel", art["rel"]) * 100)
            rec_label = time_ago(art["date"])
            new_badge = '<span class="badge badge-new">NEW</span>' if is_recent(art["date"]) else ""

            # 본문 품질 뱃지 (심층 분석 시에만)
            cq = art.get("content_q", 0.5)
            if art.get("content_text"):   # 본문을 실제로 가져온 경우만 표시
                cq_pct = int(cq * 100)
                cq_color = "#166534" if cq >= 0.7 else "#92400e" if cq >= 0.5 else "#991b1b"
                cq_bg    = "#dcfce7"  if cq >= 0.7 else "#fff7ed"  if cq >= 0.5 else "#fee2e2"
                cq_badge = (f'<span class="badge" style="background:{cq_bg};color:{cq_color};">'
                            f'본문 {cq_pct}%</span>')
            else:
                cq_badge = ""

            type_badge = ('<span class="badge badge-press">📢 보도자료</span>'
                          if art["art_type"] == "보도자료"
                          else '<span class="badge badge-article">✏️ 기사</span>')

            st.markdown(f"""
<div class="news-card">
  <div>
    <span class="news-rank">#{rank}</span>&nbsp;
    <span style="color:#6b7280;font-size:0.82rem;">{art['source']}</span>
  </div>
  <div style="margin-top:0.5rem;">
    <a class="news-title" href="{art['link']}" target="_blank">{art['title']}</a>
  </div>
  <div class="news-meta">🕐 {rec_label}</div>
  <div class="score-bar-wrap">
    <div class="score-bar" style="width:{score_pct}%"></div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── 리서치 패널 ────────────────────────────────────────────────────────────
    with col_side:

        if top_kw:
            st.markdown('<div class="combo-header">🏷️ 핵심 키워드</div>', unsafe_allow_html=True)
            max_count = top_kw[0][1] if top_kw else 1
            kw_html = ""
            for w, c in top_kw:
                ratio  = c / max_count
                size   = 0.72 + 0.28 * ratio
                blues  = ["#bfdbfe", "#93c5fd", "#60a5fa", "#3b82f6", "#2563eb"]
                color  = blues[min(int(ratio * 4), 4)]
                kw_html += (
                    f'<span style="display:inline-block;margin:2px 3px;padding:2px 9px;'
                    f'border-radius:999px;background:#eff6ff;border:1px solid {color};'
                    f'color:{color};font-size:{size:.2f}rem;font-weight:700;">'
                    f'{w} <span style="color:#9ca3af;font-size:0.65rem;">{c}</span></span>'
                )
            st.markdown(f'<div style="line-height:2.1;">{kw_html}</div>', unsafe_allow_html=True)

else:
    st.markdown("""
<div style="text-align:center; padding: 3rem 1rem; color: #6b7280;">
    <div style="font-size:3rem;">🔍</div>
    <div style="font-size:1.1rem; margin-top:1rem; color:#111827; font-weight:600;">위 검색창에 키워드를 입력하고 검색하세요</div>
    <div style="font-size:0.9rem; margin-top:0.5rem; color:#6b7280;">예: 인공지능 &nbsp;·&nbsp; 삼성전자 &nbsp;·&nbsp; 부동산 &nbsp;·&nbsp; 코스피</div>
</div>
""", unsafe_allow_html=True)
