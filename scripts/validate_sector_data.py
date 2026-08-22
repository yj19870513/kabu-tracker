#!/usr/bin/env python3
"""業種分類の公開前監査。

Yahoo Finance の大分類を東証33業種として混入させないため、
stocks.json と公式分類マスターのコード・業種を毎回照合する。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stocks = json.loads((ROOT / "data" / "stocks.json").read_text(encoding="utf-8"))
stocks = stocks.get("stocks", stocks) if isinstance(stocks, dict) else stocks
master = json.loads((ROOT / "data" / "sector_classification.json").read_text(encoding="utf-8"))
mapping = master.get("sectors", {})

tse33 = {
    "水産・農林業","建設業","不動産業","非鉄金属","鉱業","サービス業","機械","金属製品",
    "情報・通信業","食料品","医薬品","陸運業","その他金融業","小売業","卸売業","化学",
    "繊維製品","電気機器","ガラス・土石製品","証券、商品先物取引業","輸送用機器","石油・石炭製品",
    "パルプ・紙","精密機器","ゴム製品","鉄鋼","銀行業","保険業","その他製品","倉庫・運輸関連業",
    "海運業","空運業","電気・ガス業"
}
extras = {"ETF・他", "米国ETF", "米国個別株"}
old_yahoo = {"資本財","情報技術","一般消費財","生活必需品","通信サービス","ヘルスケア","金融","不動産","素材","公益事業","エネルギー"}

codes = [str(s.get("code")) for s in stocks]
errors = []
if len(codes) != len(set(codes)):
    errors.append("stocks.json に重複コードがあります")
if set(codes) != set(mapping):
    errors.append(f"コード対応不足: stocks={len(set(codes))}, master={len(set(mapping))}")
for code, sector in mapping.items():
    if sector in old_yahoo:
        errors.append(f"{code}: Yahoo大分類が混入しています: {sector}")
    elif sector not in tse33 | extras:
        errors.append(f"{code}: 許可されていない業種: {sector}")

print(f"銘柄数: {len(codes)} / マスター: {len(mapping)}")
print(f"業種: {len(set(mapping.values()))}分類")
if errors:
    print("ERROR")
    print("\n".join(f"- {e}" for e in errors))
    raise SystemExit(1)
print("OK: 全コードが正本マスターにあり、旧Yahoo大分類はありません")
