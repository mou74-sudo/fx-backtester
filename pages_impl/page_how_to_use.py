import streamlit as st


def render() -> None:
    st.title("📖 How to Use This Tool")

    st.markdown("""
This guide walks you through everything step by step — no trading or coding experience needed.

---

## The idea in one sentence

You give it historical price data, tell it your trading rules, and it shows you
exactly how that strategy would have performed — and whether it's likely to keep working.

---

## Step 1 — Get your data (📥 Get Data tab)

The easiest option is to **fetch data directly** — no CSV needed:

1. Go to **📥 Get Data**
2. Select **Nasdaq 100 (NQ)** or **S&P 500 (ES)**
3. Choose your lookback window (e.g. 180 days)
4. Click **Fetch** — data downloads automatically via Yahoo Finance

Alternatively you can upload your own OHLC CSV with these columns:
```
timestamp, open, high, low, close
```

The **🤖 AI Pipeline** also fetches and analyses data automatically every 7 hours — check the **🏠 Home** tab to see the latest results.

---

## Step 2 — Run a backtest (🔬 Backtest tab)

A backtest simulates your strategy on historical data. Think of it as asking:
*"If I had followed these rules every day for the last 2 years, what would have happened?"*

**Settings explained:**

| Setting | What it does |
|---------|-------------|
| Strategy type | RSI = buy oversold, sell overbought. Breakout = trade when price breaks a recent high/low. |
| Trade direction | Long only = only buy. Short only = only sell. Both = buy and sell. |
| Stop loss | How many pips the market can move against you before you exit to limit the loss. |
| Take profit | How many pips of profit triggers an automatic exit. |
| Risk per trade | What % of your account you risk on each trade. 1% is standard. |
| Daily trend filter | If ticked, only buys when the daily chart is trending up, only sells when trending down. Reduces bad trades. |

**Reading the results:**
- **Net pips** — total pips made or lost across all trades
- **Win rate** — what % of trades were profitable
- **Expectancy** — average pips per trade. Positive = good. Negative = losing strategy.
- **Max drawdown** — the biggest peak-to-trough loss during the period (%)
- **Equity curve** — chart of your account balance over time. You want this going up-right.

---

## Step 3 — Check your stops and TPs (📊 MAE/MFE tab)

After running a backtest, go to this tab. It answers two questions:

**Are your stops too tight?**
If your winning trades regularly came within 2 pips of your stop before going your way,
your stop is probably too tight — a slightly wider stop would have kept you in those trades.

**Are your take-profits too small?**
If price went an average of 60 pips in your favour but your TP was only 30 pips,
you're leaving money on the table. The tool will tell you this in plain English.

---

## Step 4 — Find the best settings (🔍 Grid Search tab)

Instead of guessing whether RSI 14 is better than RSI 21, grid search tests them all
and shows you which combination produced the best results.

**How to use it safely:**
1. Set the data split to 70% in-sample / 30% out-of-sample
2. Choose 2–3 parameters to vary (e.g. RSI period + stop loss)
3. Run the search — it only optimises on the first 70% of your data
4. Click "Validate on out-of-sample" — this shows whether the best settings
   also worked on the 30% of data the search never saw
5. If OOS is also profitable → the edge is likely real
6. If OOS is terrible → the settings are curve-fitted (they only worked on that specific period)

> **Don't vary more than 3 parameters at once.** The more knobs you turn,
> the more likely you'll find settings that *look* great but are just
> random coincidence.

---

## Step 5 — Confirm the edge is real (🔄 Walk-Forward tab)

Walk-forward is a stricter version of the OOS test in step 4.
It splits your data into 5 (or more) separate time windows and asks:
*"Did this strategy work consistently across different market conditions?"*

A strategy that only worked in 2021 but not in 2022 or 2023 is not a real edge —
it just happened to fit one specific market regime.

**Reading the verdict:**
- 🟢 **VALIDATED** — worked in 60%+ of time windows AND total pips positive
- 🟡 **INCONCLUSIVE** — mixed results, needs more data or refinement
- 🔴 **FAILED** — didn't hold up. Don't trade this with real money.

---

## Step 6 — Study key levels (📍 Key Levels tab)

This tab doesn't backtest a strategy — instead it answers:
*"When price touches the previous day's high, how often does it bounce back vs break through?"*

**How to read the results:**

> **Previous Day High @ 1.10450**
> Touches: 31 | Reversed: 19 (61%) | Broke through: 12 (39%)
> Average move 5 bars after touch: -8.3 pips

This means: when NQ hits the previous day high, it rejects 61% of the time,
and when it rejects, price drops an average of 8.3 points over the next 5 candles.
That's useful information for where to set your entry and take-profit.

---

## Common mistakes to avoid

❌ **Don't run grid search on all your data** — you'll find "perfect" settings
   that only worked on that specific history.

❌ **Don't trade a strategy that only has 10–20 trades in the backtest** — too small
   a sample. You need at least 30–50 trades to draw any conclusion.

❌ **Don't ignore the walk-forward result** — a beautiful equity curve that fails
   walk-forward is a curve-fitted curve. It will lose money live.

❌ **Don't risk more than 1–2% per trade** — even a good strategy has losing streaks.
   At 1% risk, you can lose 20 trades in a row and still have 82% of your account.

---

## Quick reference — what each tab does

| Tab | One sentence |
|-----|-------------|
| 📥 Get Data | Fetch NQ/ES data or upload your own CSV |
| 🔬 Backtest | Run your strategy and see the equity curve |
| 📊 MAE/MFE | Check if stops and TPs are correctly sized |
| 🔍 Grid Search | Find the best settings for your strategy |
| 🔄 Walk-Forward | Confirm the edge holds across different time periods |
| 📍 Key Levels | See how price reacts at daily/weekly/session highs and lows |

---

*Built with real data. Always paper trade before using real money.*
""")
