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

app = FastAPI(title="가치투자 스크리닝 API", version="3.0.0")

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

QUARTERLY_DIVIDEND = {
    "005930", "005935",
    "086790", "105560", "055550", "316140",
    "000660",
}

DIVIDEND_STABLE = {
    "005930", "005935",
    "005380", "005385", "005387",
    "000270", "000272",
    "086790", "105560", "055550", "316140",
    "015760",
}

DIVIDEND_GROWTH_10Y = set()

DIVIDEND_GROWTH_5Y = {
    "086790", "105560", "055550",
}

BUYBACK_RATIO = {
    "000270": 2.5,
    "000272": 2.5,
    "005380": 1.8,
    "005385": 1.8,
    "005387": 1.8,
    "005930": 1.2,
    "005935": 1.2,
    "086790": 1.5,
    "105560": 1.5,
    "055550": 1.0,
}

TREASURY_RATIO = {
    "005930": 8.0,
    "005935": 8.0,
    "005380": 3.0,
    "005385": 3.0,
    "005387": 3.0,
    "000270": 1.5,
    "000272": 1.5,
    "086790": 1.0,
    "105560": 1.0,
    "055550": 1.0,
}

GLOBAL_BRAND = {
    "005930", "005935",
    "005380", "005385", "005387",
    "000270", "000272",
    "051910", "051915",
    "068270",
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

    # PER (18점)
    per = naver.get("per") or info.get("trailingPE") or info.get("forwardPE")
    if per and per > 0:
        if per < 5:       scores["per"] = 18
        elif per < 8:     scores["per"] = 13
        elif per < 10:    scores["per"] = 8
        elif per < 15:    scores["per"] = 4
        else:             scores["per"] = 0
        details["per"] = round(per, 2)
        if per < 8:       details["per_status"] = "저평가"
        elif per < 15:    details["per_status"] = "적정"
        else:             details["per_status"] = "고평가"
    else:
        scores["per"] = 0
        details["per"] = None
        details["per_status"] = None

    # PBR (5점)
    pbr = naver.get("pbr") or info.get("priceToBook")
    if not pbr:
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
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

    # 이익 지속성 (5점)
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

    # 단독 상장 여부 (4점)
    if ticker_code in DOUBLE_LISTED:
        scores["listing"] = 0
        details["listing"] = "중복상장"
    else:
        scores["listing"] = 4
        details["listing"] = "단독 상장 ✅"

    return {"total": sum(scores.values()), "max": 32, "scores": scores, "details": details}


def calc_category_b(info: dict, naver: dict, ticker_code: str) -> dict:
    scores = {}
    details = {}

    # 배당수익률 (10점)
    price    = info.get("currentPrice") or info.get("regularMarketPrice") or 0
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

    # 배당 빈도 (4점)
    if ticker_code in QUARTERLY_DIVIDEND:
        scores["dividend_freq"] = 4
        details["dividend_freq"] = "분기 배당 ✅"
    else:
        scores["dividend_freq"] = 0
        details["dividend_freq"] = "연 1회 배당"

    # 배당 안정성 (4점)
    if ticker_code in DIVIDEND_GROWTH_10Y:
        scores["dividend_stability"] = 4
        details["dividend_stability"] = "10년+ 연속 인상 ✅"
    elif ticker_code in DIVIDEND_GROWTH_5Y:
        scores["dividend_stability"] = 3
        details["dividend_stability"] = "5년+ 연속 인상 ✅"
    elif ticker_code in DIVIDEND_STABLE:
        scores["dividend_stability"] = 2
        details["dividend_stability"] = "3년+ 배당 유지"
    else:
        payout = info.get("payoutRatio", 0) or 0
        if div_rate > 0 and 0 < payout < 0.8:
            scores["dividend_stability"] = 1
            details["dividend_stability"] = "배당 지속 중"
        else:
            scores["dividend_stability"] = 0
            details["dividend_stability"] = "배당 이력 불명확"

    # 자사주 소각 여부 (6점)
    if ticker_code in BUYBACK_EXCELLENT:
        scores["buyback"] = 6
        details["buyback"] = "정기 자사주 소각 ✅"
    else:
        scores["buyback"] = 0
        details["buyback"] = "소각 미실시"

    # 주주환원 강도 — 연간 소각 비율 (7점)
    ratio = BUYBACK_RATIO.get(ticker_code, 0)
    if ratio > 2.0:
        scores["buyback_ratio"] = 7
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

    # 유통주식 건전성 — 자사주 보유 비율 (4점)
    treasury = TREASURY_RATIO.get(ticker_code, -1)
    if treasury == -1:
        scores["treasury"] = 4
        details["treasury"] = "자사주 없음 ✅"
    elif treasury < 2.0:
        scores["treasury"] = 3
        details["treasury"] = f"자사주 {treasury}% (양호)"
    elif treasury < 5.0:
        scores["treasury"] = 2
        details["treasury"] = f"자사주 {treasury}% (보통)"
    else:
        scores["treasury"] = 0
        details["treasury"] = f"자사주 {treasury}% (과다)"

    # 부채 건전성 (6점)
    sector = info.get("sector", "")
    dte    = info.get("debtToEquity")
    if sector in ["Financial Services", "금융"]:
        scores["debt_safety"]     = 4
        details["debt_to_equity"] = None
        details["debt_grade"]     = "금융업 예외"
    elif dte is not None:
        if dte < 50:
            scores["debt_safety"]     = 6
            details["debt_to_equity"] = round(dte, 1)
            details["debt_grade"]     = "매우 안전"
        elif dte < 100:
            scores["debt_safety"]     = 5
            details["debt_to_equity"] = round(dte, 1)
            details["debt_grade"]     = "안전"
        elif dte < 200:
            scores["debt_safety"]     = 3
            details["debt_to_equity"] = round(dte, 1)
            details["debt_grade"]     = "양호"
        elif dte < 400:
            scores["debt_safety"]     = 1
            details["debt_to_equity"] = round(dte, 1)
            details["debt_grade"]     = "주의"
        else:
            scores["debt_safety"]     = 0
            details["debt_to_equity"] = round(dte, 1)
            details["debt_grade"]     = "위험"
    else:
        scores["debt_safety"]     = 2
        details["debt_to_equity"] = None
        details["debt_grade"]     = "N/A"

    return {"total": sum(scores.values()), "max": 41, "scores": scores, "details": details}


def calc_category_c(info: dict, ticker_code: str) -> dict:
    scores = {}
    details = {}

    scores["growth"] = 5
    details["growth"] = "수동 입력 필요"

    scores["management"] = 5
    details["management"] = "수동 입력 필요"

    if ticker_code in GLOBAL_BRAND:
        scores["brand"] = 4
        details["brand"] = "세계적 브랜드 보유 ✅"
    else:
        scores["brand"] = 0
        details["brand"] = "글로벌 브랜드 없음"

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

    return {"total": sum(scores.values()), "max": 27, "scores": scores, "details": details}


def get_grade(score: int) -> dict:
    if score >= 90: return {"grade": "S", "label": "최고의 매수 기회 · 강력 매수",    "color": "#a78bfa"}
    if score >= 80: return {"grade": "A", "label": "장기투자 강력 추천 · 적극 매수",  "color": "#10b981"}
    if score >= 70: return {"grade": "B", "label": "한국 시장 우량주 · 매수 고려",    "color": "#3b82f6"}
    if score >= 50: return {"grade": "C", "label": "보유 유지 · 추가 매수 신중",      "color": "#f59e0b"}
    return             {"grade": "D", "label": "장기투자 비추천",                  "color": "#ef4444"}


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
        try:
            income = stock.income_stmt
            if income is not None and not income.empty:
                for col in income.columns[:4]:
                    try:
                        op_inc = income.loc["Operating Income", col]
                        rev    = income.loc["Total Revenue", col]
                        if rev and rev != 0:
                            op_margins.append(round(float(op_inc / rev), 4))
                    except: pass
        except: pass

        cat_a = calc_category_a(info, {"operating_margins": op_margins}, naver, ticker_code)
        cat_b = calc_category_b(info, naver, ticker_code)
        cat_c = calc_category_c(info, ticker_code)
        total = min(100, cat_a["total"] + cat_b["total"] + cat_c["total"])
        grade = get_grade(total)

        return {
            "ticker":         ticker_code,
            "name":           info.get("longName") or info.get("shortName") or ticker_code,
            "score":          total,
            "grade":          grade["grade"],
            "grade_label":    grade["label"],
            "per":            cat_a["details"].get("per"),
            "pbr":            cat_a["details"].get("pbr"),
            "roe":            naver.get("roe") or (round(info.get("returnOnEquity") * 100, 2) if info.get("returnOnEquity") else None),
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
            "051910", "035420", "068270", "207940", "006400",
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
                (ticker, name, score, grade, grade_label, per, pbr, roe, dividend_yield, sector, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                    name=EXCLUDED.name, score=EXCLUDED.score, grade=EXCLUDED.grade,
                    grade_label=EXCLUDED.grade_label, per=EXCLUDED.per, pbr=EXCLUDED.pbr,
                    roe=EXCLUDED.roe, dividend_yield=EXCLUDED.dividend_yield,
                    sector=EXCLUDED.sector, updated_at=NOW()
            """, (
                r["ticker"], r["name"], r["score"], r["grade"],
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
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    scheduler.add_job(run_full_scan, "cron", hour=2, minute=0, kwargs={"start": 0, "end": 9999})
    scheduler.start()
    print("✅ 스케줄러 시작 — 매일 새벽 2시 자동 스캔")


@app.get("/")
def root():
    return {"message": "가치투자 스크리닝 API v3.0 🚀"}


@app.get("/reset-rankings")
async def reset_rankings():
    """랭킹 데이터 초기화"""
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


@app.get("/ranking")
async def get_ranking():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, name, score, grade, grade_label,
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
                    "name":           r[1],
                    "score":          r[2],
                    "grade":          r[3],
                    "grade_label":    r[4],
                    "per":            r[5],
                    "pbr":            r[6],
                    "roe":            r[7],
                    "dividend_yield": r[8],
                    "sector":         r[9],
                    "updated_at":     r[10].strftime("%Y-%m-%d %H:%M") if r[10] else None,
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
        p = info.get("currentPrice") or info.get("regularMarketPrice")
        if p:
            return {
                "yfinance": {
                    "priceToBook":    info.get("priceToBook"),
                    "bookValue":      info.get("bookValue"),
                    "trailingPE":     info.get("trailingPE"),
                    "debtToEquity":   info.get("debtToEquity"),
                    "returnOnEquity": info.get("returnOnEquity"),
                    "dividendYield":  info.get("dividendYield"),
                    "dividendRate":   info.get("dividendRate"),
                    "sector":         info.get("sector"),
                },
                "naver": naver,
                "is_double_listed":   ticker_code in DOUBLE_LISTED,
                "has_buyback_policy": ticker_code in BUYBACK_EXCELLENT,
                "quarterly_dividend": ticker_code in QUARTERLY_DIVIDEND,
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
        try:
            income = stock.income_stmt
            if income is not None and not income.empty:
                for col in income.columns[:4]:
                    try:
                        op_inc = income.loc["Operating Income", col]
                        rev    = income.loc["Total Revenue", col]
                        if rev and rev != 0:
                            op_margins.append(round(float(op_inc / rev), 4))
                    except: pass
        except: pass

        cat_a = calc_category_a(info, {"operating_margins": op_margins}, naver, ticker_code)
        cat_b = calc_category_b(info, naver, ticker_code)
        cat_c = calc_category_c(info, ticker_code)
        total = min(100, cat_a["total"] + cat_b["total"] + cat_c["total"])

        return {
            "ticker":      ticker_code,
            "name":        info.get("longName") or info.get("shortName") or ticker_code,
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
                "roe":            naver.get("roe") or (round(info.get("returnOnEquity") * 100, 2) if info.get("returnOnEquity") else None),
                "roe_status":     None,
                "dividend_yield": cat_b["details"].get("dividend_yield"),
                "dy_status":      cat_b["details"].get("dy_status"),
                "debt_to_equity": cat_b["details"].get("debt_to_equity"),
                "debt_grade":     cat_b["details"].get("debt_grade"),
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