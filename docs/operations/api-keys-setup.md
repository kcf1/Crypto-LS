# API Keys Setup Guide

## Overview

The system uses separate API keys for different purposes to improve security:

- **Data Collection Keys** (`BINANCE_DATA_API_KEY` / `BINANCE_DATA_API_SECRET`): Read-only keys for data collection (liquidations)
- **Trading Keys** (`BINANCE_TRADING_API_KEY` / `BINANCE_TRADING_API_SECRET`): Keys with trading permissions for order management

## Setup Steps

### 1. Create API Keys in Binance

#### Data Collection Key (Read-only)
1. Go to Binance API Management: https://www.binance.com/en/my/settings/api-management
2. Create new API key with label: `Crypto-LS-Data`
3. **Permissions:**
   - ✅ Read Info
   - ✅ Enable Futures
   - ❌ Enable Spot & Margin Trading (not needed)
   - ❌ Enable Withdrawals (never enable)
4. **IP Whitelist:** Add your data collection server IPs
5. Copy the API Key and Secret Key

#### Trading Key (Read + Trade)
1. Create another API key with label: `Crypto-LS-Trading`
2. **Permissions:**
   - ✅ Read Info
   - ✅ Enable Spot & Margin Trading (if trading spot)
   - ✅ Enable Futures (if trading futures)
   - ❌ Enable Withdrawals (never enable unless absolutely necessary)
3. **IP Whitelist:** Add your trading server IPs
4. Copy the API Key and Secret Key

### 2. Configure `.env` File

Add the keys to your `.env` file (create from `.env.example` if needed):

```env
# Data Collection (Read-only, for liquidations data)
BINANCE_DATA_API_KEY=your_data_collection_api_key_here
BINANCE_DATA_API_SECRET=your_data_collection_api_secret_here

# Trading/Order Management (Read + Trade, for order placement)
BINANCE_TRADING_API_KEY=your_trading_api_key_here
BINANCE_TRADING_API_SECRET=your_trading_api_secret_here
```

### 3. Update Docker Services

If using Docker, the `docker-compose.yml` is configured to load environment variables from `.env`:

```bash
# Restart the data-updater service to pick up new API keys
docker compose restart data-updater

# Or rebuild and restart
docker compose up -d --build data-updater
```

### 4. Verify Configuration

Check that the services are using the correct keys:

```bash
# Check data-updater logs for liquidations collection
docker logs crypto-ls-data-updater | grep -i liquidation

# Should see successful data collection if keys are configured correctly
```

## Security Best Practices

1. **Use Separate Keys**: Always use different keys for data collection and trading
2. **IP Whitelisting**: Restrict API keys to specific IP addresses
3. **Read-Only for Data**: Data collection keys should only have read permissions
4. **No Withdrawals**: Never enable withdrawal permissions unless absolutely necessary
5. **Rotate Regularly**: Periodically regenerate API keys
6. **Testnet for Development**: Use testnet keys for development and testing

## Troubleshooting

### Liquidations Not Collecting

If liquidations data is not being collected:

1. **Check API keys are set:**
   ```bash
   # In Docker container
   docker exec crypto-ls-data-updater env | grep BINANCE_DATA
   ```

2. **Check logs:**
   ```bash
   docker logs crypto-ls-data-updater | grep -i "skip liquidations\|API key"
   ```

3. **Verify key permissions:**
   - Ensure `BINANCE_DATA_API_KEY` has "Read Info" and "Enable Futures" permissions
   - Check IP whitelist includes your server IP

### Trading Not Working

If order placement fails:

1. **Check trading keys are set:**
   ```bash
   # In your environment
   echo $BINANCE_TRADING_API_KEY
   ```

2. **Verify key permissions:**
   - Ensure `BINANCE_TRADING_API_KEY` has trading permissions enabled
   - Check IP whitelist includes your server IP

## Legacy Support

The system maintains backward compatibility with legacy single API key setup:

- If `BINANCE_DATA_API_KEY` is not set, it falls back to `BINANCE_API_KEY`
- If `BINANCE_TRADING_API_KEY` is not set, it falls back to `BINANCE_API_KEY`

However, using separate keys is **strongly recommended** for better security.
