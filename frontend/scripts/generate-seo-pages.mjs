import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const SITE_URL = "https://www.배당스크리너.com";
const API_BASE = process.env.VITE_API_URL || "https://value-screener-production-2355.up.railway.app";
const DIST_DIR = path.resolve("dist");

const fallbackStocks = [
  { ticker: "005930", name: "삼성전자" },
  { ticker: "005387", name: "현대차2우B" },
  { ticker: "000270", name: "기아" },
  { ticker: "086790", name: "하나금융지주" },
  { ticker: "105560", name: "KB금융" },
  { ticker: "055550", name: "신한지주" },
];

const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll('"', "&quot;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");

const replaceMeta = (html, attribute, key, value) => {
  const pattern = new RegExp(`<meta\\s+${attribute}=["']${key}["'][^>]*>`, "i");
  return html.replace(pattern, `<meta ${attribute}="${key}" content="${escapeHtml(value)}" />`);
};

async function fetchStocks() {
  try {
    const response = await fetch(`${API_BASE}/stocks?market=KOSPI`, {
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.stocks) || data.stocks.length === 0) throw new Error("종목 목록이 비어 있습니다");
    return data.stocks;
  } catch (error) {
    console.warn(`종목 목록 API 호출 실패, 기본 목록으로 SEO 페이지를 생성합니다: ${error.message}`);
    return fallbackStocks;
  }
}

function stockHtml(template, stock) {
  const title = `${stock.name} 배당금·배당수익률·배당점수 | 배당스크리너`;
  const description = `${stock.name}(${stock.ticker})의 PER, PBR, ROE, 배당수익률과 100점 만점 배당점수를 확인하세요. 매일 갱신되는 한국 배당주 분석.`;
  const url = `${SITE_URL}/stock/${stock.ticker}`;
  let html = template.replace(/<title>.*?<\/title>/is, `<title>${escapeHtml(title)}</title>`);
  html = replaceMeta(html, "name", "description", description);
  html = replaceMeta(html, "property", "og:title", title);
  html = replaceMeta(html, "property", "og:description", description);
  html = replaceMeta(html, "property", "og:url", url);
  html = replaceMeta(html, "name", "twitter:title", title);
  html = replaceMeta(html, "name", "twitter:description", description);
  html = html.replace(/<link\s+rel=["']canonical["'][^>]*>/i, `<link rel="canonical" href="${url}" />`);
  return html.replace(
    '<div id="root"></div>',
    `<div id="root"><main><h1>${escapeHtml(stock.name)} 배당주 분석</h1><p>${escapeHtml(stock.name)}(${stock.ticker})의 PER, PBR, ROE, 배당수익률과 100점 만점 배당점수를 분석합니다.</p><p>분석 결과는 투자 참고용 정보이며 투자 권유가 아닙니다.</p></main></div>`,
  );
}

const template = await readFile(path.join(DIST_DIR, "index.html"), "utf8");
const stocks = await fetchStocks();

await Promise.all(stocks.map(async (stock) => {
  const directory = path.join(DIST_DIR, "stock", stock.ticker);
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, "index.html"), stockHtml(template, stock), "utf8");
}));

const lastmod = new Date().toISOString().slice(0, 10);
const urls = [
  `  <url><loc>${SITE_URL}/</loc><lastmod>${lastmod}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>`,
  ...stocks.map((stock) => `  <url><loc>${SITE_URL}/stock/${stock.ticker}</loc><lastmod>${lastmod}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>`),
];
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`;
await writeFile(path.join(DIST_DIR, "sitemap.xml"), sitemap, "utf8");
await writeFile(path.join(DIST_DIR, "robots.txt"), `User-agent: *\nAllow: /\n\nSitemap: ${SITE_URL}/sitemap.xml\n`, "utf8");

console.log(`SEO 종목 페이지 ${stocks.length}개와 sitemap.xml 생성 완료`);
