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
    "research_question": "為什麼在過去35年間，美國女性在客觀生活條件（教育、就業、薪資）明顯改善的情況下，主觀幸福感卻出現下降？女性幸福感的下降是絕對性的，還是相對於男性而言的？這種趨勢是否跨越不同年齡、種族、教育程度和婚姻狀態的群體？",
    "theoretical_framework": "本文建立在主觀幸福感（subjective well-being）研究的基礎上，結合了 Easterlin 的「幸福悖論」概念。理論上探討了三種可能的解釋路徑：(1) 女性運動提高了期望值，導致期望與現實的落差擴大；(2) 工作與家庭的雙重負擔（second shift）假說；(3) 社會比較對象的變化——女性不再只與其他女性比較，而是開始與男性比較。",
    "data": "使用美國 General Social Survey (GSS) 1972-2006 年的資料，以及歐洲 Eurobarometer 1975-2006 年的跨國調查資料。GSS 樣本涵蓋超過 50,000 名受訪者，Eurobarometer 涵蓋歐盟各國。主要依變項為自評幸福感（happiness）的三點量表。",
    "methods": "採用有序 probit 迴歸模型（ordered probit），控制年齡、教育、收入、婚姻狀態、種族、子女數等變項。進行次群體分析以檢驗趨勢的穩健性。使用跨國比較作為外部效度驗證。以世代分析（cohort analysis）區分年齡效應與世代效應。",
    "key_findings": "1. 1970年代以來，美國女性的主觀幸福感持續下降，無論絕對值或相對於男性。\n2. 這一趨勢在不同年齡、種族、教育程度和婚姻狀態的女性群體中都成立。\n3. 歐洲資料也呈現類似的趨勢，排除了純粹美國特殊性的解釋。\n4. 1970年代女性的幸福感高於男性，但到2000年代已低於男性（性別幸福感差距逆轉）。\n5. 客觀指標的改善與主觀幸福感的下降形成鮮明對比。",
    "contribution": "本文提出了一個重要的經驗事實挑戰：社會進步（尤其是性別平等的推進）不必然帶來主觀福祉的提升。這對公共政策的意涵在於，不能僅依靠客觀指標衡量社會進步，需要同時關注主觀幸福感。理論上，本文為「期望理論」（aspiration theory）和社會比較理論在性別研究中的應用提供了實證基礎。",
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

## 2. 理論框架 (Theoretical Framework)

{DEMO_SUMMARY['theoretical_framework']}

## 3. 資料來源 (Data)

{DEMO_SUMMARY['data']}

## 4. 研究方法 (Methods)

{DEMO_SUMMARY['methods']}

## 5. 主要發現 (Key Findings)

{DEMO_SUMMARY['key_findings']}

## 6. 學術貢獻 (Contribution)

{DEMO_SUMMARY['contribution']}
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
