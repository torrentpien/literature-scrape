# 學術期刊 PDF 抓取與摘要工具

自動抓取學術期刊最新文章的 PDF，並進行結構化摘要分析。

## 功能特色

- **多來源文章發現**：透過 CrossRef API、OpenAlex API、SAGE 網頁三種方式取得最新文章
- **自動 PDF 下載**：支援透過校園 IP（如政大 140.119.x.x）下載付費期刊 PDF
- **結構化摘要**：自動分析並產出研究問題、理論框架、資料、方法、發現、貢獻
- **雙語支援**：摘要可產出繁體中文或英文
- **定時排程**：可設定固定間隔自動抓取
- **可擴充架構**：輕鬆新增更多期刊

## 目前支援期刊

| 代碼 | 期刊 | ISSN | 出版社 |
|------|------|------|--------|
| `asr` | American Sociological Review | 0003-1224 | SAGE |

## 快速開始

### 1. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env，填入你的 API key
```

如果不使用 Claude API 進行摘要，可使用 `local` 模式（無需 API key）。

### 3. 執行

```bash
# 列出最新文章（不下載）
python main.py list -j asr

# 完整流程：抓取 → 下載 PDF → 產生摘要（繁體中文）
python main.py run -j asr -b claude -l zh

# 使用本地摘要（不需要 API key）
python main.py run -j asr -b local

# 僅下載 PDF
python main.py download -j asr

# 定時排程（每 168 小時 = 每週）
python main.py schedule -j asr -i 168

# 查看已設定的期刊
python main.py journals
```

## 使用說明

### 校園 IP 存取

下載付費期刊 PDF 需要透過有訂閱權限的校園網路。在政治大學校園內（IP: 140.119.x.x）或透過 VPN 連線即可。

### 摘要後端

- **`claude`**（預設）：使用 Anthropic Claude API，品質最佳。需設定 `ANTHROPIC_API_KEY`。
- **`local`**：基於規則的文字擷取，無需 API key，品質較低但完全離線。

### 輸出結構

```
output/
├── pdfs/
│   └── asr/           # 各期刊 PDF 檔案
│       └── *.pdf
├── summaries/
│   └── asr/           # 各期刊摘要
│       ├── *.json     # 結構化 JSON
│       └── *.md       # 可讀 Markdown
└── asr_metadata.json  # 文章元資料
```

### 摘要格式

每篇文章的摘要包含：

1. **研究問題** - 核心問題與子問題
2. **理論框架** - 理論、概念框架、文獻對話
3. **資料來源** - 資料集、樣本、時間範圍
4. **研究方法** - 統計模型、分析策略
5. **主要發現** - 關鍵實證結果
6. **學術貢獻** - 理論與政策意涵

## 新增期刊

在 `config.py` 的 `JOURNALS` dict 中新增條目：

```python
JOURNALS = {
    "asr": { ... },  # 既有設定
    "ajs": {
        "name": "American Journal of Sociology",
        "issn": "0002-9602",
        "publisher": "chicago",
        "pdf_base_url": "https://www.journals.uchicago.edu/doi/pdf/{doi}",
        "landing_url": "https://www.journals.uchicago.edu/doi/{doi}",
        "toc_url": "https://www.journals.uchicago.edu/toc/ajs/current",
    },
}
```

## 專案結構

```
literature-scrape/
├── main.py              # CLI 入口與排程
├── config.py            # 設定（期刊、API、路徑）
├── requirements.txt     # Python 相依套件
├── .env.example         # 環境變數範本
├── src/
│   ├── scraper.py       # 文章元資料抓取（CrossRef/OpenAlex/SAGE）
│   ├── downloader.py    # PDF 下載器
│   ├── extractor.py     # PDF 文字擷取與段落辨識
│   └── summarizer.py    # 摘要產生（Claude API / 本地）
├── output/
│   ├── pdfs/            # 下載的 PDF
│   └── summaries/       # 產生的摘要
└── logs/                # 執行紀錄
```
