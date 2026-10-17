# asset-context.v1

Input: `asset` is BTC or ETH; optional `trade` contains direction, entry, stop and target. Optional `request_id` is a UUID for deduplication, reused only for the identical request. A duplicate returns 409, not a cached response. There is no provider/model, user identity, venue, horizon or timeframe input.

Output contains `schema_version`, `asset`, `status: partial`, `generated_at_ms`, `cache_hit`, `evidence`, `coverage_gaps`, `observations` and nullable `trade_math`.

- Seven evidence blocks: price and aggregate open interest at 1h/4h/1d, plus funding at 8h. All source timestamps are Unix milliseconds.
- `source` is CoinGlass; `endpoint` identifies the provider API path. Price and funding identify Binance; open interest is aggregate and must not be described as Binance-only.
- `latest` and `previous_change` use `unit`: price USDT, open interest USD, funding percent. A funding change is percentage points, not a fractional ratio. `previous_change` is an absolute difference, not percentage change.
- Status can be available, stale, unavailable, insufficient_history or invalid. Missing numbers are null, not zero. Do not use stale/invalid blocks as current evidence.
- `source_time_ms` identifies the reported candle, `retrieved_at_ms` the retrieval, and `generated_at_ms` response generation. Reported OHLC closes may still be forming; no source-publication timestamp or point-in-time backtest guarantee is provided. A cache hit does not make old evidence fresh.
- `observations` are deterministic observations, not model output. Price/open-interest divergence is a comparison of different measures/venues, not proof of positioning or causation.
- `trade_math` contains absolute `entry_to_stop_usdt`, `entry_to_target_usdt`, and `reward_risk_ratio`; it excludes fees, slippage, leverage and likelihood.
- Partial coverage is expected: macro/catalysts and fundamentals are unavailable. Treat `coverage_gaps` as part of the answer, not something to fill with invented facts.

Failures: 401 sign-in; scope 403 fresh consent; eligibility 403 account access; 429 limits; 409 duplicate admission; 503 gated/unavailable context. Transport success with `isError: true` is a tool failure. At least one available block is required for a useful context response. Never display raw credentials or account identifiers in a briefing.
