# External Data Sources

This document provides an overview of external cryptocurrency data sources available for integration into the Crypto-LS system, focusing on free-tier APIs that complement Binance exchange data.

## Overview

While Binance provides comprehensive exchange-specific data (OHLCV, funding rates, open interest, etc.), external data aggregators offer additional value through:

- **Cross-exchange price aggregation**: Compare prices across multiple exchanges
- **Historical data**: Extended historical price and market data
- **Market intelligence**: Rankings, categories, trending coins, global metrics
- **On-chain data**: Blockchain metrics and analytics (future consideration)

This document focuses on **free-tier APIs** from CoinGecko and CoinMarketCap, which provide substantial data without cost.

---

## CoinGecko Free API

### Overview

CoinGecko is an independent cryptocurrency data aggregator tracking 18,000+ cryptocurrencies across 1,460+ exchanges. The free Public/Demo API provides comprehensive market data and historical information.

### API Details

- **Base URL**: `https://api.coingecko.com/api/v3`
- **Authentication**: No API key required for free tier (rate limits apply)
- **Documentation**: https://docs.coingecko.com/

### Available Data Types

#### 1. Price Data
- **Current Prices**: `/simple/price` - Query cryptocurrency prices in supported currencies
- **Token Prices**: `/simple/token_price/{id}` - Get token prices by contract address
- **Market Data**: `/coins/markets` - Query all coins with price, market cap, volume, and market data
- **Historical Prices**: `/coins/{id}/market_chart` - Historical market data (price, market cap, volume) with automatic granularity
- **OHLC Data**: `/coins/{id}/ohlc` - OHLC (candlestick) data for charting

#### 2. Coin Information
- **Coin List**: `/coins/list` - List all supported coins (ID, name, symbol)
- **Coin Details**: `/coins/{id}` - Detailed metadata including:
  - Description, logo, websites, social links
  - Contract addresses for token platforms
  - Technical documentation links
- **Historical Data**: `/coins/{id}/history` - Historical price, market cap, volume for specific dates
- **Exchange Tickers**: `/coins/{id}/tickers` - Coin tickers from CEX and DEX exchanges

#### 3. Market Data
- **Global Metrics**: `/global` - Global cryptocurrency market data (total market cap, BTC dominance, etc.)
- **Trending**: `/trending` - Trending coins, NFTs, and categories

#### 4. Exchange Data
- **Exchange List**: `/exchanges` - List active exchanges with trading volumes
- **Exchange Details**: `/exchanges/{id}` - Exchange-specific information

#### 5. Categories & Platforms
- **Categories**: `/coins/categories/list` - All coin categories
- **Category Data**: `/coins/categories` - Categories with market data
- **Asset Platforms**: `/asset_platforms` - List blockchain networks (Ethereum, BSC, Polygon, etc.)

#### 6. Derivatives
- **Derivatives**: `/derivatives` - Derivative tickers and exchanges

### Rate Limits

Rate limits for the free tier are not explicitly documented but exist. It's recommended to:
- Implement request throttling (e.g., 1 request per second)
- Cache responses when possible
- Monitor for 429 (Too Many Requests) errors

### Use Cases

- **Historical Price Analysis**: Access extended historical data beyond Binance's limits
- **Cross-Exchange Comparison**: Compare prices across multiple exchanges
- **Market Overview**: Global market metrics and trending coins
- **Token Discovery**: Find tokens by contract address or platform
- **Category Analysis**: Analyze coins by categories (DeFi, NFT, Gaming, etc.)

---

## CoinMarketCap Free API (Basic Plan)

### Overview

CoinMarketCap is a leading cryptocurrency market data aggregator. The free Basic plan provides access to 30+ endpoints with current market data (no historical data).

### API Details

- **Base URL**: `https://pro-api.coinmarketcap.com/v1`
- **Authentication**: API key required (free signup at pro.coinmarketcap.com)
- **Documentation**: https://coinmarketcap.com/api/documentation/v1/

### Plan Limits

- **Monthly Credits**: 10,000 call credits per month
- **Rate Limit**: 30 requests per minute
- **Historical Data**: ❌ Not available (latest data only)
- **Use Case**: Personal use only

### Available Endpoints (30+)

#### 1. Cryptocurrency Data

**Latest Market Data:**
- `/v1/cryptocurrency/listings/latest` - Latest ranked listings with price, market cap, volume
- `/v2/cryptocurrency/quotes/latest` - Latest quotes for specific coins
- `/v2/cryptocurrency/info` - Coin metadata (logo, description, links, socials)
- `/v1/cryptocurrency/map` - CoinMarketCap ID mapping (recommended for stable IDs)
- `/v2/cryptocurrency/market-pairs/latest` - Market pairs for coins across exchanges
- `/v2/cryptocurrency/ohlcv/latest` - Latest OHLCV data (no historical)
- `/v2/cryptocurrency/price-performance-stats/latest` - Price performance statistics

**Categories & Trends:**
- `/v1/cryptocurrency/categories` - Coin categories with market data
- `/v1/cryptocurrency/category` - Single category details
- `/v1/cryptocurrency/trending/latest` - Trending coins (24h, 7d, 30d)
- `/v1/cryptocurrency/trending/gainers-losers` - Biggest gainers & losers
- `/v1/cryptocurrency/trending/most-visited` - Most visited coins

#### 2. Exchange Data

- `/v1/exchange/listings/latest` - Exchange rankings by volume
- `/v1/exchange/quotes/latest` - Exchange quotes and statistics
- `/v1/exchange/market-pairs/latest` - Exchange market pairs
- `/v1/exchange/info` - Exchange metadata
- `/v1/exchange/map` - Exchange ID mapping
- `/v1/exchange/assets` - Exchange asset holdings (reserves)

#### 3. Global Metrics

- `/v1/global-metrics/quotes/latest` - Global market data:
  - Total market cap
  - BTC dominance
  - Altcoin market cap
  - Total volume (24h)
  - Active cryptocurrencies/exchanges count

#### 4. Tools

- `/v2/tools/price-conversion` - Price conversion (1 conversion per call, supports 93 fiat currencies + 4 precious metals)

#### 5. Blockchain Data

- `/v1/blockchain/statistics/latest` - Blockchain statistics (Bitcoin, Ethereum, etc.)

#### 6. Fiat & Other

- `/v1/fiat/map` - Fiat currency mapping
- `/v1/key/info` - API key usage and limits

### Credit System

CoinMarketCap uses a credit system:
- **Base cost**: 1 credit per endpoint call
- **Paginated endpoints**: +1 credit per 100 data points returned (rounded up)
- **Currency conversion**: +1 credit per conversion option beyond the first
- **Example**: `/cryptocurrency/listings/latest?limit=5000` = 1 base + 50 (5000/100) = 51 credits

### Use Cases

- **Market Rankings**: Get ranked lists of cryptocurrencies by market cap
- **Price Comparison**: Compare prices across exchanges via market pairs
- **Trending Analysis**: Identify trending coins and gainers/losers
- **Global Metrics**: Track overall market health (BTC dominance, total market cap)
- **Exchange Analysis**: Compare exchange volumes and market pairs
- **Category Analysis**: Analyze coins by categories

### Limitations

- **No Historical Data**: Only latest/current data available on free tier
- **Credit Limits**: 10,000 credits/month (~333 calls/day if using 30 credits per call)
- **Rate Limits**: 30 requests/minute requires careful request management

---

## Comparison: CoinGecko vs CoinMarketCap

| Feature | CoinGecko Free | CoinMarketCap Free |
|---------|----------------|-------------------|
| **Current Prices** | ✅ Yes | ✅ Yes |
| **Historical Prices** | ✅ Yes (market_chart, ohlc) | ❌ No (latest only) |
| **Market Cap & Volume** | ✅ Yes | ✅ Yes |
| **OHLCV Data** | ✅ Yes | ✅ Yes (latest only) |
| **Exchange Data** | ✅ Yes | ✅ Yes |
| **Categories** | ✅ Yes | ✅ Yes |
| **Trending Data** | ✅ Yes | ✅ Yes |
| **Global Metrics** | ✅ Yes | ✅ Yes |
| **Metadata** | ✅ Yes | ✅ Yes |
| **Monthly Limits** | Not explicitly stated | 10,000 credits |
| **Rate Limits** | Not explicitly stated | 30 req/min |
| **Historical Data** | ✅ Full historical | ❌ Latest only |
| **API Key Required** | ❌ No | ✅ Yes (free signup) |

---

## Integration Recommendations

### For Historical Data
**Use CoinGecko** for:
- Historical price data beyond Binance's limits
- OHLC data for backtesting
- Market chart data with automatic granularity

### For Market Intelligence
**Use CoinMarketCap** for:
- Market rankings and trending coins
- Cross-exchange price comparison via market pairs
- Global market metrics (BTC dominance, total market cap)
- Exchange rankings and volumes

### Complementary Use
Both APIs complement Binance data:
- **Binance**: Exchange-specific data (OHLCV, funding rates, open interest, futures data)
- **CoinGecko**: Historical data and cross-exchange aggregation
- **CoinMarketCap**: Market rankings, categories, trending analysis, global metrics

---

## Implementation Considerations

### Rate Limiting
- **CoinGecko**: Implement conservative throttling (1 req/sec recommended)
- **CoinMarketCap**: Respect 30 req/min limit, monitor credit usage

### Caching Strategy
- Cache responses to minimize API calls
- CoinGecko: Cache historical data (doesn't change)
- CoinMarketCap: Cache latest data for 1-5 minutes depending on use case

### Error Handling
- Handle 429 (Too Many Requests) with exponential backoff
- Monitor credit usage for CoinMarketCap
- Implement fallback strategies if APIs are unavailable

### Data Storage
Consider storing:
- **CoinGecko**: Historical price data, market charts
- **CoinMarketCap**: Rankings snapshots, trending data, global metrics

---

## Future Considerations

### On-Chain Data Providers
For blockchain/on-chain data (not covered in this document):
- **Glassnode**: On-chain analytics ($999+/month)
- **Etherscan API**: Ethereum/BSC on-chain data (FREE tier available)
- **IntoTheBlock/Sentora**: On-chain analysis (now free research platform)

### Paid Tier Upgrades
If free tiers become limiting:
- **CoinGecko Pro**: Higher rate limits, more endpoints
- **CoinMarketCap Hobbyist**: $29/month for 12 months historical data
- **CoinMarketCap Startup**: $79/month for 24 months historical data

---

## Related Documentation

- [Architecture Overview](ARCHITECTURE.md) - System architecture and data flow
- [Binance Data Collection](ARCHITECTURE.md#data-flow) - Current Binance data sources
- [Data Integrity](operations/data-integrity.md) - Data quality checks

---

## References

- CoinGecko API Documentation: https://docs.coingecko.com/
- CoinMarketCap API Documentation: https://coinmarketcap.com/api/documentation/v1/
- CoinGecko Pricing: https://www.coingecko.com/en/api/pricing
- CoinMarketCap Pricing: https://coinmarketcap.com/api/pricing/
