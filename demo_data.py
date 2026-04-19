#!/usr/bin/env python3
"""
Generate demo data for testing the UI without network access.

Usage:
    python demo_data.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import OUTPUT_DIR, PDF_DIR, SUMMARY_DIR

DEMO_ARTICLES = [
    {
        "title": "The Paradox of Declining Female Happiness",
        "authors": ["Betsey Stevenson", "Justin Wolfers"],
        "doi": "10.1177/000312240907400401",
        "journal": "0003-1224",
        "volume": "74",
        "issue": "2",
        "pages": "190-225",
        "publication_date": "2025-04",
        "abstract": "By many objective measures the lives of women in the United States have improved over the past 35 years, yet measures of subjective well-being indicate that women's happiness has declined both absolutely and relative to men.",
        "pdf_url": "https://journals.sagepub.com/doi/pdf/10.1177/000312240907400401",
        "landing_url": "https://journals.sagepub.com/doi/10.1177/000312240907400401",
        "article_type": "journal-article",
    },
    {
        "title": "Cultural Matching and the Evaluation of Job Applicants",
        "authors": ["Lauren A. Rivera"],
        "doi": "10.1177/0003122412463213",
        "journal": "0003-1224",
        "volume": "77",
        "issue": "6",
        "pages": "999-1022",
        "publication_date": "2025-04",
        "abstract": "This article investigates the role of cultural matching in hiring decisions at elite professional service firms.",
        "pdf_url": "https://journals.sagepub.com/doi/pdf/10.1177/0003122412463213",
        "landing_url": "https://journals.sagepub.com/doi/10.1177/0003122412463213",
        "article_type": "journal-article",
    },
    {
        "title": "Does Incarceration Reduce Voting? Evidence from New York",
        "authors": ["Ariel White"],
        "doi": "10.1177/0003122419884070",
        "journal": "0003-1224",
        "volume": "84",
        "issue": "5",
        "pages": "960-983",
        "publication_date": "2025-04",
        "abstract": "This study uses administrative data to examine how incarceration affects voter turnout.",
        "pdf_url": "https://journals.sagepub.com/doi/pdf/10.1177/0003122419884070",
        "landing_url": "https://journals.sagepub.com/doi/10.1177/0003122419884070",
        "article_type": "journal-article",
    },
]

DEMO_SUMMARY = {
    "title": "The Paradox of Declining Female Happiness",
    "authors": ["Betsey Stevenson", "Justin Wolfers"],
    "doi": "10.1177/000312240907400401",
    "journal": "0003-1224",
    "volume": "74",
    "issue": "2",
    "publication_date": "2025-04",
    "research_question": "- 核心問題：為什麼在過去 35 年間，美國女性在客觀生活條件（教育、就業、薪資）明顯改善的情況下，主觀幸福感反而下降？\n- 研究動機：檢驗女性運動與性別平權的推進是否帶來主觀福祉提升。",
    "theoretical_context": "- 回應 Easterlin 的「幸福悖論」，將其應用到性別研究。\n- 挑戰傳統「進步必然伴隨幸福感提升」的預設。\n- 與 Dolan et al. (2008) 的主觀幸福感文獻對話。",
    "theoretical_framework": "- 主觀幸福感（subjective well-being）作為核心概念。\n- 三種解釋機制：(1) 期望理論 — 運動提高期望，現實跟不上；(2) 第二輪班 (second shift) — 工作家庭雙重負擔；(3) 參照群體變化 — 比較對象從女性擴展到男性。",
    "data_source": "- GSS (General Social Survey, 美國) 1972–2006，N > 50,000。\n- Eurobarometer 1975–2006，歐盟各國。\n- 主要變項：自評幸福感（三點量表）、教育、就業、婚姻、子女。",
    "model_methodology": "- 方法論：量化分析。\n- 模型：有序 probit 迴歸 (ordered probit)。\n- 穩健性：按年齡、教育、族群分組；以世代分析 (cohort analysis) 區分年齡 vs. 世代效應。\n- 外部效度：跨國比較（美 vs. 歐）。",
    "findings": "- 1970 年代起，美國女性幸福感持續下降，絕對與相對皆然。\n- 趨勢跨年齡、種族、教育、婚姻穩定存在。\n- 歐洲出現類似趨勢，排除美國特殊性。\n- 性別幸福感差距逆轉：1970s 女 > 男；2000s 男 > 女。",
    "conclusion_contribution": "- 結論：客觀指標的改善 ≠ 主觀福祉提升。\n- 理論貢獻：為期望理論與社會比較理論提供性別向度的實證。\n- 政策意涵：社會進步衡量需同時納入主觀福祉。",
    "limitations": "- 未明確說明因果機制，僅呈現實證相關。\n- 未來研究：應追蹤個體層次的世代資料以分離機制。",
    "raw_summary": "[Demo data]",
}


def main():
    print("Generating demo data...")

    # Save metadata
    meta_path = OUTPUT_DIR / "asr_metadata.json"
    meta_path.write_text(json.dumps(DEMO_ARTICLES, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {meta_path}")

    # Save one demo summary
    summary_dir = SUMMARY_DIR / "asr"
    summary_dir.mkdir(parents=True, exist_ok=True)

    doi_suffix = DEMO_SUMMARY["doi"].split("/")[-1]
    json_path = summary_dir / f"{doi_suffix}.json"
    json_path.write_text(json.dumps(DEMO_SUMMARY, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved: {json_path}")

    # Save markdown summary
    md_path = summary_dir / f"{doi_suffix}.md"
    md_content = f"""# {DEMO_SUMMARY['title']}

**Authors:** {', '.join(DEMO_SUMMARY['authors'])}
**Journal:** {DEMO_SUMMARY['journal']} | Vol. {DEMO_SUMMARY['volume']}, No. {DEMO_SUMMARY['issue']}
**DOI:** {DEMO_SUMMARY['doi']}
**Date:** {DEMO_SUMMARY['publication_date']}

---

## 1. 研究問題 (Research Question)

{DEMO_SUMMARY['research_question']}

## 2. 對話的理論脈絡 (Theoretical Context)

{DEMO_SUMMARY['theoretical_context']}

## 3. 理論架構 (Theoretical Framework)

{DEMO_SUMMARY['theoretical_framework']}

## 4. 資料來源 (Data Source)

{DEMO_SUMMARY['data_source']}

## 5. 研究模型與方法 (Model & Methodology)

{DEMO_SUMMARY['model_methodology']}

## 6. 模型結果 (Findings / Results)

{DEMO_SUMMARY['findings']}

## 7. 重要結論與貢獻 (Conclusion & Contribution)

{DEMO_SUMMARY['conclusion_contribution']}

## 8. 限制與未來研究 (Limitations & Future Research)

{DEMO_SUMMARY['limitations']}
"""
    md_path.write_text(md_content, encoding="utf-8")
    print(f"  Saved: {md_path}")

    # Create a dummy PDF dir
    pdf_dir = PDF_DIR / "asr"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    print("\nDone! Start the web UI with:")
    print("  python web/app.py")
    print("  Then open http://localhost:5000")


if __name__ == "__main__":
    main()
