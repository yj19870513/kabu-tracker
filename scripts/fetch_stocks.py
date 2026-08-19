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
    """floatにできない値・NaN・無限大はNoneに。
    Infinityが混ざるとJSONとして不正になり、ブラウザ側で読み込みに失敗するため必ず除外する。"""
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        if f in (float("inf"), float("-inf")):
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


def compute_historical_averages(ticker, div_by_year, eps_hist, equity_hist, shares_outstanding):
    """過去10年の年平均株価から、年ごとの利回り・PER・PBRを逆算し平均する。
    学長マガジンの「買い時判定＝絶対水準ではなく自分自身の過去平均との比較」に対応するため。
    株価は暦年平均で近似（正確な決算期とはズレる）。shares_outstandingは現在値で過去も一定と仮定する近似。"""
    out = {"avg_yield": None, "avg_per": None, "avg_pbr": None, "years_used": 0}
    try:
        h = ticker.history(period="10y")["Close"].dropna()
        if h.empty:
            return out
        by_year_price = {}
        for idx, val in h.items():
            y = str(idx.year)
            by_year_price.setdefault(y, []).append(float(val))
        avg_price = {y: sum(v) / len(v) for y, v in by_year_price.items()}

        eps_by_year = {e["year"]: e["value"] for e in eps_hist}
        equity_by_year = {e["year"]: e["value"] for e in equity_hist}

        this_year = str(datetime.now(JST).year)
        years = sorted([y for y in avg_price if y != this_year])[-10:]  # 進行中の年は除外、直近10年

        yields, pers, pbrs = [], [], []
        for y in years:
            p = avg_price.get(y)
            if not p:
                continue
            if y in div_by_year and div_by_year[y] > 0:
                yields.append(div_by_year[y] / p * 100)
            if y in eps_by_year and eps_by_year[y] > 0:
                pers.append(p / eps_by_year[y])
            if y in equity_by_year and shares_outstanding:
                bps = equity_by_year[y] / shares_outstanding
                if bps > 0:
                    pbrs.append(p / bps)

        out["avg_yield"] = rnd(sum(yields) / len(yields)) if yields else None
        out["avg_per"] = rnd(sum(pers) / len(pers)) if pers else None
        out["avg_pbr"] = rnd(sum(pbrs) / len(pbrs)) if pbrs else None
        out["years_used"] = len(years)
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

        # --- 配当履歴（過去平均計算にも使うため先に取得） ---
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
        # 進行中の年を除いた「確定済み」配当履歴（トレンド判定・変動計算はこちらを使う）
        this_year = str(datetime.now(JST).year)
        d["div_confirmed"] = {y: v for y, v in div_by_year.items() if y != this_year}

        # --- 配当 ---
        # dividendRateはYahoo Finance側のスナップショット値で、直近1回分だけを
        # 返すなどの不整合があるため、確定済みの年度履歴を優先する。
        div_rate = num(info.get("dividendRate")) or num(info.get("trailingAnnualDividendRate"))
        d["dividend_raw_yahoo"] = rnd(div_rate)
        conf = d.get("div_confirmed") or {}
        conf_years = sorted(conf)
        latest_annual = num(conf[conf_years[-1]]) if conf_years else None
        if latest_annual is not None and latest_annual > 0:
            d["dividend"] = rnd(latest_annual)
            d["dividend_source"] = "配当履歴（年度集計）"
            d["yield_pct"] = rnd(latest_annual / price * 100) if price else None
        else:
            d["dividend"] = rnd(div_rate)
            d["dividend_source"] = "Yahoo Finance参考値" if div_rate else "未確認"
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
        equity_hist = series_by_year(bs, "Stockholders Equity")
        assets = series_by_year(bs, "Total Assets")
        if equity_hist and assets and num(assets[-1]["value"]):
            d["equity_ratio"] = rnd(equity_hist[-1]["value"] / assets[-1]["value"] * 100)
        else:
            d["equity_ratio"] = None
        d["equity_hist"] = equity_hist
        cash_hist = series_by_year(bs, "Cash And Cash Equivalents")
        d["cash_hist"] = cash_hist
        debt_hist = series_by_year(bs, "Total Debt")
        d["debt_hist"] = debt_hist

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
        ocf_hist = series_by_year(cf, "Operating Cash Flow")
        d["op_cf"] = ocf_hist[-1]["value"] if ocf_hist else None
        d["op_cf_hist"] = ocf_hist

        d["shares_outstanding"] = num(info.get("sharesOutstanding"))

        # --- 配当余力（ネットキャッシュ÷1株配当＝配当何年分の余力か） ---
        # ネットキャッシュ＝現金等－有利子負債。「確かめたい4つのこと」記事の指標⑤に対応。
        d["div_capacity_years"] = None
        if cash_hist and d.get("shares_outstanding") and d.get("dividend"):
            latest_cash = cash_hist[-1]["value"]
            latest_debt = debt_hist[-1]["value"] if debt_hist else 0
            net_cash_per_share = (latest_cash - latest_debt) / d["shares_outstanding"]
            if d["dividend"] > 0:
                d["div_capacity_years"] = rnd(net_cash_per_share / d["dividend"])

        # --- テクニカル ---
        d["high52"] = rnd(info.get("fiftyTwoWeekHigh"))
        d["low52"] = rnd(info.get("fiftyTwoWeekLow"))
        d["ma25"] = rnd(sum(closes[-25:]) / 25) if len(closes) >= 25 else None
        d["ma75"] = rnd(sum(closes[-75:]) / 75) if len(closes) >= 75 else None

        # --- 配当データの整合性チェック ---
        # yfinanceのdividendRateが直近1回分だけを拾うなど、直近の年間実績と大きく食い違う場合に警告する
        d["div_warning"] = None
        conf = d.get("div_confirmed") or {}
        if conf and d.get("dividend_raw_yahoo"):
            latest_year = max(conf)
            latest_annual = conf[latest_year]
            if latest_annual > 0:
                ratio = d["dividend_raw_yahoo"] / latest_annual
                if ratio < 0.5 or ratio > 2.0:
                    d["div_warning"] = (
                        f"Yahoo参考値{d['dividend_raw_yahoo']}円は{latest_year}年の実績{latest_annual}円と大きく異なります。"
                        "株式分割やデータ不備の可能性があるため、証券会社の情報で必ず確認してください。"
                    )

        # --- 過去10年平均（買い時判定用：現在値との比較に使う） ---
        avg = compute_historical_averages(t, div_by_year, d["eps_hist"], equity_hist, d["shares_outstanding"])
        d["avg_yield_10y"] = avg["avg_yield"]
        d["avg_per_10y"] = avg["avg_per"]
        d["avg_pbr_10y"] = avg["avg_pbr"]
        d["hist_years_used"] = avg["years_used"]

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
