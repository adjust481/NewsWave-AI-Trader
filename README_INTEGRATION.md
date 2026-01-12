# LLM Integration Guide (Advanced)

> **Note:** This is an advanced reference document for LLM integration details. For general usage and demos, please see the main [README.md](./README.md).

This document provides detailed operational guidance for integrating and troubleshooting the Gemini LLM mode in the AI Quant Router project.

---

## Table of Contents

- [Environment Variables Reference](#environment-variables-reference)
- [Gemini Model Selection](#gemini-model-selection)
- [Common Use Cases](#common-use-cases)
- [Troubleshooting](#troubleshooting)
- [Production Deployment](#production-deployment)
- [Testing LLM Integration](#testing-llm-integration)

---

## Environment Variables Reference

### Core Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AI_PM_USE_LLM` | No | `0` (disabled) | Set to `1` to enable LLM mode |
| `GEMINI_API_KEY` | Yes (for LLM mode) | None | Your Gemini API key from Google AI Studio |
| `GEMINI_MODEL` | No | `gemini-2.0-flash-exp` | Gemini model to use |

### Example Configurations

**Development (rule-based only):**
```bash
# No variables needed - rule-based is the default
python3 demo_news_driven.py
```

**Testing with LLM:**
```bash
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="your_key_here"
export GEMINI_MODEL="gemini-1.5-flash"  # Stable model
python3 demo_news_driven.py
```

**Production:**
```bash
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="production_key"
export GEMINI_MODEL="gemini-1.5-flash"  # Use stable version
python3 demo_news_driven.py
```

---

## Gemini Model Selection

### Available Models

| Model | Speed | Quality | Cost | Stability | Recommended For |
|-------|-------|---------|------|-----------|-----------------|
| `gemini-2.0-flash-exp` | ⚡⚡⚡ | ⭐⭐⭐ | 💰 | ⚠️ Experimental | Latest features, testing |
| `gemini-1.5-flash` | ⚡⚡⚡ | ⭐⭐ | 💰 | ✅ Stable | Production, daily use |
| `gemini-1.5-pro` | ⚡⚡ | ⭐⭐⭐⭐ | 💰💰💰 | ✅ Stable | Complex reasoning, high-stakes |
| `gemini-2.0-flash-thinking-exp` | ⚡ | ⭐⭐⭐⭐ | 💰💰 | ⚠️ Experimental | Deep analysis, research |

### Model Selection Guide

**For hackathon demos:**
```bash
export GEMINI_MODEL="gemini-2.0-flash-exp"  # Latest, impressive
```

**For production:**
```bash
export GEMINI_MODEL="gemini-1.5-flash"  # Stable, reliable
```

**For research/analysis:**
```bash
export GEMINI_MODEL="gemini-1.5-pro"  # Best quality
```

### Switching Models at Runtime

```bash
# Test with different models
export GEMINI_MODEL="gemini-1.5-flash"
python3 demo_news_driven.py

export GEMINI_MODEL="gemini-1.5-pro"
python3 demo_news_driven.py
```

---

## Common Use Cases

### Use Case 1: Fast Development (No LLM)

**Scenario:** Iterating on code, running tests frequently

```bash
# No setup needed - just run
python3 demo_news_driven.py
pytest
```

**Why:** Fast, free, no network dependency, no API quota concerns

---

### Use Case 2: Demo/Presentation (With LLM)

**Scenario:** Showing the project to judges or stakeholders

```bash
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="your_key"
export GEMINI_MODEL="gemini-2.0-flash-exp"  # Latest features
python3 demo_news_driven.py
```

**Why:** Shows real AI reasoning, impressive natural language output

---

### Use Case 3: Production Deployment

**Scenario:** Running in a live trading environment

```bash
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="production_key"
export GEMINI_MODEL="gemini-1.5-flash"  # Stable version
python3 demo_news_driven.py
```

**Why:** Reliable with automatic fallback, stable API, predictable costs

---

### Use Case 4: A/B Testing Models

**Scenario:** Comparing model performance

```bash
# Run with Flash
export GEMINI_MODEL="gemini-1.5-flash"
python3 demo_news_driven.py > results_flash.txt

# Run with Pro
export GEMINI_MODEL="gemini-1.5-pro"
python3 demo_news_driven.py > results_pro.txt

# Compare outputs
diff results_flash.txt results_pro.txt
```

**Why:** Understand quality vs. cost tradeoffs

---

## Troubleshooting

### Problem: "google.genai module not found"

**Error message:**
```
ModuleNotFoundError: No module named 'google.genai'
```

**Solution:**
```bash
pip install --upgrade google-genai
```

---

### Problem: "404 NOT_FOUND: models/gemini-2.0-flash-exp"

**Error message:**
```
[Note] LLM error: 404 models/gemini-2.0-flash-exp is not found
```

**Cause:** Experimental model may not be available in your region or has been deprecated.

**Solution:** Switch to a stable model:
```bash
export GEMINI_MODEL="gemini-1.5-flash"
python3 demo_news_driven.py
```

---

### Problem: "GEMINI_API_KEY not set"

**Error message:**
```
[Note] LLM error: RuntimeError: GEMINI_API_KEY not set
```

**Solution:**
```bash
# Set your API key
export GEMINI_API_KEY="your_actual_key_here"

# Verify it's set
echo $GEMINI_API_KEY
```

**Get an API key:**
1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy and use the key

---

### Problem: "429 RESOURCE_EXHAUSTED: Quota exceeded"

**Error message:**
```
[Note] LLM error: 429 Quota exceeded for quota metric
```

**Cause:** You've hit the API rate limit or daily quota.

**Solution:**
```bash
# The system automatically falls back to rule-based mode
# Wait a few minutes and try again, or:

# 1. Use a different API key
export GEMINI_API_KEY="backup_key"

# 2. Switch to a lower-tier model (lower quota usage)
export GEMINI_MODEL="gemini-1.5-flash"

# 3. Disable LLM temporarily
unset AI_PM_USE_LLM
```

---

### Problem: Tests failing with LLM enabled

**Scenario:** Tests pass in rule-based mode but fail with LLM enabled.

**Solution:**
```bash
# Run tests in rule-based mode (recommended)
unset AI_PM_USE_LLM
pytest

# If you need to test LLM integration specifically:
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="your_key"
pytest tests/test_ai_integration.py -v
```

---

### Problem: LLM responses are inconsistent

**Scenario:** Same input produces different outputs across runs.

**Explanation:** This is expected behavior - LLMs are non-deterministic by design.

**Mitigation:**
- The system uses fallback logic to ensure robustness
- Rule-based mode is always available as a consistent baseline
- For testing, use rule-based mode to ensure reproducibility

---

## Production Deployment

### Recommended Configuration

```bash
# Use stable model
export GEMINI_MODEL="gemini-1.5-flash"

# Enable LLM with fallback
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="production_key"

# Run your application
python3 demo_news_driven.py
```

### Best Practices

1. **Always test fallback behavior:**
   ```bash
   # Simulate API failure by using invalid key
   export GEMINI_API_KEY="invalid"
   python3 demo_news_driven.py
   # Should fall back to rule-based mode gracefully
   ```

2. **Monitor LLM success rate:**
   - Check logs for `[Note] LLM analysis: OK` (success)
   - Check logs for `[Note] LLM error:` (fallback triggered)

3. **Use stable models in production:**
   - Avoid experimental models (`-exp` suffix)
   - Prefer `gemini-1.5-flash` or `gemini-1.5-pro`

4. **Set up API key rotation:**
   - Have backup keys ready
   - Monitor quota usage
   - Implement key rotation if needed

5. **Test under failure conditions:**
   - Network timeouts
   - Invalid API keys
   - Quota exhaustion
   - Model deprecation

### Health Check Script

```bash
#!/bin/bash
# health_check.sh - Verify LLM integration is working

echo "Testing rule-based mode..."
unset AI_PM_USE_LLM
python3 demo_news_driven.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "✓ Rule-based mode: OK"
else
  echo "✗ Rule-based mode: FAILED"
  exit 1
fi

echo "Testing LLM mode..."
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="$PRODUCTION_GEMINI_KEY"
python3 demo_news_driven.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "✓ LLM mode: OK"
else
  echo "✗ LLM mode: FAILED (check API key and quota)"
  exit 1
fi

echo "✓ All checks passed"
```

---

## Testing LLM Integration

### Quick Verification

```bash
# 1. Test rule-based mode (should always work)
unset AI_PM_USE_LLM
python3 demo_news_driven.py

# 2. Test LLM mode (requires API key)
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="your_key"
python3 demo_news_driven.py

# 3. Run unit tests
pytest tests/test_ai_integration.py -v
```

### Expected Output Patterns

**Rule-based mode:**
```
HISTORICAL PATTERN ANALYSIS
----------------------------------------------------------------------
  Pattern name:     广告_利好
  Analysis method:  rule_based
  [Note] LLM error: LLM not enabled (set AI_PM_USE_LLM=1)

AI PM DECISION
----------------------------------------------------------------------
  Strategy:     ou_arb
  Reason:       Arb regime detected (1/1 recent ticks)
```

**LLM mode (success):**
```
HISTORICAL PATTERN ANALYSIS
----------------------------------------------------------------------
  Pattern name:     广告利好消息
  Analysis method:  llm
  Comment:          这是一个积极的广告合作消息，通常会带来短期股价上涨
  [Note] LLM analysis: OK (model=gemini-2.0-flash-exp)

AI PM DECISION
----------------------------------------------------------------------
  Strategy:     ou_arb
  Reason:       [LLM] 当前存在套利机会，建议采用防御性策略
```

**LLM mode (fallback):**
```
HISTORICAL PATTERN ANALYSIS
----------------------------------------------------------------------
  Pattern name:     广告_利好
  Analysis method:  rule_based
  [Note] LLM error: RuntimeError: GEMINI_API_KEY not set

AI PM DECISION
----------------------------------------------------------------------
  Strategy:     ou_arb
  Reason:       Arb regime detected (1/1 recent ticks) (fallback_to_rule_based: ...)
```

### Integration Test Checklist

- [ ] Rule-based mode works without API key
- [ ] LLM mode works with valid API key
- [ ] Fallback triggers when API key is missing
- [ ] Fallback triggers when API key is invalid
- [ ] Fallback triggers on network errors
- [ ] Error messages are concise and clear
- [ ] All 103 unit tests pass
- [ ] Demo completes successfully in both modes

---

## Helper Functions (Optional)

If you frequently switch between modes, add these to your `~/.zshrc`:

```bash
# Add to ~/.zshrc

ai_router_off() {
  unset AI_PM_USE_LLM
  unset GEMINI_API_KEY
  echo "✓ AI Router: LLM disabled (rule-based mode)"
}

ai_router_llm() {
  export AI_PM_USE_LLM=1
  export GEMINI_API_KEY="your_actual_key_here"
  export GEMINI_MODEL="gemini-2.0-flash-exp"
  echo "✓ AI Router: LLM enabled (model=$GEMINI_MODEL)"
}

ai_router_status() {
  echo "AI_PM_USE_LLM: ${AI_PM_USE_LLM:-not set}"
  echo "GEMINI_API_KEY: ${GEMINI_API_KEY:+set (${#GEMINI_API_KEY} chars)}"
  echo "GEMINI_MODEL: ${GEMINI_MODEL:-gemini-2.0-flash-exp (default)}"
}
```

**Usage:**
```bash
source ~/.zshrc

ai_router_off      # Disable LLM
ai_router_llm      # Enable LLM
ai_router_status   # Check current configuration
```

---

## External Resources

- [Google Gemini API Documentation](https://ai.google.dev/gemini-api/docs)
- [Available Gemini Models](https://ai.google.dev/gemini-api/docs/models/gemini)
- [Google AI Studio (Get API Key)](https://aistudio.google.com/app/apikey)
- [Python SDK Documentation](https://ai.google.dev/gemini-api/docs/quickstart?lang=python)

---

## Summary

This document covered:
- ✅ Environment variable configuration
- ✅ Model selection and comparison
- ✅ Common use cases and workflows
- ✅ Troubleshooting guide for common errors
- ✅ Production deployment best practices
- ✅ Testing and verification procedures

For general project information, architecture, and demos, return to [README.md](./README.md).

---

**Last Updated:** 2025-01-12
**Status:** Production Ready
