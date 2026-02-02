# API Key Setup Checklist

## Common Issues and Fixes

### 1. IP Whitelist Issue (Most Common)

**Error:** `{"code":-2015,"msg":"Invalid API-key, IP, or permissions for action"}`

**Fix:**
1. Go to Binance API Management: https://www.binance.com/en/my/settings/api-management
2. Click on your `Crypto-LS-Data` API key
3. Check **"Restrict access to trusted IPs only"**
4. Add your current IP address:
   - Find your IP: https://www.whatismyip.com/
   - Add it to the whitelist
5. Save changes
6. Wait 1-2 minutes for changes to propagate

### 2. API Key Permissions

**Required Permissions for Liquidations:**
- ✅ **Read Info** (required)
- ✅ **Enable Futures** (required)
- ❌ Enable Spot & Margin Trading (not needed)
- ❌ Enable Withdrawals (never enable)

**Check:**
1. Go to API Management
2. Click on your `Crypto-LS-Data` key
3. Verify permissions are set correctly

### 3. Testnet vs Production

**If using Testnet:**
- Set `USE_TESTNET=true` in `.env`
- Use testnet API keys: `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_API_SECRET`
- Testnet URL: https://testnet.binancefuture.com/

**If using Production:**
- Ensure `USE_TESTNET` is not set or `false` in `.env`
- Use production API keys: `BINANCE_DATA_API_KEY` and `BINANCE_DATA_API_SECRET`

### 4. Verify API Keys in .env

Make sure your `.env` file has:
```env
BINANCE_DATA_API_KEY=your_full_api_key_here
BINANCE_DATA_API_SECRET=your_full_api_secret_here
```

**No spaces, no quotes, no extra characters**

### 5. Test After Fixes

Run the test script again:
```bash
python scripts/backfill/test_auth.py
```

Should return: `SUCCESS: Authentication working!`

Then test liquidations:
```bash
python scripts/backfill/test_backfill_liquidations.py
```
