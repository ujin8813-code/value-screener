from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import re
import httpx

app = FastAPI(title="가치투자 스크리닝 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 중복상장 기업 목록 (금융지주 제외) ──
DOUBLE_LISTED = {
    "005930", "005935",
    "005380", "005385", "005387",
    "000270", "000272",
    "051910", "051915",
    "003550", "034730",
    "000660", "017670", "096770",
    "003490",
}

# ── 자사주 소각 우수 기업 ──
BUYBACK_EXCELLENT = {
    "005380", "005385", "005387",
    "000270", "000272",
    "005930", "005935",
    "086790", "105560", "055550",
}


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
                    except:
                        pass

    except Exception as e:
        print(f"네이버 HTML 파싱 실패: {e}")
    return result


def calc_category_a(info: dict, hist_financials: dict, naver: dict) -> dict:
    scores = {}
    details = {}

    # PER (15점) — 네이버 우선
    per = naver.get("per") or info.get("trailingPE") or info.get("forwardPE")
    if per and per > 0:
        if per < 5:       scores["per"] = 15
        elif per < 8:     scores["per"] = 11
        elif per < 12:    scores["per"] = 7
        elif per < 20:    scores["per"] = 3
        else:             scores["per"] = 0
        details["per"] = round(per, 2)
        if per < 8:       details["per_status"] = "저평가"
        elif per < 15:    details["per_status"] = "적정"
        else:             details["per_status"] = "고평가"
    else:
        scores["per"] = 0
        details["per"] = None
        details["per_status"] = None

    # PBR (5점) — 네이버 우선
    pbr = naver.get("pbr") or info.get("priceToBook")
    if not pbr:
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        bvps  = info.get("bookValue") or naver.get("bps") or 0
        if price and bvps and bvps > 0:
            pbr = round(price / bvps, 2)
    if pbr and pbr > 0:
        if pbr < 0.5:     scores["pbr"] = 5
        elif pbr < 1.0:   scores["pbr"] = 4
        elif pbr < 1.5:   scores["pbr"] = 2
        elif pbr < 2.0:   scores["pbr"] = 1
        else:             scores["pbr"] = 0
        details["pbr"] = round(pbr, 2)
        if pbr < 1.0:     details["pbr_status"] = "저평가"
        elif pbr < 1.5:   details["pbr_status"] = "적정"
        else:             details["pbr_status"] = "고평가"
    else:
        scores["pbr"]  = 0
        details["pbr"] = None
        details["pbr_status"] = None

    # ROE (10점) — yfinance TTM 우선, 없으면 네이버
    roe_raw = info.get("returnOnEquity")
    roe_yf  = round(roe_raw * 100, 2) if roe_raw else None
    roe_nav = naver.get("roe")
    roe_pct = roe_yf or roe_nav

    if roe_pct:
        if roe_pct >= 20:   scores["roe"] = 10
        elif roe_pct >= 15: scores["roe"] = 8
        elif roe_pct >= 10: scores["roe"] = 5
        elif roe_pct >= 5:  scores["roe"] = 2
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

    # 이익 안정성 (5점)
    op_margins = hist_financials.get("operating_margins", [])
    if len(op_margins) >= 3:
        all_positive = all(m > 0 for m in op_margins[-4:] if m is not None)
        growing = len(op_margins) >= 2 and op_margins[-1] >= op_margins[0]
        if all_positive and growing: scores["stability"] = 5
        elif all_positive:           scores["stability"] = 3
        else:                        scores["stability"] = 1
    else:
        scores["stability"] = 2

    return {"total": sum(scores.values()), "max": 35, "scores": scores, "details": details}


def calc_category_b(info: dict, naver: dict, ticker_code: str) -> dict:
    scores = {}
    details = {}

    # 배당수익률 (10점) — yfinance 직접계산 우선
    price    = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    div_rate = info.get("dividendRate", 0) or 0
    dy_calc  = round((div_rate / price) * 100, 2) if price and div_rate else None
    dy_nav   = naver.get("dividend_yield")
    dy_raw   = info.get("dividendYield")
    dy_yf    = (dy_raw if dy_raw and dy_raw > 1 else dy_raw * 100) if dy_raw else None
    # 직접계산 → yfinance → 네이버 순서
    dy_pct   = dy_calc or dy_yf or dy_nav

    if dy_pct and dy_pct > 0:
        if dy_pct > 6:    scores["dividend_yield"] = 10
        elif dy_pct > 4:  scores["dividend_yield"] = 7
        elif dy_pct > 2:  scores["dividend_yield"] = 4
        elif dy_pct > 1:  scores["dividend_yield"] = 2
        else:             scores["dividend_yield"] = 0
        details["dividend_yield"] = round(dy_pct, 2)
        if dy_pct > 4:    details["dy_status"] = "고배당"
        elif dy_pct > 2:  details["dy_status"] = "양호"
        else:             details["dy_status"] = "낮음"
    else:
        scores["dividend_yield"] = 0
        details["dividend_yield"] = 0.0
        details["dy_status"] = None

    # 자사주 소각 (10점)
    if ticker_code in BUYBACK_EXCELLENT:
        scores["buyback"] = 10
        details["buyback"] = "자사주 100% 소각 정책 ✅"
    else:
        scores["buyback"] = 3
        details["buyback"] = "소각 정책 미확인"

    # 배당 지속성 (5점)
    payout = info.get("payoutRatio", 0) or 0
    if div_rate > 0 and 0 < payout < 0.8:
        scores["dividend_continuity"] = 5
        details["dividend_continuity"] = "배당 지속 중 (양호)"
    elif div_rate > 0:
        scores["dividend_continuity"] = 3
        details["dividend_continuity"] = "배당 지속 중"
    else:
        scores["dividend_continuity"] = 0
        details["dividend_continuity"] = "배당 없음"

    # 단독 상장 여부 (5점)
    if ticker_code in DOUBLE_LISTED:
        scores["listing"] = 0
        details["listing"] = "중복상장"
    else:
        scores["listing"] = 5
        details["listing"] = "단독 상장 ✅"

    # 부채비율 (5점) — 금융주 예외처리
    sector = info.get("sector", "")
    dte    = info.get("debtToEquity")
    if sector in ["Financial Services", "금융"]:
        scores["debt_safety"]     = 3
        details["debt_to_equity"] = dte
        details["debt_grade"]     = "금융업 예외"
    elif dte is not None:
        if dte < 100:
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

    return {"total": sum(scores.values()), "max": 35, "scores": scores, "details": details}


def calc_category_c(info: dict, ticker_code: str) -> dict:
    scores = {}
    details = {}

    # 미래 성장 잠재력 (10점 더미)
    scores["growth"] = 6
    details["growth"] = "수동 입력 필요"

    # 기업 경영 (10점 더미)
    scores["management"] = 6
    details["management"] = "수동 입력 필요"

    # 세계적 브랜드 (5점 더미)
    scores["brand"] = 3
    details["brand"] = "수동 입력 필요"

    # 경쟁 해자 (5점) — 시가총액 기반
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

    return {"total": sum(scores.values()), "max": 30, "scores": scores, "details": details}


def get_grade(score: int) -> dict:
    if score >= 90: return {"grade": "S", "label": "생애 최고의 매수 기회 · 강력 매수", "color": "#a78bfa"}
    if score >= 80: return {"grade": "A", "label": "장기투자 강력 추천 · 적극 매수",    "color": "#10b981"}
    if score >= 65: return {"grade": "B", "label": "한국 시장 우량주 · 장기투자 적합",  "color": "#3b82f6"}
    if score >= 50: return {"grade": "C", "label": "보유 유지 · 추가 매수 신중",        "color": "#f59e0b"}
    return             {"grade": "D", "label": "장기투자 비추천",                    "color": "#ef4444"}


@app.get("/")
def root():
    return {"message": "가치투자 스크리닝 API 정상 작동 중 🚀"}


@app.get("/debug/{ticker_code}")
async def debug(ticker_code: str):
    naver = await fetch_naver_metrics(ticker_code)
    for suffix in [".KS", ".KQ"]:
        stock = yf.Ticker(ticker_code.strip().zfill(6) + suffix)
        info  = stock.info
        p = info.get("currentPrice") or info.get("regularMarketPrice")
        if p:
            price    = p
            div_rate = info.get("dividendRate", 0) or 0
            dy_calc  = round((div_rate / price) * 100, 2) if price and div_rate else None
            return {
                "yfinance": {
                    "priceToBook":    info.get("priceToBook"),
                    "bookValue":      info.get("bookValue"),
                    "trailingPE":     info.get("trailingPE"),
                    "debtToEquity":   info.get("debtToEquity"),
                    "returnOnEquity": info.get("returnOnEquity"),
                    "dividendYield":  info.get("dividendYield"),
                    "dividendRate":   div_rate,
                    "dy_calc":        dy_calc,
                    "sector":         info.get("sector"),
                },
                "naver": naver,
                "is_double_listed":   ticker_code in DOUBLE_LISTED,
                "has_buyback_policy": ticker_code in BUYBACK_EXCELLENT,
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
                    except:
                        pass
        except:
            pass

        cat_a = calc_category_a(info, {"operating_margins": op_margins}, naver)
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
                "roe":            cat_a["details"].get("roe"),
                "roe_status":     cat_a["details"].get("roe_status"),
                "dividend_yield": cat_b["details"].get("dividend_yield"),
                "dy_status":      cat_b["details"].get("dy_status"),
                "debt_to_equity": cat_b["details"].get("debt_to_equity"),
                "debt_grade":     cat_b["details"].get("debt_grade"),
                "buyback_policy": cat_b["details"].get("buyback"),
                "listing":        cat_b["details"].get("listing"),
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