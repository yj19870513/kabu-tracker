#!/usr/bin/env python3
"""配当履歴・出典データの機械チェック。

判定を自動で青・緑・赤へ変更するスクリプトではありません。
入力データの欠落や、明らかな形式不整合を検出して推測判定を防ぎます。
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    with (ROOT / "data" / name).open(encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="結果をJSONで出力")
    args = parser.parse_args()

    stocks = load("stocks.json")
    sources = load("dividend_sources.json")
    adjusted = load("dividend_history_adjusted.json")
    overrides = load("dividend_audit_overrides.json")
    sources.update(overrides.get("sources", {}))
    adjusted.update(overrides.get("adjusted", {}))
    stock_rows = stocks.get("stocks", stocks) if isinstance(stocks, dict) else stocks
    stock_by_code = {str(row.get("code")): row for row in stock_rows if isinstance(row, dict)}
    for code, patch in overrides.get("stocks", {}).items():
        if code in stock_by_code:
            stock_by_code[code].update(patch)
    stock_codes = {str(row.get("code")) for row in stock_rows if isinstance(row, dict)}
    errors, warnings = [], []
    legacy_conflicts = []
    consistency_conflicts = []
    source_codes = set(sources)

    for code, item in sources.items():
        if code not in stock_codes:
            errors.append(f"出典コード {code} がstocks.jsonにありません")
        if not isinstance(item, dict):
            errors.append(f"{code}: 出典データがオブジェクトではありません")
            continue
        urls = item.get("sources", [])
        if item.get("status") == "reviewed" and not urls:
            warnings.append(f"{code}: reviewed ですが出典リンクがありません")
        for source in urls:
            url = str(source.get("url", "")) if isinstance(source, dict) else ""
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors.append(f"{code}: URL形式が不正です: {url}")

    for code, item in adjusted.items():
        history = item.get("history", {}) if isinstance(item, dict) else {}
        years = []
        for year, value in history.items():
            try:
                year_num, value_num = int(str(year)[:4]), float(value)
                if value_num < 0:
                    raise ValueError
                years.append(year_num)
            except (TypeError, ValueError):
                errors.append(f"{code}: 配当履歴の値が不正です: {year}={value}")
        if len(years) < 2:
            warnings.append(f"{code}: グラフ比較用の履歴が2年未満です")
        years.sort()
        source_item_for_gap = sources.get(str(code)) if isinstance(sources, dict) else None
        gaps = [f"{a}〜{b}" for a, b in zip(years, years[1:]) if b - a > 1]
        if gaps and not (isinstance(source_item_for_gap, dict) and source_item_for_gap.get("history")):
            warnings.append(f"{code}: 年度の空白があります（{', '.join(gaps)}）")
        drops = item.get("remaining_drops", [])
        if item.get("status") in ("blue_ok", "reviewed") and drops:
            warnings.append(f"{code}: 青系ステータスですがremaining_dropsが残っています")

        row = stock_by_code.get(code)
        # 出典側に確認済みの数値履歴がある銘柄は、stocks.jsonや旧調整履歴を
        # 正本として比較しない。旧履歴を混ぜると、分割前後の額面が混在する。
        source_item = sources.get(code) if isinstance(sources.get(code), dict) else {}
        source_history = source_item.get("history", {})
        if source_history and history:
            mismatches = []
            for year in set(source_history) & set(history):
                try:
                    if abs(float(source_history[year]) - float(history[year])) > 0.01:
                        mismatches.append(str(year))
                except (TypeError, ValueError):
                    mismatches.append(str(year))
            if mismatches:
                legacy_conflicts.append(
                    f"{code}: 旧調整履歴と出典正本が不一致（{len(mismatches)}年度）。表示・判定は出典正本を使用"
                )
        elif not source_history and source_item.get("confirmed_real_cuts") is not None and history:
            pairs = sorted(
                (int(str(year)[:4]), float(value))
                for year, value in history.items()
                if int(str(year)[:4]) < 2026
            )
            computed = sum(1 for (_, before), (_, after) in zip(pairs, pairs[1:]) if after < before - 0.01)
            declared = int(source_item["confirmed_real_cuts"])
            if computed != declared:
                consistency_conflicts.append(
                    f"{code}: グラフ履歴の減少{computed}回と確認メモ{declared}回が不一致。判定保留"
                )
        if row and history and not source_history:
            stored_history = row.get("div_by_year") or {}
            for year, adjusted_value in history.items():
                if year not in stored_history:
                    errors.append(f"{code}: stocks.jsonに調整履歴{year}がありません")
                    continue
                try:
                    stored_value = float(stored_history[year])
                    canonical_value = float(adjusted_value)
                    if abs(stored_value - canonical_value) > 0.01:
                        legacy_conflicts.append(
                            f"{code}: stocks.jsonの旧配当と調整履歴が{year}年で不一致。調整履歴を優先"
                        )
                except (TypeError, ValueError):
                    errors.append(f"{code}: stocks.jsonの{year}年配当が不正です")
        if row and row.get("dividend") and history:
            latest_meta = item.get("actual_latest") if isinstance(item, dict) else None
            if isinstance(latest_meta, dict) and latest_meta.get("value") is not None:
                latest_adjusted = float(latest_meta["value"])
            else:
                latest_year = max(history, key=lambda y: int(str(y)[:4]))
                latest_adjusted = float(history[latest_year])
            raw = float(row["dividend"])
            if latest_adjusted > 0 and (raw / latest_adjusted < 0.5 or raw / latest_adjusted > 2.0):
                warnings.append(
                    f"{code}: stocks.jsonのYahoo配当{raw:g}円と調整履歴{latest_adjusted:g}円が不一致"
                )

    # 出典正本そのものの減配回数は、メタデータと必ず一致させる。
    # 一致しない場合は「減配なし」に進めず、データ修正を要求する。
    for code, item in sources.items():
        if not isinstance(item, dict) or not item.get("history"):
            continue
        pairs = sorted(
            (int(str(year)[:4]), float(value))
            for year, value in item["history"].items()
            if int(str(year)[:4]) < 2026
        )
        computed = sum(1 for (_, before), (_, after) in zip(pairs, pairs[1:]) if after < before - 0.01)
        declared = item.get("confirmed_real_cuts")
        if declared is not None and int(declared) != computed:
            errors.append(f"{code}: 出典正本の減配回数 {computed} とメタデータ {declared} が不一致")

    missing = sorted(stock_codes - source_codes)
    result = {
        "stocks": len(stock_codes),
        "sources": len(source_codes),
        "adjusted": len(adjusted),
        "missing_sources": missing,
        "errors": errors,
        "warnings": warnings,
        "legacy_conflicts": legacy_conflicts,
        "consistency_conflicts": consistency_conflicts,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"銘柄 {result['stocks']} / 出典 {result['sources']} / 調整履歴 {result['adjusted']}")
        print(f"出典未登録: {len(missing)}銘柄")
        print(f"エラー: {len(errors)}件 / 警告: {len(warnings)}件")
        print(f"旧履歴との不一致（出典正本を優先）: {len(legacy_conflicts)}件")
        print(f"判定保留が必要な履歴矛盾: {len(consistency_conflicts)}件")
        for line in errors:
            print(f"ERROR: {line}")
        for line in warnings[:30]:
            print(f"WARN: {line}")
        if len(warnings) > 30:
            print(f"WARN: …ほか{len(warnings) - 30}件")
        for line in legacy_conflicts[:10]:
            print(f"INFO: {line}")
        if len(legacy_conflicts) > 10:
            print(f"INFO: …ほか{len(legacy_conflicts) - 10}件")
        for line in consistency_conflicts:
            print(f"BLOCK: {line}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
