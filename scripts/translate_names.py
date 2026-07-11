#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stocks_list.csv から日本語名辞書(NAME_JA)を生成し、
stocks.json の銘柄名とセクター名を日本語化する。"""
import csv
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE, "data", "stocks_list.csv")
JSON_PATH = os.path.join(BASE, "data", "stocks.json")

SECTOR_JA = {
    "Industrials": "資本財",
    "Consumer Cyclical": "一般消費財",
    "Consumer Defensive": "生活必需品",
    "Technology": "情報技術",
    "Basic Materials": "素材",
    "Financial Services": "金融",
    "Financial": "金融",
    "Healthcare": "ヘルスケア",
    "Energy": "エネルギー",
    "Real Estate": "不動産",
    "Utilities": "公益事業",
    "Communication Services": "通信サービス",
}


def build_name_ja():
    name_ja = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        for r in csv.reader(f):
            if not r or not r[0].strip():
                continue
            code = r[0].strip()
            if len(r) > 1 and r[1].strip():
                name_ja[code] = r[1].strip()
    return name_ja


def main():
    name_ja = build_name_ja()
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for s in data.get("stocks", []):
        code = s.get("code")
        if code in name_ja:
            s["name"] = name_ja[code]
        sec = s.get("sector") or ""
        s["sector"] = SECTOR_JA.get(sec, sec)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"日本語化完了: {len(name_ja)}銘柄の辞書を適用")


if __name__ == "__main__":
    main()
