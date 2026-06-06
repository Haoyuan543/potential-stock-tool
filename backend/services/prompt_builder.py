from __future__ import annotations

import json
from typing import Any


def build_analysis_prompt(payload: dict[str, Any], profile: dict[str, Any] | None = None) -> str:
    """Build a clean Traditional Chinese investment-report prompt."""

    mode = payload["mode"]
    profile_text = json.dumps(profile, ensure_ascii=False, indent=2) if profile else "General Mode：不可讀取或推測使用者持股。"
    context = {
        "symbol": payload.get("symbol"),
        "mode": mode,
        "data_freshness": payload.get("data_freshness", {}),
        "summary": payload.get("summary", {}),
        "action_plan": payload.get("action_plan", {}),
        "position_advice": payload.get("position_advice", {}),
        "truthfulness": payload.get("truthfulness", {}),
        "market_data": payload.get("market_data", {}),
        "local_scores": payload.get("local_scores", {}),
        "missing": payload.get("missing", []),
        "sources": payload.get("sources", []),
    }

    return f"""
你是繁體中文的 AI 投資研究員，請根據下方資料產生「給投資人看的」股票分析報告。

重要規則：
- 只使用繁體中文；必要英文術語請放括號，例如「資料可信度（Truthfulness）」。
- 不要輸出程式碼、命令列、JSON、檔名、API 欄位名、資料庫欄位名或工程除錯文字。
- 不要使用 `Data Missing`、`jsonl`、`python -m`、`exact_data`、`search_inferred` 這類工程語言。
- 若資料缺漏，請改寫成投資人看得懂的中文，例如「資料不足：ETF 實際持股變化尚未取得」。
- 不可把缺漏資料當作中性，也不可把搜尋推論當成官方精確數字。
- 若整體分數不足、短線時機不好或風險偏高，結論必須保守，不能寫強烈偏多。
- 報告要簡潔、有層次，不要重複同一段內容。

報告格式：

# 即時 AI 投資分析報告

## 1. 一分鐘結論
用 6 到 8 行列出：
- 今日結論
- 今日動作
- 可買位置
- 可賣位置
- 主要風險
- 需要再確認的資料

## 2. 操作建議
- 現在是否適合買
- 現在是否適合賣
- 若漲到關鍵價位
- 若跌到關鍵價位
- 改變看法的條件

Personalized Mode 時，必須加入：
## 3. 對我目前部位的建議
- 持股張數
- 均價
- 目前損益
- 核心部位
- 機動部位
- 今日是否建議賣
- 建議賣出張數

## 4. 支撐與壓力
## 5. 運價與航運景氣
## 6. 法人與籌碼
## 7. 基本面與股利
## 8. 新聞與事件風險
## 9. 多空辯論
## 10. 資料可信度與限制
## 11. 免責聲明

User profile:
{profile_text}

Context:
{json.dumps(context, ensure_ascii=False, indent=2)}
"""
