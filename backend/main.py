from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import yfinance as yf
import re
import httpx
import psycopg2
import os
import asyncio
from datetime import datetime
import tweepy

app = FastAPI(title="배당 스크리너 API", version="4.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:QCfWStztJzsQBAxGkolDhPhEAZkSNrrv@crossover.proxy.rlwy.net:36008/railway"
)

X_API_KEY             = os.environ.get("zWfljqzajqAbTknAIr2dFrDdt")
X_API_SECRET          = os.environ.get("FeK1FvAA5rvpQb6wkv90eHlQQ5mizSDxl5mISC1C3PlrArO7j0")
X_ACCESS_TOKEN        = os.environ.get("2038127304191135744-cP2ts1HIjodWgbTHgrRu6nPJsxMntD")
X_ACCESS_TOKEN_SECRET = os.environ.get("DSBITJ01MkcWeYpmas6qgJYyjJW3ooNZjT8tscCISmNZx")

KR_NAME_MAP: dict = {}

def load_kr_names():
    global KR_NAME_MAP
    try:
        import FinanceDataReader as fdr
        import pandas as pd
        kospi  = fdr.StockListing('KOSPI')
        kosdaq = fdr.StockListing('KOSDAQ')
        combined = pd.concat([kospi, kosdaq])
        KR_NAME_MAP = dict(zip(combined['Code'], combined['Name']))
        print(f"✅ 한국어 종목명 {len(KR_NAME_MAP)}개 로드 완료")
    except Exception as e:
        print(f"한국어 종목명 로드 실패: {e}")

DOUBLE_LISTED = {
    "005930", "005935",
    "005380", "005385", "005387",
    "000270", "000272",
    "051910", "051915",
    "003550", "034730",
    "000660", "017670", "096770",
    "003490",
}

BUYBACK_EXCELLENT = {
    "005380", "005385", "005387",
    "000270", "000272",
    "005930", "005935",
    "086790", "105560", "055550",
}

DIVIDEND_GROWTH_10Y = set()

DIVIDEND_GROWTH_5Y = {
    "086790", "105560", "055550",
}

DIVIDEND_STABLE_3Y = {
    "005930", "005935",
    "005380", "005385", "005387",
    "000270", "000272",
    "086790", "105560", "055550", "316140",
    "015760",
}

BUYBACK_RATIO = {
    "000270": 2.5, "000272": 2.5,
    "005380": 1.8, "005385": 1.8, "005387": 1.8,
    "005930": 1.2, "005935": 1.2,
    "086790": 1.5, "105560": 1.5, "055550": 1.0,
}

TREASURY_RATIO = {
    "005930": 8.0, "005935": 8.0,
    "005380": 3.0, "005385": 3.0, "005387": 3.0,
    "000270": 1.5, "000272": 1.5,
    "086790": 1.0, "105560": 1.0, "055550": 1.0,
}


def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rankings (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL UNIQUE,
                name VARCHAR(100),
                name_kr VARCHAR(100),
                score INTEGER,
                grade VARCHAR(5),
                grade_label VARCHAR(100),
                per FLOAT,
                pbr FLOAT,
                roe FLOAT,
                dividend_yield FLOAT,
                sector VARCHAR(100),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            cur.execute("ALTER TABLE rankings ADD COLUMN IF NOT EXISTS name_kr VARCHAR(100)")
        except: pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scan_log (
                id SERIAL PRIMARY KEY,
                scanned_at TIMESTAMP DEFAULT NOW(),
                total_scanned INTEGER,
                total_qualified INTEGER
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ DB 초기화 완료")
    except Exception as e:
        print(f"DB 초기화 실패: {e}")


def detect_quarterly_dividend(stock) -> bool:
    try:
        dividends = stock.dividends
        if dividends is None or len(dividends) == 0:
            return False
        recent = dividends.last("2Y")
        if len(recent) == 0:
            recent = dividends.last("3Y")
        if len(recent) == 0:
            return False
        return len(recent) >= 5
    except:
        return False


async def fetch_naver_metrics(ticker_code: str) -> dict:
    result = {
        "per": None, "pbr": None, "eps": None,
        "bps": None, "dividend_yield": None, "roe": None
    }
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://finance.naver.com",
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
            html = res.text

            m = re.search(r'<em id="_per">([\d,\.]+)</em>', html)
            if m:
                try: result["per"] = float(m.group(1).replace(",", ""))
                except: pass

            m = re.search(r'<em id="_pbr">([\d,\.]+)</em>', html)
            if m:
                try: result["pbr"] = float(m.group(1).replace(",", ""))
                except: pass

            m = re.search(r'<em id="_eps">([\d,\-]+)</em>', html)
            if m:
                try: result["eps"] = float(m.group(1).replace(",", ""))
                except: pass

            m = re.search(r'<em id="_bps">([\d,]+)</em>', html)
            if m:
                try: result["bps"] = float(m.group(1).replace(",", ""))
                except: pass

            m = re.search(r'<em id="_dvr">([\d,\.]+)</em>', html)
            if m:
                try: result["dividend_yield"] = float(m.group(1).replace(",", ""))
                except: pass

            for roe_pat in [
                r'ROE\(순이익/자본\).*?<td[^>]*>\s*([\d,\.]+)\s*</td>',
                r'자기자본이익률.*?<td[^>]*>\s*([\d,\.]+)',
                r'ROE.*?<td[^>]*>\s*([\d,\.]+)\s*</td>',
            ]:
                roe_m = re.search(roe_pat, html, re.DOTALL)
                if roe_m:
                    try:
                        result["roe"] = float(roe_m.group(1).replace(",", ""))
                        break
                    except: pass

    except Exception as e:
        print(f"네이버 파싱 실패 ({ticker_code}): {e}")
    return result


def calc_category_a(info: dict, hist_financials: dict, naver: dict, ticker_code: str) -> dict:
    scores = {}
    details = {}

    per = naver.get("per") or info.get("trailingPE") or info.get("forwardPE")
    if per and per > 0:
        if per < 5:       scores["per"] = 15
        elif per < 8:     scores["per"] = 10
        elif per < 10:    scores["per"] = 5
        else:             scores["per"] = 0
        details["per"] = round(per, 2)
        if per < 8:       details["per_status"] = "저평가"
        elif per < 15:    details["per_status"] = "적정"
        else:             details["per_status"] = "고평가"
    else:
        scores["per"] = 0
        details["per"] = None
        details["per_status"] = None

    roe_raw = info.get("returnOnEquity")
    roe_yf  = round(roe_raw * 100, 2) if roe_raw else None
    roe_nav = naver.get("roe")
    roe_pct = roe_nav or roe_yf
    if roe_pct and roe_pct > 100:
        roe_pct = roe_yf if roe_yf and roe_yf <= 100 else None

    if roe_pct and roe_pct > 0:
        if roe_pct >= 15:   scores["roe"] = 5
        elif roe_pct >= 10: scores["roe"] = 3
        elif roe_pct >= 5:  scores["roe"] = 1
        else:               scores["roe"] = 0
        details["roe"] = round(roe_pct, 2)
        if roe_pct >= 15:   details["roe_status"] = "우수"
        elif roe_pct >= 10: details["roe_status"] = "양호"
        elif roe_pct >= 5:  details["roe_status"] = "보통"
        else:               details["roe_status"] = "저조"
    else:
        scores["roe"] = 0
        details["roe"] = None
        details["roe_status"] = None

    pbr = naver.get("pbr") or info.get("priceToBook")
    if not pbr:
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0
        bvps  = info.get("bookValue") or naver.get("bps") or 0
        if price and bvps and bvps > 0:
            pbr = round(price / bvps, 2)
    if pbr and pbr > 0:
        if pbr < 0.3:     scores["pbr"] = 5
        elif pbr < 0.6:   scores["pbr"] = 4
        elif pbr < 1.0:   scores["pbr"] = 3
        else:             scores["pbr"] = 0
        details["pbr"] = round(pbr, 2)
        if pbr < 1.0:     details["pbr_status"] = "저평가"
        elif pbr < 1.5:   details["pbr_status"] = "적정"
        else:             details["pbr_status"] = "고평가"
    else:
        scores["pbr"]  = 0
        details["pbr"] = None
        details["pbr_status"] = None

    op_margins = hist_financials.get("operating_margins", [])
    if len(op_margins) >= 3:
        all_positive = all(m > 0 for m in op_margins[-4:] if m is not None)
        growing = len(op_margins) >= 2 and op_margins[-1] >= op_margins[0]
        if all_positive and growing:
            scores["stability"] = 5
            details["stability"] = "흑자 지속 + 성장"
        elif all_positive:
            scores["stability"] = 3
            details["stability"] = "흑자 지속"
        else:
            scores["stability"] = 0
            details["stability"] = "적자 이력 있음"
    else:
        scores["stability"] = 3
        details["stability"] = "데이터 부족"

    if ticker_code in DOUBLE_LISTED:
        scores["listing"] = 0
        details["listing"] = "중복상장"
    else:
        scores["listing"] = 5
        details["listing"] = "단독 상장 ✅"

    return {"total": sum(scores.values()), "max": 35, "scores": scores, "details": details}


def calc_category_b(info: dict, naver: dict, ticker_code: str, is_quarterly: bool = False) -> dict:
    scores = {}
    details = {}

    price    = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose") or 0
    div_rate = info.get("dividendRate", 0) or 0
    dy_calc  = round((div_rate / price) * 100, 2) if price and div_rate else None
    dy_nav   = naver.get("dividend_yield")
    dy_raw   = info.get("dividendYield")
    dy_yf    = (dy_raw if dy_raw and dy_raw > 1 else dy_raw * 100) if dy_raw else None
    dy_pct   = dy_calc or dy_yf or dy_nav

    if dy_pct and dy_pct > 0:
        if dy_pct > 7:    scores["dividend_yield"] = 10
        elif dy_pct > 5:  scores["dividend_yield"] = 7
        elif dy_pct > 3:  scores["dividend_yield"] = 5
        else:             scores["dividend_yield"] = 2
        details["dividend_yield"] = round(dy_pct, 2)
        if dy_pct > 5:    details["dy_status"] = "고배당"
        elif dy_pct > 3:  details["dy_status"] = "양호"
        else:             details["dy_status"] = "낮음"
    else:
        scores["dividend_yield"] = 0
        details["dividend_yield"] = 0.0
        details["dy_status"] = None

    if is_quarterly:
        scores["dividend_freq"] = 5
        details["dividend_freq"] = "분기 배당 ✅"
    else:
        scores["dividend_freq"] = 0
        details["dividend_freq"] = "연 1회 배당"

    if ticker_code in DIVIDEND_GROWTH_10Y:
        scores["dividend_stability"] = 5
        details["dividend_stability"] = "10년+ 연속 인상 ✅"
    elif ticker_code in DIVIDEND_GROWTH_5Y:
        scores["dividend_stability"] = 4
        details["dividend_stability"] = "5년+ 연속 인상 ✅"
    elif ticker_code in DIVIDEND_STABLE_3Y:
        scores["dividend_stability"] = 3
        details["dividend_stability"] = "3년+ 배당 유지"
    else:
        payout = info.get("payoutRatio", 0) or 0
        if div_rate > 0 and 0 < payout < 0.8:
            scores["dividend_stability"] = 1
            details["dividend_stability"] = "배당 지속 중"
        else:
            scores["dividend_stability"] = 0
            details["dividend_stability"] = "배당 이력 불명확"

    if ticker_code in BUYBACK_EXCELLENT:
        scores["buyback"] = 7
        details["buyback"] = "정기 자사주 소각 ✅"
    else:
        scores["buyback"] = 0
        details["buyback"] = "소각 미실시"

    ratio = BUYBACK_RATIO.get(ticker_code, 0)
    if ratio > 2.0:
        scores["buyback_ratio"] = 8
        details["buyback_ratio"] = f"연간 소각 {ratio}% (매우 강함)"
    elif ratio > 1.5:
        scores["buyback_ratio"] = 5
        details["buyback_ratio"] = f"연간 소각 {ratio}% (강함)"
    elif ratio > 0.5:
        scores["buyback_ratio"] = 3
        details["buyback_ratio"] = f"연간 소각 {ratio}% (보통)"
    else:
        scores["buyback_ratio"] = 0
        details["buyback_ratio"] = "소각 비율 미미"

    treasury = TREASURY_RATIO.get(ticker_code, -1)
    if treasury == -1:
        scores["treasury"] = 5
        details["treasury"] = "자사주 없음 ✅"
    elif treasury < 2.0:
        scores["treasury"] = 4
        details["treasury"] = f"자사주 {treasury}% (양호)"
    elif treasury < 5.0:
        scores["treasury"] = 2
        details["treasury"] = f"자사주 {treasury}% (보통)"
    else:
        scores["treasury"] = 0
        details["treasury"] = f"자사주 {treasury}% (과다)"

    return {"total": sum(scores.values()), "max": 40, "scores": scores, "details": details}


def calc_category_c(info: dict, ticker_code: str, hist_financials: dict) -> dict:
    scores = {}
    details = {}

    op_margins = hist_financials.get("operating_margins", [])
    op_margin  = op_margins[-1] * 100 if op_margins else None
    if op_margin is None:
        raw = info.get("operatingMargins")
        if raw: op_margin = raw * 100

    if op_margin is not None:
        if op_margin >= 15:   scores["op_margin"] = 8
        elif op_margin >= 10: scores["op_margin"] = 6
        elif op_margin >= 5:  scores["op_margin"] = 3
        else:                 scores["op_margin"] = 0
        details["op_margin"] = round(op_margin, 2)
    else:
        scores["op_margin"] = 0
        details["op_margin"] = None

    rev_growth = hist_financials.get("revenue_growth")
    if rev_growth is None:
        raw = info.get("revenueGrowth")
        if raw: rev_growth = raw * 100

    if rev_growth is not None:
        if rev_growth >= 10:   scores["rev_growth"] = 7
        elif rev_growth >= 5:  scores["rev_growth"] = 5
        elif rev_growth >= 0:  scores["rev_growth"] = 3
        else:                  scores["rev_growth"] = 0
        details["rev_growth"] = round(rev_growth, 2)
    else:
        scores["rev_growth"] = 3
        details["rev_growth"] = None

    sector = info.get("sector", "")
    current_ratio = info.get("currentRatio")
    if sector in ["Financial Services", "금융"]:
        scores["current_ratio"] = 5
        details["current_ratio"] = None
        details["current_ratio_status"] = "금융업 예외"
    elif current_ratio is not None:
        if current_ratio >= 2.0:   scores["current_ratio"] = 5
        elif current_ratio >= 1.5: scores["current_ratio"] = 3
        elif current_ratio >= 1.0: scores["current_ratio"] = 1
        else:                      scores["current_ratio"] = 0
        details["current_ratio"] = round(current_ratio, 2)
        details["current_ratio_status"] = None
    else:
        scores["current_ratio"] = 2
        details["current_ratio"] = None
        details["current_ratio_status"] = None

    market_cap = info.get("marketCap", 0) or 0
    if market_cap > 10_000_000_000_000:
        scores["moat"] = 5
        details["moat"] = "대형주 (강한 해자)"
    elif market_cap > 1_000_000_000_000:
        scores["moat"] = 3
        details["moat"] = "중형주 (보통 해자)"
    else:
        scores["moat"] = 1
        details["moat"] = "소형주 (약한 해자)"

    return {"total": sum(scores.values()), "max": 25, "scores": scores, "details": details}


def get_grade(score: int) -> dict:
    if score >= 90: return {"grade": "S", "label": "최고의 매수 기회 · 강력 매수",    "color": "#a78bfa"}
    if score >= 80: return {"grade": "A", "label": "장기투자 강력 추천 · 적극 매수",  "color": "#10b981"}
    if score >= 70: return {"grade": "B", "label": "한국 시장 우량주 · 매수 고려",    "color": "#3b82f6"}
    if score >= 50: return {"grade": "C", "label": "보유 유지 · 추가 매수 신중",      "color": "#f59e0b"}
    return             {"grade": "D", "label": "장기투자 비추천",                  "color": "#ef4444"}


async def post_to_x():
    api_key              = os.environ.get("X_API_KEY")
    api_secret           = os.environ.get("X_API_SECRET")
    access_token         = os.environ.get("X_ACCESS_TOKEN")
    access_token_secret  = os.environ.get("X_ACCESS_TOKEN_SECRET")

    print(f"🔑 X_API_KEY: {api_key[:5] if api_key else 'None'}")
    print(f"🔑 X_API_SECRET: {api_secret[:5] if api_secret else 'None'}")
    print(f"🔑 X_ACCESS_TOKEN: {access_token[:5] if access_token else 'None'}")
    print(f"🔑 X_ACCESS_TOKEN_SECRET: {access_token_secret[:5] if access_token_secret else 'None'}")

    try:
        if not all([api_key, api_secret, access_token, access_token_secret]):
            print("⚠️ X API 키 누락 — 포스팅 스킵")
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, name, score, grade, per, dividend_yield
            FROM rankings
            ORDER BY score DESC
            LIMIT 3
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            print("⚠️ 포스팅할 랭킹 데이터 없음")
            return

        today = datetime.now().strftime("%Y.%m.%d")
        medals = ["🥇", "🥈", "🥉"]

        lines = [f"📊 오늘의 배당 우량주 ({today})\n"]
        for i, row in enumerate(rows):
            ticker, name, score, grade, per, dy = row
            per_str = f"PER {per:.1f}" if per else "PER -"
            dy_str  = f"배당 {dy:.1f}%" if dy else "배당 -"
            lines.append(f"{medals[i]} {name} ({ticker}) — {score}점 {grade}등급")
            lines.append(f"   {per_str} | {dy_str}\n")

        lines.append("👉 전체 랭킹: 배당스크리너.com")
        lines.append("#배당주 #가치투자 #배당스크리너 #한국주식")

        tweet_text = "\n".join(lines)

        client = tweepy.Client(
            bearer_token=os.environ.get("X_BEARER_TOKEN"),
            consumer_key=api_key
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        client.create_tweet(text=tweet_text)
        print(f"✅ X 포스팅 완료: {today}")

    except Exception as e:
        print(f"X 포스팅 실패: {e}")


async def analyze_ticker(ticker_code: str) -> dict | None:
    try:
        naver = await fetch_naver_metrics(ticker_code)
        stock = None
        info  = None
        for suffix in [".KS", ".KQ"]:
            s = yf.Ticker(ticker_code.strip().zfill(6) + suffix)
            i = s.info
            p = i.get("currentPrice") or i.get("regularMarketPrice") or i.get("previousClose")
            if p:
                stock, info = s, i
                break
        if not stock:
            return None

        op_margins = []
        revenues   = []
        try:
            income = stock.income_stmt
            if income is not None and not income.empty:
                for col in income.columns[:4]:
                    try:
                        op_inc = income.loc["Operating Income", col]
                        rev    = income.loc["Total Revenue", col]
                        if rev and rev != 0:
                            op_margins.append(round(float(op_inc / rev), 4))
                            revenues.append(float(rev))
                    except: pass
        except: pass

        rev_growth = None
        if len(revenues) >= 2:
            rev_growth = round(((revenues[0] - revenues[-1]) / abs(revenues[-1])) * 100, 2)

        is_quarterly = detect_quarterly_dividend(stock)

        hist = {
            "operating_margins": op_margins,
            "revenue_growth":    rev_growth,
        }

        cat_a = calc_category_a(info, hist, naver, ticker_code)
        cat_b = calc_category_b(info, naver, ticker_code, is_quarterly)
        cat_c = calc_category_c(info, ticker_code, hist)
        total = min(100, cat_a["total"] + cat_b["total"] + cat_c["total"])
        grade = get_grade(total)

        name_kr = KR_NAME_MAP.get(ticker_code, "")
        name_en = info.get("longName") or info.get("shortName") or ticker_code

        return {
            "ticker":         ticker_code,
            "name":           name_kr or name_en,
            "name_kr":        name_kr,
            "score":          total,
            "grade":          grade["grade"],
            "grade_label":    grade["label"],
            "per":            cat_a["details"].get("per"),
            "pbr":            cat_a["details"].get("pbr"),
            "roe":            cat_a["details"].get("roe"),
            "dividend_yield": cat_b["details"].get("dividend_yield"),
            "sector":         info.get("sector", "N/A"),
        }
    except Exception as e:
        print(f"분석 실패 ({ticker_code}): {e}")
        return None


async def run_full_scan(start: int = 0, end: int = 100):
    print(f"🔍 스캔 시작 ({start}~{end}): {datetime.now()}")
    try:
        import FinanceDataReader as fdr
        kospi = fdr.StockListing('KOSPI')
        tickers = kospi['Code'].tolist()
    except Exception as e:
        print(f"종목 리스트 수집 실패: {e}")
        tickers = [
            "005930", "000660", "005380", "005387", "000270",
            "086790", "105560", "055550", "316140", "017670",
            "034730", "003550", "015760", "032830", "028260",
        ]

    target = tickers[start:end]
    qualified = []
    total_scanned = 0

    for ticker in target:
        result = await analyze_ticker(ticker)
        total_scanned += 1
        if result and result["score"] >= 60:
            qualified.append(result)
            print(f"✅ {ticker} {result['name']} — {result['score']}점 ({result['grade']}등급)")

    try:
        conn = get_db()
        cur = conn.cursor()
        for r in qualified:
            cur.execute("""
                INSERT INTO rankings
                (ticker, name, name_kr, score, grade, grade_label, per, pbr, roe, dividend_yield, sector, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    name=EXCLUDED.name, name_kr=EXCLUDED.name_kr,
                    score=EXCLUDED.score, grade=EXCLUDED.grade,
                    grade_label=EXCLUDED.grade_label, per=EXCLUDED.per, pbr=EXCLUDED.pbr,
                    roe=EXCLUDED.roe, dividend_yield=EXCLUDED.dividend_yield,
                    sector=EXCLUDED.sector, updated_at=NOW()
            """, (
                r["ticker"], r["name"], r.get("name_kr", ""), r["score"], r["grade"],
                r["grade_label"], r["per"], r["pbr"], r["roe"],
                r["dividend_yield"], r["sector"]
            ))
        cur.execute("""
            INSERT INTO scan_log (total_scanned, total_qualified)
            VALUES (%s, %s)
        """, (total_scanned, len(qualified)))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ 스캔 완료: {total_scanned}개 중 {len(qualified)}개 저장")
    except Exception as e:
        print(f"DB 저장 실패: {e}")


@app.on_event("startup")
async def startup():
    init_db()
    load_kr_names()
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    # 매일 오전 7시 전체 스캔
    scheduler.add_job(run_full_scan, "cron", hour=7, minute=0, kwargs={"start": 0, "end": 9999})
    # 매일 오전 9시 X 자동 포스팅 (스캔 완료 후)
    scheduler.add_job(post_to_x, "cron", hour=9, minute=0)
    scheduler.start()
    print("✅ 스케줄러 시작 — 매일 오전 7시 스캔, 9시 X 포스팅")


@app.get("/")
def root():
    return {"message": "배당 스크리너 API v4.2 🚀"}


@app.get("/search")
async def search(q: str):
    if not q or len(q) < 1:
        return {"results": []}
    q = q.strip()
    results = []
    for code, name in KR_NAME_MAP.items():
        if q in name or q in code:
            results.append({"ticker": code, "name": name})
        if len(results) >= 10:
            break
    return {"results": results}


@app.get("/reset-rankings")
async def reset_rankings():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM rankings")
        cur.execute("DELETE FROM scan_log")
        conn.commit()
        cur.close()
        conn.close()
        return {"message": "랭킹 데이터 초기화 완료 ✅"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scan-now")
async def trigger_scan(start: int = 0, end: int = 100):
    asyncio.create_task(run_full_scan(start, end))
    return {"message": f"스캔 시작: {start}~{end}번째 종목"}


@app.get("/scan-all")
async def scan_all():
    async def run_sequential():
        try:
            import FinanceDataReader as fdr
            kospi = fdr.StockListing('KOSPI')
            total = len(kospi['Code'].tolist())
        except:
            total = 1000
        print(f"🚀 전체 순차 스캔 시작! 총 {total}개 종목")
        for start in range(0, total, 100):
            end = min(start + 100, total)
            await run_full_scan(start, end)
            print(f"⏳ {start}~{end} 완료. 30초 대기...")
            await asyncio.sleep(30)
        print("🎉 전체 스캔 완료!")
    asyncio.create_task(run_sequential())
    return {"message": "전체 순차 스캔 시작! 화면 꺼도 됩니다 🚀"}


@app.get("/post-now")
async def post_now():
    """X 포스팅 즉시 테스트"""
    await post_to_x()
    return {"message": "X 포스팅 완료 ✅"}


@app.get("/ranking")
async def get_ranking():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, name, name_kr, score, grade, grade_label,
                   per, pbr, roe, dividend_yield, sector, updated_at
            FROM rankings
            ORDER BY score DESC
        """)
        rows = cur.fetchall()
        cur.execute("SELECT scanned_at, total_scanned, total_qualified FROM scan_log ORDER BY scanned_at DESC LIMIT 1")
        log = cur.fetchone()
        cur.close()
        conn.close()
        return {
            "rankings": [
                {
                    "ticker":         r[0],
                    "name":           r[2] or r[1],
                    "name_en":        r[1],
                    "score":          r[3],
                    "grade":          r[4],
                    "grade_label":    r[5],
                    "per":            r[6],
                    "pbr":            r[7],
                    "roe":            r[8] if r[8] and r[8] < 100 else None,
                    "dividend_yield": r[9],
                    "sector":         r[10],
                    "updated_at":     r[11].strftime("%Y-%m-%d %H:%M") if r[11] else None,
                }
                for r in rows
            ],
            "last_scan": {
                "scanned_at":      log[0].strftime("%Y-%m-%d %H:%M") if log else None,
                "total_scanned":   log[1] if log else 0,
                "total_qualified": log[2] if log else 0,
            } if log else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"랭킹 조회 실패: {str(e)}")


@app.get("/debug/{ticker_code}")
async def debug(ticker_code: str):
    naver = await fetch_naver_metrics(ticker_code)
    for suffix in [".KS", ".KQ"]:
        stock = yf.Ticker(ticker_code.strip().zfill(6) + suffix)
        info  = stock.info
        p = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if p:
            price    = p
            div_rate = info.get("dividendRate", 0) or 0
            dy_calc  = round((div_rate / price) * 100, 2) if price and div_rate else None
            is_quarterly = detect_quarterly_dividend(stock)
            return {
                "yfinance": {
                    "priceToBook":      info.get("priceToBook"),
                    "trailingPE":       info.get("trailingPE"),
                    "returnOnEquity":   info.get("returnOnEquity"),
                    "debtToEquity":     info.get("debtToEquity"),
                    "dividendYield":    info.get("dividendYield"),
                    "dividendRate":     div_rate,
                    "dy_calc":          dy_calc,
                    "operatingMargins": info.get("operatingMargins"),
                    "revenueGrowth":    info.get("revenueGrowth"),
                    "currentRatio":     info.get("currentRatio"),
                    "sector":           info.get("sector"),
                },
                "naver":              naver,
                "name_kr":            KR_NAME_MAP.get(ticker_code, "없음"),
                "is_quarterly":       is_quarterly,
                "is_double_listed":   ticker_code in DOUBLE_LISTED,
                "has_buyback_policy": ticker_code in BUYBACK_EXCELLENT,
                "buyback_ratio":      BUYBACK_RATIO.get(ticker_code, 0),
                "treasury_ratio":     TREASURY_RATIO.get(ticker_code, -1),
            }
    return {"error": "종목을 찾을 수 없습니다"}


@app.get("/analyze/{ticker_code}")
async def analyze(ticker_code: str):
    if not re.match(r"^\d{6}$", ticker_code.strip()):
        raise HTTPException(status_code=400, detail="6자리 종목코드를 입력하세요")
    try:
        naver = await fetch_naver_metrics(ticker_code)
        stock = None
        info  = None
        price = None
        for suffix in [".KS", ".KQ"]:
            s = yf.Ticker(ticker_code.strip().zfill(6) + suffix)
            i = s.info
            p = i.get("currentPrice") or i.get("regularMarketPrice") or i.get("previousClose")
            if p:
                stock, info, price = s, i, p
                break
        if not stock:
            raise HTTPException(status_code=404, detail=f"종목을 찾을 수 없습니다: {ticker_code}")

        op_margins = []
        revenues   = []
        try:
            income = stock.income_stmt
            if income is not None and not income.empty:
                for col in income.columns[:4]:
                    try:
                        op_inc = income.loc["Operating Income", col]
                        rev    = income.loc["Total Revenue", col]
                        if rev and rev != 0:
                            op_margins.append(round(float(op_inc / rev), 4))
                            revenues.append(float(rev))
                    except: pass
        except: pass

        rev_growth = None
        if len(revenues) >= 2:
            rev_growth = round(((revenues[0] - revenues[-1]) / abs(revenues[-1])) * 100, 2)

        is_quarterly = detect_quarterly_dividend(stock)

        hist = {
            "operating_margins": op_margins,
            "revenue_growth":    rev_growth,
        }

        cat_a = calc_category_a(info, hist, naver, ticker_code)
        cat_b = calc_category_b(info, naver, ticker_code, is_quarterly)
        cat_c = calc_category_c(info, ticker_code, hist)
        total = min(100, cat_a["total"] + cat_b["total"] + cat_c["total"])

        name_kr = KR_NAME_MAP.get(ticker_code, "")
        name_en = info.get("longName") or info.get("shortName") or ticker_code

        return {
            "ticker":      ticker_code,
            "name":        name_kr or name_en,
            "name_en":     name_en,
            "price":       price,
            "currency":    info.get("currency", "KRW"),
            "market_cap":  info.get("marketCap"),
            "sector":      info.get("sector", "N/A"),
            "total_score": total,
            "grade":       get_grade(total),
            "categories":  {"a": cat_a, "b": cat_b, "c": cat_c},
            "key_metrics": {
                "per":            cat_a["details"].get("per"),
                "per_status":     cat_a["details"].get("per_status"),
                "pbr":            cat_a["details"].get("pbr"),
                "pbr_status":     cat_a["details"].get("pbr_status"),
                "roe":            cat_a["details"].get("roe"),
                "roe_status":     cat_a["details"].get("roe_status"),
                "dividend_yield": cat_b["details"].get("dividend_yield"),
                "dy_status":      cat_b["details"].get("dy_status"),
                "op_margin":      cat_c["details"].get("op_margin"),
                "rev_growth":     cat_c["details"].get("rev_growth"),
                "current_ratio":  cat_c["details"].get("current_ratio"),
                "buyback_policy": cat_b["details"].get("buyback"),
                "listing":        cat_a["details"].get("listing"),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 수집 중 오류: {str(e)}")


@app.get("/dividend-simulation")
async def dividend_simulation(
    initial: float = 10_000_000,
    annual_yield: float = 5.0,
    years: int = 5,
    reinvest: bool = True
):
    results = []
    current = initial
    rate = annual_yield / 100
    for y in range(1, years + 1):
        if reinvest:
            dividend = current * rate
            current += dividend
        else:
            dividend = initial * rate
        results.append({
            "year":                y,
            "dividend":            round(dividend),
            "total_value":         round(current if reinvest else initial + dividend * y),
            "cumulative_dividend": round(initial * ((1 + rate) ** y - 1) if reinvest else dividend * y)
        })
    return {
        "initial":               initial,
        "annual_yield":          annual_yield,
        "years":                 years,
        "reinvest":              reinvest,
        "final_value":           results[-1]["total_value"],
        "total_dividend_earned": results[-1]["cumulative_dividend"],
        "yearly":                results
    }
