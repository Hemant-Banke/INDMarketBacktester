/** Hover explanations for metric labels, keyed by the label as shown. */
export const TIPS: Record<string, string> = {
  // headline and risk / return
  'CAGR': 'Compound annual growth rate: the constant yearly return that turns the starting value into the final value over the period.',
  'Total return': 'Change in value from the first to the last day, after costs.',
  'Volatility': 'Standard deviation of daily returns, annualised (× √252). How much returns swing around their average.',
  'Volatility (annual)': 'Standard deviation of daily returns, annualised (× √252). How much returns swing around their average.',
  'Sharpe': 'Average daily return above the 6.5% risk-free rate, divided by the standard deviation of daily returns, annualised. Return per unit of total risk.',
  'Sharpe (rf 6.5%)': 'Average daily return above the 6.5% risk-free rate, divided by the standard deviation of daily returns, annualised. Return per unit of total risk.',
  'Sortino': 'Like Sharpe, but divides by the volatility of losing days only, so upside swings are not penalised.',
  'Calmar': 'CAGR divided by the size of the maximum drawdown. Return per unit of worst loss.',
  'Max drawdown': 'Largest fall from a previous peak to a later low.',
  'Longest drawdown (sessions)': 'Most trading sessions spent in a row below a previous peak.',
  'Best day': 'Largest one-day gain.',
  'Worst day': 'Largest one-day loss.',
  'Best month': 'Largest calendar-month gain.',
  'Worst month': 'Largest calendar-month loss.',
  'Positive months': 'Share of calendar months that ended with a gain.',
  'Daily VaR 95%': 'Value at risk: on 95% of days the loss was smaller than this. Taken from the actual daily returns.',
  'Daily CVaR 95%': 'Conditional value at risk: the average loss on the worst 5% of days.',
  'Skew': 'Asymmetry of daily returns. Negative means occasional large losses; positive means occasional large gains.',
  'Excess kurtosis': 'How fat the tails of daily returns are compared with a normal distribution. Above 0 means extreme days happen more often than a bell curve suggests.',

  // versus benchmark
  'Alpha (annual, CAPM)': 'Annual return not explained by exposure to the benchmark: strategy excess return minus beta × benchmark excess return, both above the 6.5% risk-free rate.',
  'Beta': 'How much the strategy moves with the benchmark. 1 moves one-for-one; 0.5 moves half as much; based on daily returns.',
  'Correlation': 'How closely daily returns move together with the benchmark, from −1 to 1.',
  'Tracking error': 'Annualised volatility of the daily difference between strategy and benchmark returns.',
  'Information ratio': 'Average annual outperformance divided by tracking error. Outperformance per unit of deviation from the benchmark.',
  'Up-market capture': 'In months the benchmark rose: the strategy’s average return as a share of the benchmark’s. Above 100% means it gained more.',
  'Down-market capture': 'In months the benchmark fell: the strategy’s average return as a share of the benchmark’s. Below 100% means it lost less.',
  'Months beating benchmark': 'Share of calendar months in which the strategy returned more than the benchmark.',

  // portfolio
  'Final equity': 'Cash plus the market value of holdings on the last day.',
  'Costs paid': 'All brokerage, taxes, exchange and depository charges paid. Slippage is not included here; it is already in the fill prices.',
  'Annual turnover': 'Value traded per year (buys and sells averaged) as a share of average equity. 100% means the portfolio is replaced about once a year.',
  'Average invested': 'Average share of equity held in stocks rather than cash.',
  'Average holdings': 'Average number of open positions per session.',
  'Orders filled': 'Number of buy and sell fills, including partial ones.',

  // trade statistics
  'Closed round trips': 'Completed buy-then-sell trades. A position sold in parts counts once per part, matched to buys first-in, first-out.',
  'Win rate': 'Share of closed round trips with a profit after costs.',
  'Average win': 'Average return of profitable round trips.',
  'Average loss': 'Average return of losing round trips.',
  'Profit factor': 'Total profit of winning round trips divided by total loss of losing ones. Above 1 means winners outweigh losers.',
  'Median holding': 'Median number of trading sessions between buying and selling.',
  'Best trade': 'Highest return of a single round trip.',
  'Worst trade': 'Lowest return of a single round trip.',

  // table columns
  'Days ahead': 'Share of sessions in this regime when the strategy’s daily return beat the benchmark’s. 50% is a coin flip; it counts days, not the size of the gains.',
  'Time': 'Share of the backtest spent in this regime.',
  'Strategy ann.': 'Strategy’s average daily return in this regime, annualised (× 252).',
  'Bench ann.': 'Benchmark’s average daily return in this regime, annualised (× 252).',
  'Strategy vol': 'Strategy’s daily volatility in this regime, annualised.',
  'Strategy max DD': 'Largest peak-to-low fall of the strategy within the episode.',
  'Bench max DD': 'Largest peak-to-low fall of the benchmark within the episode.',
  'Depth': 'Size of the fall from the peak to the trough.',
  'Peak': 'Last high before the fall.',
  'Trough': 'Lowest point of the drawdown.',
  'Recovered': 'First day back at the previous peak.',
  'Exit reason': 'Why the position was sold. Hover the Exits rows in Trade statistics for each reason.',
  'P&L (after costs)': 'Profit or loss in rupees, after buy and sell costs.',
  'Weight': 'Share of total equity on the last day.',
  'Unrealised': 'Gain or loss on the position not yet sold, at the last close.',
  'Costs': 'Brokerage, taxes, exchange and depository charges on this fill.',

  // costs and tax
  'Before any costs or tax': 'Estimated CAGR with every day’s charges, slippage and tax added back as a return on the previous day’s equity.',
  'After trading costs (charges + slippage)': 'Estimated CAGR after STT, stamp duty, exchange, SEBI, GST, DP charges and slippage, before capital-gains tax.',
  'After costs and tax (the backtest)': 'The backtest’s own CAGR: tax was paid from the portfolio each April.',
  'After costs and tax (estimated)': 'Tax was not deducted in this run; this subtracts each year’s tax as a return on that day’s equity.',
  'After tax, if everything were sold on the last day': 'CAGR to the value left after selling every holding on the last day and paying all tax still due, including the year in progress.',
  'Trading costs': 'Charges plus slippage over the whole backtest.',
  'Capital-gains tax': 'STCG and LTCG tax for completed financial years, including cess and surcharge.',
  'Value traded': 'Total value of all buys and sells.',
  'Cost per ₹ traded': 'Charges plus slippage per side, in basis points (1 bp = 0.01%) of value traded.',
  'Round-trip cost': 'Typical cost of buying and later selling, in basis points of the position: charges on both sides plus slippage twice.',
  'Average trade size': 'Average value of a closed round trip at entry.',
  'Median trade return': 'Median price return of closed round trips, before costs. Compare with the round-trip cost.',
  'Average trade return': 'Average price return of closed round trips, before costs.',
  'Tax accrued, not yet paid': 'Tax on gains realised so far in the financial year that was still running at the end.',
  'Tax if sold everything': 'Tax for the running financial year if every holding were sold at the last close.',
  'Selling costs if sold everything': 'Charges and slippage to sell every holding at the last close.',
  'Value after selling and tax': 'Equity minus selling costs and all tax that would still be due. What you would actually keep.',
  'Losses carried forward': 'Capital losses not yet used against gains. They can offset gains for 8 financial years.',

  // robustness
  'Net P&L': 'Sum of every holding’s profit and loss, after charges and slippage, before tax.',
  'Names traded': 'Distinct stocks and funds held at some point.',
  'Top 1 share': 'Share of net P&L from the single best holding.',
  'Top 5 share': 'Share of net P&L from the five best holdings.',
  'Top 10 share': 'Share of net P&L from the ten best holdings.',
  'Names for 50% of profit': 'How many of the best holdings it takes to add up to half of all gross profit.',
  'Names for 80% of profit': 'How many of the best holdings it takes to add up to 80% of all gross profit.',
  'CAGR without': 'CAGR with this group’s daily P&L removed, as if that money had sat idle.',
  'Sharpe t-statistic': 'Sharpe ratio per session × √sessions. Above 2 suggests positive risk-adjusted return is not chance.',
  'Probabilistic Sharpe': 'Chance the true Sharpe ratio is above 0, correcting for skew and fat tails (Bailey & López de Prado).',
  'Sharpe 95% range': 'Range that should contain the true annual Sharpe ratio 95% of the time, given this much history.',
  'Alpha t-statistic': 'Alpha from a regression of daily returns on the benchmark’s, divided by its standard error. Above 2: unlikely to be luck.',
  'Excess return t-statistic': 'Average daily return above the benchmark divided by its standard error.',
  'CAGR 5th percentile': 'In 95% of resampled histories CAGR was higher than this.',
  'CAGR median': 'Median CAGR across resampled histories.',
  'CAGR 95th percentile': 'Only 5% of resampled histories did better than this.',
  'Typical max drawdown': 'Median worst drawdown across resampled histories.',
  'Bad-case max drawdown': 'Worst drawdown exceeded in only 5% of resampled histories.',
  'Chance CAGR < 15%': 'Share of resampled histories with a CAGR under 15%.',
  'Chance of beating benchmark': 'Share of resampled histories where the strategy’s CAGR beat the benchmark’s over the same resampled days.',
  'Excess CAGR 5th percentile': 'Strategy CAGR minus benchmark CAGR, exceeded in 95% of resampled histories.',
  'Median fill vs volume': 'Median fill size as a share of that session’s traded volume.',
  '95th pct fill vs volume': '95% of fills were smaller than this share of the session’s volume.',
  'Largest fill vs volume': 'Largest fill as a share of the session’s volume.',
  'Fills over 1% of volume': 'Share of fills that took more than 1% of the session’s volume.',
  'Fills cut by volume cap': 'Fills reduced by the maximum share of daily volume. The rest was retried on later sessions.',
  'Delisted exits': 'Positions closed because the stock stopped trading for 30 sessions, booked at the last price less the haircut you set.',
}

const EXIT_TIPS: Record<string, string> = {
  'rebalance: exit': 'Sold completely at a rebalance because the stock was no longer in the target portfolio.',
  'rebalance': 'Sold in part at a rebalance to trim the position back to its target weight. The shares sold close the oldest buys first.',
  'exit': 'Sold by close_all(), which sells every holding.',
  'stop': 'Stop-loss or trailing stop triggered. Fills at the stop price, or at the open if the price gapped below it.',
  'take-profit': 'Take-profit level reached. Fills at that level, or at the open if the price gapped above it.',
  'delisted': 'No trades for 30 sessions (suspended or delisted). Sold at the last traded price.',
  'sell': 'Sold by the strategy with sell() and no specific reason.',
}

export function tip(label: string): string | undefined {
  if (label.startsWith('Exits: ')) {
    const reason = label.slice(7)
    return EXIT_TIPS[reason] ?? `Positions closed for the reason “${reason}”, as set by the strategy.`
  }
  return TIPS[label]
}
