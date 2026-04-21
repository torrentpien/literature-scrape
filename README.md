# Academic Journal PDF Scraper & Summarizer

Automatically scrape the latest articles from academic journals, download PDFs via institutional access, and generate structured bilingual (Chinese/English) summaries using LLMs.

## Features

- **Multi-source article discovery** — RSS feeds, CrossRef API, OpenAlex API, and publisher TOC scraping
- **Automated PDF download** — Institutional IP access (e.g., NCCU 140.119.x.x) with Cloudflare bypass (`curl_cffi`) and JS-challenge handling (`playwright`)
- **9-section structured summaries** — Research question, theoretical context, framework, data, methods, findings, conclusions, limitations, and R simulation code
- **Bilingual output** — Each section produced in both Traditional Chinese and English
- **R simulation code** — Automatically generates runnable R code with simulated data and statistical models matching the paper's methodology (quantitative studies only)
- **Web UI** — Browse articles, view summaries, check for new issues, trigger pipelines, retry failed downloads
- **Multiple LLM backends** — OpenAI GPT (default), Anthropic Claude, or local rule-based extraction
- **Periodic scheduling** — Configurable interval for automatic scraping

## Supported Journals

| Key | Journal | Publisher | Platform |
|-----|---------|-----------|----------|
| `asr` | American Sociological Review | SAGE | Atypon |
| `ajs` | American Journal of Sociology | U of Chicago Press | Atypon |
| `nclimate` | Nature Climate Change | Springer Nature | Nature |
| `jcc` | Journal of Contemporary China | Taylor & Francis | Atypon |
| `chinaq` | The China Quarterly | Cambridge UP | Cambridge Core |
| `socprob` | Social Problems | Oxford UP | Silverchair |
| `socforces` | Social Forces | Oxford UP | Silverchair |

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt

# Required for JS-challenge sites (Springer Nature):
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — add your OpenAI API key
```

Key settings in `.env`:
```
OPENAI_API_KEY=sk-proj-xxxxx
SUMMARIZER_BACKEND=openai        # or "claude" or "local"
OPENAI_MODEL=gpt-4o-mini         # or gpt-4o
```

### 3. Run via CLI

```bash
# List latest articles (no download)
python main.py list -j asr

# Full pipeline: fetch → download PDF → summarize (Traditional Chinese)
python main.py run -j asr -b openai -l zh

# Download PDFs only (no summarization)
python main.py download -j asr

# Periodic scheduling (every 168 hours = weekly)
python main.py schedule -j asr -i 168

# Show all configured journals
python main.py journals

# Diagnose RSS feed
python main.py debug-rss -j asr

# Diagnose PDF download access
python main.py debug-download -j asr
```

### 4. Launch Web UI

```bash
python web/app.py
# Open http://localhost:5000
```

**Web UI features:**
- **Dashboard** — Journal cards with article/PDF/summary counts; "Check for new articles" per journal or all at once
- **Pipeline control** — Full pipeline (fetch → download → summarize) or summarize-only mode (skip re-downloading)
- **Article list** — Search/filter by title, author, status; per-article retry download button; batch retry for all missing PDFs
- **Article detail** — 9-section structured summary with bilingual output
- **R code page** — Syntax-highlighted R simulation code with copy/download buttons and per-article regeneration

## Institutional Access & Bot Protection

Downloading paywalled PDFs requires:

1. **Institutional network** — NCCU campus IP (140.119.x.x) or VPN
2. **Cloudflare bypass** — `curl_cffi` impersonates Chrome's TLS fingerprint (SAGE, T&F, Chicago)
3. **JS challenge bypass** — `playwright` with headless Chromium solves JavaScript challenges (Springer Nature)

```bash
pip install curl_cffi playwright
playwright install chromium
```

Diagnostic commands:
```bash
python main.py debug-download -j asr       # Test SAGE access
python main.py debug-download -j nclimate   # Test Nature access
```

## Summary Structure

Each article summary contains 9 sections (bilingual: Chinese + English):

1. **Research Question** — Core problem, motivation, background
2. **Theoretical Context** — Literature conversation, position in existing research
3. **Theoretical Framework** — Core theories/concepts and their relationships
4. **Data Source** — Dataset, sample size, characteristics, time period
5. **Model & Methodology** — Methods, statistical models, variables (IV/DV/controls)
6. **Findings / Results** — Empirical results, hypothesis support/rejection
7. **Conclusion & Contribution** — Main conclusions, theoretical/practical contributions
8. **Limitations & Future Research** — Author-noted limitations, future directions
9. **R Simulation Code** — Auto-generated R code with simulated data and models matching the paper's methodology (quantitative studies only; skipped for qualitative research)

## Adding New Journals

Add an entry to the `JOURNALS` dict in `config.py`:

```python
"newjournal": {
    "name": "Journal Name",
    "issn": "0000-0000",
    "publisher": "sage",         # sage, uchicago, tandf, nature, cambridge, oup
    "pdf_base_url": "https://publisher.com/doi/pdf/{doi}",
    "landing_url": "https://publisher.com/doi/{doi}",
    "toc_url": "https://publisher.com/toc/journal/current",
    "rss_urls": [
        "https://publisher.com/action/showFeed?jc=xxx&type=etoc&feed=rss_2_0",
    ],
},
```

**URL template placeholders:**
- `{doi}` — Full DOI (e.g., `10.1177/00031224251409746`)
- `{article_id}` — DOI suffix after prefix (e.g., `s41558-025-02345-7` for Nature)

## Project Structure

```
literature-scrape/
├── main.py              # CLI entry point & scheduler
├── config.py            # Journal registry, API settings, paths
├── demo_data.py         # Generate test data for UI preview
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── src/
│   ├── scraper.py       # Article discovery (RSS/CrossRef/OpenAlex/TOC)
│   ├── downloader.py    # PDF download (curl_cffi + playwright fallback)
│   ├── extractor.py     # PDF text extraction & section identification
│   └── summarizer.py    # LLM summarization (OpenAI/Claude/local)
├── web/
│   ├── app.py           # Flask web application
│   ├── templates/       # Jinja2 HTML templates
│   │   ├── base.html    #   Layout (navbar, footer)
│   │   ├── index.html   #   Dashboard
│   │   ├── journal.html #   Article list with retry buttons
│   │   ├── article.html #   Article detail & structured summary
│   │   └── rcode.html   #   R simulation code page
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── output/
│   ├── pdfs/<journal>/        # Downloaded PDFs
│   ├── summaries/<journal>/   # Summaries (.json + .md)
│   └── <journal>_metadata.json
└── logs/
    └── scraper.log
```

---

# 學術期刊 PDF 抓取與摘要工具

自動抓取學術期刊最新文章的 PDF，並透過 LLM 產生結構化的中英文並列摘要。

## 功能特色

- **多來源文章發現**：RSS、CrossRef API、OpenAlex API、出版社 TOC 網頁爬取
- **自動 PDF 下載**：校園 IP（政大 140.119.x.x）+ Cloudflare 繞過（`curl_cffi`）+ JS 挑戰處理（`playwright`）
- **9 段式結構化摘要**：研究問題、理論脈絡、理論架構、資料、方法、發現、結論、限制、R 模擬程式碼
- **中英文並列輸出**：每一節同時以繁體中文和英文呈現
- **R 模擬重製程式碼**：自動產生可執行的 R 程式碼，含模擬數據與統計模型（僅量化研究）
- **Web UI**：瀏覽文章、查看摘要、檢查新一期、觸發任務、重試失敗下載
- **多種 LLM 後端**：OpenAI GPT（預設）、Anthropic Claude、本地規則
- **定時排程**：可設定固定間隔自動抓取

## 目前支援期刊

| 代碼 | 期刊 | 出版社 | 平台 |
|------|------|--------|------|
| `asr` | American Sociological Review | SAGE | Atypon |
| `ajs` | American Journal of Sociology | 芝加哥大學出版社 | Atypon |
| `nclimate` | Nature Climate Change | Springer Nature | Nature |
| `jcc` | Journal of Contemporary China | Taylor & Francis | Atypon |
| `chinaq` | The China Quarterly | 劍橋大學出版社 | Cambridge Core |
| `socprob` | Social Problems | 牛津大學出版社 | Silverchair |
| `socforces` | Social Forces | 牛津大學出版社 | Silverchair |

## 快速開始

### 1. 安裝

```bash
pip install -r requirements.txt
playwright install chromium        # Nature 等需要瀏覽器解 JS 挑戰
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入 OPENAI_API_KEY
```

### 3. CLI 使用

```bash
python main.py list -j asr                    # 列出最新文章
python main.py run -j asr -b openai -l zh     # 完整流程：抓取 → 下載 → 摘要
python main.py journals                        # 查看所有期刊
python main.py debug-rss -j nclimate           # 診斷 RSS
python main.py debug-download -j asr           # 診斷 PDF 下載
```

### 4. Web UI

```bash
python web/app.py                              # 開啟 http://localhost:5000
```

**功能**：
- **儀表板**：期刊總覽、檢查新文章、一鍵全部檢查
- **任務控制**：完整流程 / 只產生摘要（不重抓 PDF）/ 強制重新摘要
- **文章列表**：搜尋、篩選、單篇重試下載、批次重試所有缺 PDF
- **文章詳情**：9 段結構化摘要（中英並列）
- **R 程式碼頁**：語法高亮、複製、下載 .R 檔、單篇重新產製

## 校園 IP 與機器人偵測

下載付費 PDF 需要：
1. **校園網路**：政大 IP（140.119.x.x）或 VPN
2. **Cloudflare 繞過**：`curl_cffi` 模擬 Chrome TLS 指紋（SAGE、T&F、芝大）
3. **JS 挑戰繞過**：`playwright` 無頭 Chromium（Springer Nature）

## 摘要架構（9 段）

1. **研究問題** — 核心問題、動機、背景
2. **對話的理論脈絡** — 回應/延伸的文獻與理論
3. **理論架構** — 核心概念及關係
4. **資料來源** — 資料集、樣本、特性
5. **研究模型與方法** — 方法、統計模型、自變項/依變項/控制變項
6. **模型結果** — 實證發現、假設驗證
7. **重要結論與貢獻** — 理論與實務貢獻
8. **限制與未來研究** — 作者所述限制、未來方向
9. **R 模擬重製程式碼** — 自動產生模擬數據 + 統計模型 R 程式碼（僅量化研究）

## 新增期刊

在 `config.py` 的 `JOURNALS` 中新增：

```python
"newjournal": {
    "name": "期刊名稱",
    "issn": "0000-0000",
    "publisher": "sage",         # sage, uchicago, tandf, nature, cambridge, oup
    "pdf_base_url": "https://出版社.com/doi/pdf/{doi}",
    "landing_url": "https://出版社.com/doi/{doi}",
    "toc_url": "https://出版社.com/toc/journal/current",
    "rss_urls": ["https://出版社.com/action/showFeed?jc=xxx&type=etoc&feed=rss_2_0"],
},
```

## 專案結構

```
literature-scrape/
├── main.py              # CLI 入口與排程
├── config.py            # 期刊設定、API、路徑
├── demo_data.py         # 產生測試資料
├── requirements.txt     # Python 相依套件
├── .env.example         # 環境變數範本
├── src/
│   ├── scraper.py       # 文章發現（RSS/CrossRef/OpenAlex/TOC）
│   ├── downloader.py    # PDF 下載（curl_cffi + playwright）
│   ├── extractor.py     # PDF 文字擷取與段落辨識
│   └── summarizer.py    # LLM 摘要（OpenAI/Claude/本地）
├── web/
│   ├── app.py           # Flask 網頁應用
│   ├── templates/       # HTML 模板
│   │   ├── base.html    #   版面（導覽列、頁尾）
│   │   ├── index.html   #   儀表板
│   │   ├── journal.html #   文章列表（含重試按鈕）
│   │   ├── article.html #   文章詳情與摘要
│   │   └── rcode.html   #   R 模擬程式碼頁
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── output/
│   ├── pdfs/<期刊>/           # 下載的 PDF
│   ├── summaries/<期刊>/      # 摘要（.json + .md）
│   └── <期刊>_metadata.json
└── logs/
    └── scraper.log
```
