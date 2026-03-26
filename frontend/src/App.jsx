import { useState, useEffect } from "react";

const API_BASE = "https://value-screener-production-2355.up.railway.app.up.railway.app";

const GRADE_CONFIG = {
  S: { color: "#a78bfa", border: "border-violet-400", text: "text-violet-300", bg: "from-violet-500/20 to-purple-500/20" },
  A: { color: "#34d399", border: "border-emerald-400", text: "text-emerald-300", bg: "from-emerald-500/20 to-teal-500/20" },
  B: { color: "#60a5fa", border: "border-blue-400",    text: "text-blue-300",    bg: "from-blue-500/20 to-cyan-500/20" },
  C: { color: "#fbbf24", border: "border-amber-400",   text: "text-amber-300",   bg: "from-amber-500/20 to-orange-500/20" },
  D: { color: "#f87171", border: "border-red-400",     text: "text-red-300",     bg: "from-red-500/20 to-rose-500/20" },
};

const STATUS_CONFIG = {
  "저평가":      { bg: "bg-emerald-500/20", text: "text-emerald-300" },
  "적정":        { bg: "bg-blue-500/20",    text: "text-blue-300" },
  "고평가":      { bg: "bg-red-500/20",     text: "text-red-300" },
  "우수":        { bg: "bg-emerald-500/20", text: "text-emerald-300" },
  "양호":        { bg: "bg-blue-500/20",    text: "text-blue-300" },
  "보통":        { bg: "bg-amber-500/20",   text: "text-amber-300" },
  "저조":        { bg: "bg-red-500/20",     text: "text-red-300" },
  "고배당":      { bg: "bg-emerald-500/20", text: "text-emerald-300" },
  "낮음":        { bg: "bg-red-500/20",     text: "text-red-300" },
  "안전":        { bg: "bg-emerald-500/20", text: "text-emerald-300" },
  "위험":        { bg: "bg-red-500/20",     text: "text-red-300" },
  "주의":        { bg: "bg-amber-500/20",   text: "text-amber-300" },
  "금융업 예외": { bg: "bg-blue-500/20",    text: "text-blue-300" },
};

const fmt = (n) => n != null ? Number(n).toLocaleString("ko-KR") : "N/A";

function ValueGauge({ score, grade }) {
  const [anim, setAnim] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setAnim(score), 300);
    return () => clearTimeout(t);
  }, [score]);

  const CX = 120, CY = 125, R = 90;
  const circ = Math.PI * R;
  const prog = (anim / 100) * circ;
  const col = GRADE_CONFIG[grade]?.color || "#f87171";
  const scoreToRad = (s) => Math.PI - (s / 100) * Math.PI;

  const markers = [
    { score: 50, label: "C", color: "#fbbf24" },
    { score: 65, label: "B", color: "#60a5fa" },
    { score: 80, label: "A", color: "#34d399" },
    { score: 90, label: "S", color: "#a78bfa" },
  ];

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: 280, height: 165 }}>
        <svg width="280" height="165" viewBox="0 0 280 165">
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="blur"/>
              <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>

          {/* 배경 트랙 */}
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none" stroke="rgba(255,255,255,0.07)"
            strokeWidth="14" strokeLinecap="round"
          />

          {/* 진행 바 */}
          <path
            d={`M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`}
            fill="none" stroke={col} strokeWidth="14" strokeLinecap="round"
            strokeDasharray={`${prog.toFixed(1)} ${circ.toFixed(1)}`}
            filter="url(#glow)"
            style={{ transition: "stroke-dasharray 1.4s cubic-bezier(0.34,1.56,0.64,1)" }}
          />

          {/* 등급 마커 */}
          {markers.map(({ score: s, label, color }) => {
            const rad = scoreToRad(s);
            const ix = CX + (R - 8) * Math.cos(rad);
            const iy = CY - (R - 8) * Math.sin(rad);
            const ox = CX + (R + 8) * Math.cos(rad);
            const oy = CY - (R + 8) * Math.sin(rad);
            const lx = CX + (R + 20) * Math.cos(rad);
            const ly = CY - (R + 20) * Math.sin(rad);
            const nx = CX + (R + 34) * Math.cos(rad);
            const ny = CY - (R + 34) * Math.sin(rad);
            return (
              <g key={label}>
                <line x1={ix} y1={iy} x2={ox} y2={oy} stroke={color} strokeWidth="2" opacity="0.9"/>
                <text x={lx} y={ly + 4} fill={color} fontSize="11" fontWeight="bold" textAnchor="middle">{label}</text>
                <text x={nx} y={ny + 4} fill={color} fontSize="9" textAnchor="middle" opacity="0.6">{s}</text>
              </g>
            );
          })}

          {/* 0 / 100 눈금 */}
          <text x={CX - R - 14} y={CY + 16} fill="rgba(255,255,255,0.2)" fontSize="10" textAnchor="middle">0</text>
          <text x={CX + R + 14} y={CY + 16} fill="rgba(255,255,255,0.2)" fontSize="10" textAnchor="middle">100</text>
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-end pb-3">
          <span style={{ fontSize: 52, color: col, fontFamily: "monospace", lineHeight: 1, transition: "color 0.5s", fontWeight: 700 }}>
            {Math.round(anim)}
          </span>
          <span className="text-white/30 text-xs tracking-widest mt-1">/ 100점</span>
        </div>
      </div>

      <div className={`mt-3 px-8 py-2 rounded-full border ${GRADE_CONFIG[grade]?.border} bg-white/5`}>
        <span className={`text-2xl font-black ${GRADE_CONFIG[grade]?.text}`}>{grade}등급</span>
      </div>
    </div>
  );
}

function ScoreBar({ label, score, max, color }) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setW(Math.round((score / max) * 100)), 500);
    return () => clearTimeout(t);
  }, [score, max]);

  return (
    <div className="mb-4">
      <div className="flex justify-between mb-1">
        <span className="text-white/70 text-sm">{label}</span>
        <span className="text-white text-sm font-bold">
          {score}<span className="text-white/30">/{max}</span>
        </span>
      </div>
      <div className="h-2.5 bg-white/10 rounded-full overflow-hidden">
        <div className="h-full rounded-full"
          style={{
            width: `${w}%`, background: color,
            transition: "width 1.2s cubic-bezier(0.34,1.56,0.64,1)",
            boxShadow: `0 0 10px ${color}60`
          }}
        />
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit = "", highlight = false, status = null }) {
  const sc = STATUS_CONFIG[status];
  return (
    <div className={`p-4 rounded-xl border ${highlight ? "border-blue-400/40 bg-blue-500/10" : "border-white/10 bg-white/5"}`}>
      <div className="flex items-center justify-between mb-1">
        <p className="text-white/40 text-xs">{label}</p>
        {status && sc && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${sc.bg} ${sc.text}`}>{status}</span>
        )}
      </div>
      <p className={`font-black text-xl ${highlight ? "text-blue-300" : value != null ? "text-white" : "text-white/30"}`}>
        {value != null ? `${value}${unit}` : "N/A"}
      </p>
    </div>
  );
}

function DebtCard({ value, grade }) {
  const colorMap = {
    "안전":        { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-300" },
    "양호":        { bg: "bg-blue-500/10",    border: "border-blue-500/30",    text: "text-blue-300" },
    "주의":        { bg: "bg-amber-500/10",   border: "border-amber-500/30",   text: "text-amber-300" },
    "위험":        { bg: "bg-red-500/10",     border: "border-red-500/30",     text: "text-red-300" },
    "금융업 예외": { bg: "bg-blue-500/10",    border: "border-blue-500/30",    text: "text-blue-300" },
    "N/A":         { bg: "bg-white/5",        border: "border-white/10",       text: "text-white/30" },
  };
  const c = colorMap[grade] || colorMap["N/A"];
  return (
    <div className={`p-4 rounded-xl border ${c.border} ${c.bg}`}>
      <p className="text-white/40 text-xs mb-1">부채비율</p>
      <div className="flex items-baseline gap-2">
        <p className={`font-black text-xl ${c.text}`}>{value != null ? `${value}%` : "N/A"}</p>
        {grade && grade !== "N/A" && <span className={`text-xs ${c.text}`}>{grade}</span>}
      </div>
    </div>
  );
}

function DividendSimulator({ dividendYield }) {
  const [principal, setPrincipal] = useState(10000000);
  const [years,     setYears]     = useState(10);
  const [reinvest,  setReinvest]  = useState(true);
  const [results,   setResults]   = useState([]);
  const [noReinvestResults, setNoReinvestResults] = useState([]);

  useEffect(() => {
    const rate = dividendYield / 100;
    let cur = principal, arr = [];
    for (let y = 1; y <= years; y++) {
      const div = cur * rate;
      cur += div;
      arr.push({ year: y, total: Math.round(cur), div: Math.round(div) });
    }
    setResults(arr);

    let arr2 = [];
    for (let y = 1; y <= years; y++) {
      arr2.push({
        year: y,
        total: Math.round(principal + principal * rate * y),
        div: Math.round(principal * rate)
      });
    }
    setNoReinvestResults(arr2);
  }, [principal, years, dividendYield]);

  const filterResults = (arr) => {
    if (arr.length <= 10) return arr;
    const step = Math.ceil(arr.length / 10);
    return arr.filter((_, i) => i === 0 || (i + 1) % step === 0 || i === arr.length - 1);
  };

  const filteredResults    = filterResults(results);
  const filteredNoReinvest = filterResults(noReinvestResults);
  const displayResults     = reinvest ? results : noReinvestResults;
  const maxVal             = results.length ? Math.max(...results.map(r => r.total)) : 1;
  const finalValue         = displayResults.length ? displayResults[displayResults.length - 1].total : 0;
  const totalDiv           = displayResults.reduce((s, r) => s + r.div, 0);
  const gainPct            = Math.round(((finalValue - principal) / principal) * 100);

  return (
    <div className="p-5 rounded-2xl border border-white/10 bg-white/5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xl">❄️</span>
        <h3 className="text-white font-bold text-base">배당 눈덩이 시뮬레이터</h3>
        <span className="ml-auto text-xs px-2 py-1 rounded-full bg-white/10 text-white/40">
          연 {dividendYield.toFixed(1)}%
        </span>
      </div>

      <div className="mb-4">
        <div className="flex justify-between mb-1">
          <label className="text-white/40 text-xs">초기 투자금</label>
          <span className="text-white text-xs font-bold">{(principal/10000).toLocaleString()}만원</span>
        </div>
        <input type="range" min="1000000" max="100000000" step="1000000"
          value={principal} onChange={e => setPrincipal(Number(e.target.value))}
          className="w-full accent-blue-400"/>
        <div className="flex justify-between text-white/20 text-xs mt-1">
          <span>100만</span><span>5,000만</span><span>1억</span>
        </div>
      </div>

      <div className="mb-4">
        <div className="flex justify-between mb-1">
          <label className="text-white/40 text-xs">투자 기간</label>
          <span className="text-white text-xs font-bold">{years}년</span>
        </div>
        <input type="range" min="1" max="30" step="1"
          value={years} onChange={e => setYears(Number(e.target.value))}
          className="w-full accent-blue-400"/>
        <div className="flex justify-between text-white/20 text-xs mt-1">
          <span>1년</span><span>15년</span><span>30년</span>
        </div>
      </div>

      <div className="flex items-center gap-3 mb-5">
        <button onClick={() => setReinvest(!reinvest)}
          className={`relative w-12 h-6 rounded-full transition-colors duration-300 ${reinvest ? "bg-emerald-500" : "bg-white/20"}`}>
          <div className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-all duration-300 ${reinvest ? "left-7" : "left-1"}`}/>
        </button>
        <span className="text-white/50 text-sm">배당금 재투자 (복리)</span>
      </div>

      <div className="flex items-end gap-1.5 mb-2" style={{ height: 160 }}>
        {filteredResults.map((r, i) => {
          const noR      = filteredNoReinvest[i];
          const base     = noR ? Math.round((noR.total / maxVal) * 100) : 0;
          const extra    = Math.round((r.total / maxVal) * 100) - base;
          const isLast   = i === filteredResults.length - 1;
          const displayVal = reinvest ? r.total : (noR?.total || r.total);
          return (
            <div key={r.year} className="flex-1 flex flex-col items-center gap-1" style={{ height: "100%" }}>
              <div className="text-white/50 text-center" style={{ fontSize: 10 }}>
                {Math.round(displayVal / 10000)}만
              </div>
              <div className="w-full flex-1 flex flex-col justify-end">
                {reinvest && extra > 0 && (
                  <div className="w-full rounded-t-sm"
                    style={{ height: `${extra}%`, background: "linear-gradient(to top, #34d399, #06b6d4)", opacity: 0.9 }}
                  />
                )}
                <div className="w-full"
                  style={{
                    height: `${base}%`, minHeight: 6,
                    background: isLast ? "linear-gradient(to top, #1e40af, #3b82f6)" : "linear-gradient(to top, #1e3a5f, #2563eb)",
                    borderRadius: reinvest && extra > 0 ? "0 0 4px 4px" : "4px 4px 0 0",
                    boxShadow: isLast ? "0 0 12px #3b82f640" : "none",
                  }}
                />
              </div>
              <span className="text-white/40 text-xs">{r.year}년</span>
            </div>
          );
        })}
      </div>

      {reinvest && (
        <div className="flex items-center gap-4 mb-3 justify-center">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ background: "#3b82f6" }}/>
            <span className="text-white/40 text-xs">원금+단순배당</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ background: "#34d399" }}/>
            <span className="text-white/40 text-xs">복리 추가 효과</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 mt-2">
        <div className="bg-white/5 border border-white/10 rounded-xl p-3 text-center">
          <p className="text-white/40 text-xs mb-1">최종 자산</p>
          <p className="text-white font-black text-base">{Math.round(finalValue/10000).toLocaleString()}만</p>
        </div>
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-3 text-center">
          <p className="text-emerald-300/60 text-xs mb-1">총 배당</p>
          <p className="text-emerald-300 font-black text-base">+{Math.round(totalDiv/10000).toLocaleString()}만</p>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-3 text-center">
          <p className="text-blue-300/60 text-xs mb-1">수익률</p>
          <p className="text-blue-300 font-black text-base">+{gainPct}%</p>
        </div>
      </div>

      <div className="mt-4 p-3 rounded-xl border border-dashed border-white/15 text-center">
        <p className="text-white/25 text-xs">📌 광고 영역 — 증권사 계좌개설 CPA 링크</p>
      </div>
    </div>
  );
}

export default function App() {
  const [ticker,  setTicker]  = useState("");
  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState("");

  const analyze = async () => {
    const code = ticker.trim();
    if (!code || code.length !== 6) {
      setError("6자리 종목코드를 입력하세요 (예: 005387)");
      return;
    }
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API_BASE}/analyze/${code}`);
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.detail || "분석 실패");
      }
      setResult(await res.json());
    } catch (e) {
      setError(e.message || "서버 오류");
    } finally {
      setLoading(false);
    }
  };

  const handleShare = () => {
    if (!result) return;
    const text = `📊 ${result.name} 가치투자 분석\n총점: ${result.total_score}점\n등급: ${result.grade.grade}등급 — ${result.grade.label}\n\n🔗 지금 분석해보기: ${window.location.href}`;
    if (navigator.share) navigator.share({ title: "가치투자 스크리닝", text });
    else { navigator.clipboard?.writeText(text); alert("📋 클립보드에 복사됐습니다!"); }
  };

  const grade = result?.grade?.grade;
  const cfg   = GRADE_CONFIG[grade] || GRADE_CONFIG["D"];
  const km    = result?.key_metrics || {};

  return (
    <div className="min-h-screen text-white"
      style={{ background: "radial-gradient(ellipse at 20% 50%, #0f172a 0%, #020617 60%), radial-gradient(ellipse at 80% 20%, #1e1b4b 0%, transparent 50%)" }}>
      <div className="max-w-md mx-auto px-4 py-8 pb-20">

        <div className="mb-8">
          <p className="text-white/30 text-xs tracking-widest uppercase mb-2">📈 Value Screener</p>
          <h1 className="text-3xl font-black leading-tight">
            한국 주식<br/>
            <span style={{ background: "linear-gradient(90deg,#60a5fa,#34d399)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              가치투자 분석기
            </span>
          </h1>
          <p className="text-white/30 text-sm mt-2">종목코드 입력 → 100점 만점 투자 등급 즉시 산출</p>
        </div>

        <div className="relative mb-2">
          <input
            type="text" inputMode="numeric" maxLength={6}
            placeholder="종목코드 6자리 (예: 005387)"
            value={ticker}
            onChange={e => setTicker(e.target.value.replace(/\D/g, ""))}
            onKeyDown={e => e.key === "Enter" && analyze()}
            className="w-full bg-white/10 border border-white/20 rounded-2xl px-5 py-4 text-white text-lg placeholder-white/20 focus:outline-none focus:border-blue-400 transition-all"
          />
          <button onClick={analyze} disabled={loading}
            className="absolute right-3 top-1/2 -translate-y-1/2 px-5 py-2 rounded-xl font-bold text-sm text-white disabled:opacity-40"
            style={{ background: "linear-gradient(135deg,#3b82f6,#06b6d4)", boxShadow: "0 0 20px #3b82f640" }}>
            {loading ? "분석중..." : "분석 →"}
          </button>
        </div>

        <div className="flex gap-2 mb-6 flex-wrap">
          {[["005387","현대차2우B"],["000270","기아"],["086790","하나금융"]].map(([code, name]) => (
            <button key={code} onClick={() => setTicker(code)}
              className="px-3 py-1 text-xs rounded-full border border-white/20 text-white/40 hover:text-white hover:border-white/50 transition-all">
              {name}
            </button>
          ))}
        </div>

        {error && (
          <div className="mb-4 p-4 rounded-xl border border-red-500/40 bg-red-500/10 text-red-300 text-sm">
            ⚠️ {error}
          </div>
        )}

        {result && (
          <div className="space-y-4" style={{ animation: "fadeIn 0.5s ease-out" }}>

            <div className={`p-5 rounded-2xl border ${cfg.border} bg-gradient-to-br ${cfg.bg}`}>
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-xl font-black text-white">{result.name}</h2>
                  <p className="text-white/40 text-sm mt-0.5">{result.ticker} · {result.sector}</p>
                </div>
                <div className="text-right">
                  <p className="text-white/30 text-xs">현재가</p>
                  <p className="text-white font-bold text-lg">{fmt(result.price)}원</p>
                </div>
              </div>
            </div>

            <div className={`p-6 rounded-2xl border ${cfg.border} bg-white/5 text-center`}>
              <p className="text-white/30 text-xs tracking-widest uppercase mb-4">VALUE SCORE</p>
              <ValueGauge score={result.total_score} grade={grade} />
              <p className={`mt-4 text-base font-black ${cfg.text}`}>{result.grade.label}</p>
            </div>

            <div className="text-center">
              <span className="text-white/20 text-xs">아래로 스크롤해서 상세 분석 보기</span>
              <div className="mt-1 flex justify-center">
                <svg className="w-4 h-4 text-white/20 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>

            <div className="p-5 rounded-2xl border border-white/10 bg-white/5">
              <h3 className="text-white/40 text-xs tracking-widest uppercase mb-4">카테고리별 점수</h3>
              <ScoreBar label="🛡️ 안전마진 & 자본 효율성" score={result.categories.a.total} max={35} color="#60a5fa" />
              <ScoreBar label="🤝 주주환원 의지"           score={result.categories.b.total} max={35} color="#34d399" />
              <ScoreBar label="🚀 비즈니스 퀄리티"         score={result.categories.c.total} max={30} color="#a78bfa" />
            </div>

            <div className="p-5 rounded-2xl border border-white/10 bg-white/5">
              <h3 className="text-white/40 text-xs tracking-widest uppercase mb-3">핵심 지표</h3>
              <div className="grid grid-cols-2 gap-3">
                <MetricCard label="PER"       value={km.per}            status={km.per_status} />
                <MetricCard label="PBR"       value={km.pbr}            status={km.pbr_status} />
                <MetricCard label="ROE"       value={km.roe}  unit="%"  status={km.roe_status} highlight />
                <MetricCard label="배당수익률" value={km.dividend_yield} unit="%" status={km.dy_status} highlight />
                <div className="col-span-2">
                  <DebtCard value={km.debt_to_equity} grade={km.debt_grade} />
                </div>
              </div>
              <p className="text-white/20 text-xs text-right mt-3">📊 네이버 증권 기준</p>
            </div>

            {km.dividend_yield > 0 && (
              <DividendSimulator dividendYield={km.dividend_yield} />
            )}

            <button onClick={handleShare}
              className="w-full py-4 rounded-2xl font-black text-lg text-white active:scale-95 transition-transform"
              style={{ background: "linear-gradient(135deg,#fbbf24,#f97316)", boxShadow: "0 0 30px #fbbf2430" }}>
              📤 카카오톡으로 결과 공유하기
            </button>

            <p className="text-white/15 text-xs text-center leading-relaxed">
              ⚠️ 본 분석은 참고용 정보 제공 목적이며 투자 권유가 아닙니다.<br/>
              모든 투자 판단과 책임은 투자자 본인에게 있습니다.
            </p>
          </div>
        )}
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}