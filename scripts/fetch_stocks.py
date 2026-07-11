#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日本株 高配当トラッカー データ取得スクリプト
data/stocks_list.csv の銘柄を yfinance で取得し data/stocks.json に保存する。
"""
import csv
import json
import os
import time
from datetime import datetime, timezone, timedelta

import yfinance as yf

JST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE, "data", "stocks_list.csv")
OUT_PATH = os.path.join(BASE, "data", "stocks.json")


def load_list():
    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        for r in csv.reader(f):
            if not r or not r[0].strip():
                continue
            code = r[0].strip()
            name = r[1].strip() if len(r) > 1 else code
            rows.append((code, name))
    return rows


def num(v):
    """floatにできない値はNoneに"""
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def rnd(v, n=2):
    v = num(v)
    return round(v, n) if v is not None else None


def series_by_year(df, row_label):
    """財務諸表DataFrameから {year: value} リスト（古い順）を返す"""
    out = []
    try:
        if df is None or df.empty or row_label not in df.index:
            return out
        s = df.loc[row_label]
        for col, val in s.items():
            v = num(val)
            if v is None:
                continue
            out.append({"year": str(getattr(col, "year", col))[:4], "value": v})
        out.sort(key=lambda x: x["year"])
    except Exception:
        pass
    return out


def fetch_one(code):
    d = {"code": code, "error": False}
    try:
        t = yf.Ticker(f"{code}.T")
        try:
            info = t.info or {}
        except Exception:
            info = {}

        # --- 価格系 ---
        closes = []
        try:
            h = t.history(period="4mo")["Close"].dropna()
            closes = [round(float(x), 2) for x in h.tolist()]
        except Exception:
            pass
        price = num(info.get("currentPrice")) or num(info.get("regularMarketPrice"))
        if price is None and closes:
            price = closes[-1]
        prev = num(info.get("previousClose"))
        if prev is None and len(closes) >= 2:
            prev = closes[-2]
        d["price"] = rnd(price)
        d["prev_close"] = rnd(prev)
        d["change_pct"] = rnd((price / prev - 1) * 100) if price and prev else None

        # --- 配当 ---
        div_rate = num(info.get("dividendRate")) or num(info.get("trailingAnnualDividendRate"))
        d["dividend"] = rnd(div_rate)
        if div_rate and price:
            d["yield_pct"] = rnd(div_rate / price * 100)
        else:
            y = num(info.get("dividendYield"))
            # yfinanceのバージョンにより割合(0.042)か%表記(4.2)かが揺れるため補正
            if y is not None and y < 0.5:
                y *= 100
            d["yield_pct"] = rnd(y)

        # --- 基本情報 ---
        d["name_en"] = info.get("shortName") or info.get("longName") or code
        d["sector"] = info.get("sector") or ""
        d["market_cap"] = num(info.get("marketCap"))

        # --- バリュー ---
        d["per"] = rnd(info.get("trailingPE"))
        d["pbr"] = rnd(info.get("priceToBook"))

        # --- 財務 ---
        op = num(info.get("operatingMargins"))
        d["op_margin"] = rnd(op * 100) if op is not None else None
        po = num(info.get("payoutRatio"))
        d["payout"] = rnd(po * 100) if po is not None else None
        roe = num(info.get("returnOnEquity"))
        d["roe"] = rnd(roe * 100) if roe is not None else None

        try:
            bs = t.balance_sheet
        except Exception:
            bs = None
        equity = series_by_year(bs, "Stockholders Equity")
        assets = series_by_year(bs, "Total Assets")
        if equity and assets and num(assets[-1]["value"]):
            d["equity_ratio"] = rnd(equity[-1]["value"] / assets[-1]["value"] * 100)
        else:
            d["equity_ratio"] = None
        d["cash_hist"] = series_by_year(bs, "Cash And Cash Equivalents")

        try:
            inc = t.income_stmt
        except Exception:
            inc = None
        d["revenue_hist"] = series_by_year(inc, "Total Revenue")
        d["eps_hist"] = series_by_year(inc, "Diluted EPS") or series_by_year(inc, "Basic EPS")

        try:
            cf = t.cashflow
        except Exception:
            cf = None
        ocf = series_by_year(cf, "Operating Cash Flow")
        d["op_cf"] = ocf[-1]["value"] if ocf else None

        # --- 配当履歴 ---
        div_hist = []
        div_by_year = {}
        try:
            divs = t.dividends
            for k, v in divs.items():
                y = str(k.year)
                div_by_year[y] = round(div_by_year.get(y, 0) + float(v), 2)
            for k, v in list(divs.items())[-12:]:
                div_hist.append({"date": str(k.date()), "amount": round(float(v), 2)})
        except Exception:
            pass
        d["div_hist"] = div_hist
        d["div_by_year"] = div_by_year

        # --- テクニカル ---
        d["high52"] = rnd(info.get("fiftyTwoWeekHigh"))
        d["low52"] = rnd(info.get("fiftyTwoWeekLow"))
        d["ma25"] = rnd(sum(closes[-25:]) / 25) if len(closes) >= 25 else None
        d["ma75"] = rnd(sum(closes[-75:]) / 75) if len(closes) >= 75 else None

        if d["price"] is None:
            d["error"] = True
    except Exception as e:
        d["error"] = True
        d["error_msg"] = str(e)[:200]
    return d


def fetch_vix():
    try:
        h = yf.Ticker("^VIX").history(period="5d")["Close"].dropna()
        if len(h):
            return round(float(h.iloc[-1]), 2)
    except Exception:
        pass
    return None


def main():
    stocks = []
    for code, name in load_list():
        print(f"取得中: {code} {name}")
        s = fetch_one(code)
        s["name"] = name  # 日本語名はCSVが正。translate_names.pyでも上書きされる
        stocks.append(s)
        time.sleep(1)  # API負荷対策

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    vix = fetch_vix()
    out = {
        "updated": now,
        "vix": vix,
        "vix_updated": now if vix is not None else None,
        "stocks": stocks,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    ok = sum(1 for s in stocks if not s["error"])
    print(f"完了: {ok}/{len(stocks)}件成功 / VIX={vix} / -> {OUT_PATH}")


if __name__ == "__main__":
    main()
