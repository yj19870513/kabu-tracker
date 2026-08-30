#!/usr/bin/env python3
"""公開前チェック：ローカルのdata/*が公開中(GitHub Pages)より件数が減っていないか確認する。

過去に「115銘柄の生成結果で157銘柄を置換しようとした」事故があったため、
アップロード前に必ずこのスクリプトを実行し、既存データを減らす変更でないことを確認する。
ネットワークに繋がらない場合は、その旨を表示してローカルの件数だけ表示する。
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_BASE = "https://yj19870513.github.io/kabu-tracker/data/"

# ファイルごとに「1件」を識別するキー集合を取り出す関数。
# Noneを返すファイルは件数比較の対象外（バイト数だけ参考表示）。


def codes_from_stocks_json(d):
    rows = d.get("stocks", d) if isinstance(d, dict) else d
    return {str(r.get("code")) for r in rows if isinstance(r, dict) and r.get("code")}


def codes_from_flat_dict(d):
    if not isinstance(d, dict):
        return None
    return {k for k in d.keys() if str(k).isdigit()}


def codes_from_financial8(d):
    if not isinstance(d, dict):
        return None
    stocks = d.get("stocks")
    if not isinstance(stocks, dict):
        return None
    return set(stocks.keys())


def codes_from_sector(d):
    if not isinstance(d, dict):
        return None
    sectors = d.get("sectors")
    if not isinstance(sectors, dict):
        return None
    return set(sectors.keys())


FILES = {
    "stocks.json": codes_from_stocks_json,
    "dividend_sources.json": codes_from_flat_dict,
    "dividend_history_adjusted.json": codes_from_flat_dict,
    "dividend_verified.json": codes_from_flat_dict,
    "financial8_verified.json": codes_from_financial8,
    "sector_classification.json": codes_from_sector,
    "dividend_audit_overrides.json": None,
    "gakucho_intro_stocks.json": None,
    "stocks_list.csv": None,
}


def fetch_published(name):
    url = PUBLISHED_BASE + name
    with urllib.request.urlopen(url, timeout=15) as resp:
        raw = resp.read()
    if name.endswith(".json"):
        return json.loads(raw)
    return raw.decode("utf-8")


def load_local(name):
    path = ROOT / "data" / name
    raw = path.read_text(encoding="utf-8")
    if name.endswith(".json"):
        return json.loads(raw)
    return raw


def main():
    problems = []
    network_ok = True
    print("=== 公開前チェック（ローカル vs 公開中データ） ===")
    for name, extractor in FILES.items():
        local_path = ROOT / "data" / name
        if not local_path.exists():
            continue
        local_raw = load_local(name)

        try:
            remote_raw = fetch_published(name)
        except Exception as e:  # noqa: BLE001
            network_ok = False
            print(f"- {name}: 公開版を取得できませんでした（{e}）。ローカルのみ表示")
            continue

        if extractor is None:
            local_size = len(json.dumps(local_raw, ensure_ascii=False)) if name.endswith(".json") else len(local_raw)
            remote_size = len(json.dumps(remote_raw, ensure_ascii=False)) if name.endswith(".json") else len(remote_raw)
            same = "同一" if local_raw == remote_raw else ("差分あり" if local_size >= remote_size * 0.9 else "要確認")
            print(f"- {name}: {same}（構造比較なし。文字数 ローカル{local_size} / 公開{remote_size}）")
            continue

        local_codes = extractor(local_raw)
        remote_codes = extractor(remote_raw)
        if local_codes is None or remote_codes is None:
            print(f"- {name}: 構造を認識できず件数比較をスキップしました")
            continue

        missing = sorted(remote_codes - local_codes)
        added = sorted(local_codes - remote_codes)
        status = "OK"
        if missing:
            status = "危険：件数減少"
            problems.append(f"{name}: 公開版にあってローカルに無いコード {missing}")
        print(
            f"- {name}: ローカル{len(local_codes)}件 / 公開{len(remote_codes)}件"
            f"（新規{len(added)}件, 消失{len(missing)}件）… {status}"
        )
        if missing:
            print(f"    消失コード: {missing}")

    print()
    if not network_ok:
        print("一部ファイルはネットワーク不調のため未確認です。再実行してください。")
    if problems:
        print("停止：以下のファイルは公開版よりデータが減っています。アップロードしないでください。")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("問題なし：公開しても既存データが減る変更はありません。")


if __name__ == "__main__":
    main()
