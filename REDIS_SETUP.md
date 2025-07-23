# Redis Caching Setup for Siftly

## 🎯 **Overview**

This implementation adds Redis caching to dramatically improve webhook response times by caching Airtable configurations.

## ⚡ **Performance Impact**

- **Before:** 3.2s Airtable lookup time
- **After:** ~30ms Redis cache hit time
- **Improvement:** 99% faster responses

## 🔧 **Setup Steps**

### 1. **Install Redis Dependencies**
```bash
pip install redis==6.2.0
```

### 2. **Configure Redis URL**
Add to your environment variables:
```bash
REDIS_URL="rediss://default:Ab1lAAIjcDFkNDgyNTk5ZTQ0NDA0ZmM1YmQ1ZTBkNWJmMDI1N2RhY3AxMA@aware-jackass-48485.upstash.io:6379"
```

### 3. **Test Redis Connection**
```bash
python test_redis_cache.py
```

### 4. **Set Up Cron Job on Render**

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Navigate to **Cron Jobs**
3. Create new cron job:
   - **Command:** `python cron/cache_airtable_config.py`
   - **Schedule:** `0 */3 * * *` (every 3 hours)

## 🗃️ **How It Works**

### **Cache Flow:**
1. **Webhook received** → Check Redis cache first
2. **Cache hit** → Return data instantly (~30ms)
3. **Cache miss** → Query Airtable → Cache result → Return data
4. **Cron job** → Refresh cache every 3 hours

### **Cache Structure:**
```json
{
  "+32460234291": {
    "customer_name": "John Doe",
    "preferred_language": "Dutch",
    "account_type": "premium",
    "nl-be_agent_name": "Tom"
  }
}
```

## 📊 **Monitoring**

### **Log Messages:**
- `Redis cache hit for +32460234291` - Cache working
- `Redis cache miss for +32460234291` - Fallback to Airtable
- `Cached data for +32460234291 in Redis` - New data cached

### **Performance Metrics:**
- `Airtable lookup duration: X.XXXs` - When cache misses
- `Redis cache hit for +32460234291` - When cache hits

## 🔄 **Cache Refresh**

The cron job runs every 3 hours to:
1. Fetch fresh data from Airtable
2. Update Redis cache with new data
3. Maintain 3-hour TTL for automatic expiration

## 🛠️ **Troubleshooting**

### **Redis Not Configured:**
- Check `REDIS_URL` environment variable
- Verify Upstash Redis instance is active

### **Cache Misses:**
- Ensure cron job is running
- Check Airtable connectivity
- Verify phone numbers in `to_numbers` list

### **Performance Issues:**
- Monitor Redis connection latency
- Check Airtable API rate limits
- Verify async operations are working

## 📈 **Expected Results**

- **First call:** ~0.8s (Airtable + cache)
- **Subsequent calls:** ~0.03s (Redis cache)
- **Cache refresh:** Every 3 hours automatically
- **Fallback:** Always works if Redis fails 