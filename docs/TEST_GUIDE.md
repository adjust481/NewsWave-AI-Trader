# Gemini LLM Integration - Testing Guide

## 修改总结

已完成以下修改：

### 1. 统一使用新版 SDK (`google.genai`)
- ✅ 替换 `google.generativeai` → `import google.genai as genai`
- ✅ 使用 `genai.Client(api_key=...)` 初始化
- ✅ 默认模型：`gemini-2.0-flash-exp` (可通过 `GEMINI_MODEL` 环境变量覆盖)

### 2. 修复的文件
- `strategies/ai_pm.py`:
  - 添加 `GEMINI_MODEL` 配置
  - 修复 `decide_strategy_llm()` 的响应解析
  - 简化错误消息（截断到80字符）

- `news_replay.py`:
  - 添加 `_GEMINI_MODEL` 配置
  - 修复 `analyze_pattern_with_llm()` 的响应解析
  - 添加 `llm_model` 字段追踪使用的模型
  - 简化错误消息

- `demo_news_driven.py`:
  - 改进 LLM 状态显示
  - 成功时显示：`[Note] LLM analysis: OK (model=XXX)`
  - 失败时显示：`[Note] LLM error: <简短描述>`

### 3. 关键改进
- 响应解析兼容多种结构：`response.text` 或 `response.candidates[0].content.parts[0].text`
- 错误消息截断到100字符，避免日志爆炸
- 保留完整的 fallback 逻辑

---

## 测试步骤

### 前置条件

确保安装最新的 SDK：
```bash
python3 -m pip install --upgrade google-genai
```

### 测试 1: 纯规则模式（验证不会炸）

```bash
# 使用你配置的 ai_router_off 函数
ai_router_off

# 或手动执行
unset AI_PM_USE_LLM
unset GEMINI_API_KEY
cd ~/Desktop/ai_quant_router

# 运行 demo
python3 demo_news_driven.py
```

**预期结果：**
```
HISTORICAL PATTERN ANALYSIS
----------------------------------------------------------------------
  Pattern name:     广告_利好
  Avg return (1D):  +10.0%
  Avg return (3D):  +18.0%
  Avg return (7D):  +25.0%
  Confidence:       0.55 (low)
  Typical horizon:  7d
  Analysis method:  rule_based
  Comment:          样本 1 条，平均 3 日上涨 18.0%，置信度low
  [Note] LLM error: LLM not enabled (set AI_PM_USE_LLM=1)

AI PM DECISION
----------------------------------------------------------------------
  Strategy:     ou_arb
  Risk mode:    defensive
  Confidence:   0.95
  Reason:       Arb regime detected (1/1 recent ticks) | hist_pattern=广告_利好 avg_3d=18.0% conf=low
```

✅ 关键点：
- `analysis_method=rule_based`
- 有 `[Note]` 提示但不影响运行
- AI PM 决策正常，没有 fallback 文案
- Demo 正常结束，有订单生成

---

### 测试 2: LLM 开启但缺 API Key（验证 fallback）

```bash
ai_router_off
export AI_PM_USE_LLM=1
# 不设置 GEMINI_API_KEY

python3 demo_news_driven.py
```

**预期结果：**
```
HISTORICAL PATTERN ANALYSIS
----------------------------------------------------------------------
  Pattern name:     广告_利好
  ...
  Analysis method:  rule_based
  [Note] LLM error: RuntimeError: GEMINI_API_KEY not set

AI PM DECISION
----------------------------------------------------------------------
  Strategy:     ou_arb
  Risk mode:    defensive
  Reason:       Arb regime detected (1/1 recent ticks) (fallback_to_rule_based: RuntimeError('LLM error (RuntimeError): GEMINI_API_KEY not set'))
```

✅ 关键点：
- 错误消息简短清晰
- `analysis_method=rule_based`（降级成功）
- AI PM 的 reason 包含 `fallback_to_rule_based` 和 `RuntimeError`
- Demo 正常结束，有订单

---

### 测试 3: LLM 真实连通（需要真实 API Key）

```bash
# 使用你配置的 ai_router_llm 函数
ai_router_llm

# 或手动执行
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="你的真实API密钥"
cd ~/Desktop/ai_quant_router

# 可选：指定不同的模型
# export GEMINI_MODEL="gemini-1.5-flash"

python3 demo_news_driven.py
```

**预期结果（成功时）：**
```
HISTORICAL PATTERN ANALYSIS
----------------------------------------------------------------------
  Pattern name:     广告利好消息  # LLM 生成的名称
  Avg return (1D):  +10.0%
  Avg return (3D):  +18.0%
  Avg return (7D):  +25.0%
  Confidence:       0.55 (medium)  # LLM 可能给出不同的评估
  Typical horizon:  7d
  Analysis method:  llm  # ← 关键：显示 llm
  Comment:          这是一个积极的广告合作消息，通常会带来短期股价上涨
  [Note] LLM analysis: OK (model=gemini-2.0-flash-exp)  # ← 成功标记

AI PM DECISION
----------------------------------------------------------------------
  Strategy:     ou_arb
  Risk mode:    defensive
  Reason:       [LLM] 当前存在套利机会，建议采用防御性策略  # ← LLM 生成的理由
```

✅ 关键点：
- `analysis_method=llm`
- 显示 `[Note] LLM analysis: OK (model=...)`
- AI PM 的 reason 以 `[LLM]` 开头
- Comment 是中文的自然语言解释

---

### 测试 4: 运行完整测试套件

```bash
cd ~/Desktop/ai_quant_router
python3 -m pytest -xvs
```

**预期结果：**
```
============================= 103 passed in 0.56s ==============================
```

✅ 所有测试通过，没有破坏现有功能

---

## 可用的模型名称

你可以通过 `GEMINI_MODEL` 环境变量切换模型：

```bash
# 使用最新的 2.0 flash（默认）
export GEMINI_MODEL="gemini-2.0-flash-exp"

# 使用稳定的 1.5 flash
export GEMINI_MODEL="gemini-1.5-flash"

# 使用更强大的 1.5 pro
export GEMINI_MODEL="gemini-1.5-pro"

# 使用最新的 2.0 flash thinking（推理能力更强）
export GEMINI_MODEL="gemini-2.0-flash-thinking-exp"
```

---

## 故障排查

### 问题 1: 仍然出现 404 错误

**可能原因：**
- 模型名称不正确
- API key 没有权限访问该模型

**解决方案：**
```bash
# 尝试使用稳定的 1.5 版本
export GEMINI_MODEL="gemini-1.5-flash"
python3 demo_news_driven.py
```

### 问题 2: 响应解析失败

**症状：**
```
[Note] LLM error: JSONDecodeError: ...
```

**说明：** 模型返回了非 JSON 格式的内容，已自动降级到 rule-based

**解决方案：** 这是正常的 fallback 行为，不影响使用

### 问题 3: 网络超时

**症状：**
```
[Note] LLM error: TimeoutError: ...
```

**解决方案：**
- 检查代理设置
- 增加超时时间（需要修改代码）
- 或接受 fallback 到 rule-based

---

## 代码修改要点

### 响应解析（兼容多种结构）

```python
# 新版 SDK 的响应可能有不同结构
if hasattr(response, 'text'):
    text = response.text
elif hasattr(response, 'candidates') and response.candidates:
    text = response.candidates[0].content.parts[0].text
else:
    raise RuntimeError("Unexpected Gemini response structure")
```

### 错误消息截断

```python
# 避免日志爆炸
error_type = type(e).__name__
error_msg = str(e)[:100]  # 只保留前100字符
```

### 模型配置

```python
# 支持环境变量覆盖
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
```

---

## 下一步

1. **验证 LLM 真实调用**：使用真实 API key 运行测试 3
2. **调整模型**：如果 2.0 版本有问题，切换到 1.5 版本
3. **监控日志**：观察 LLM 返回的 JSON 格式是否符合预期
4. **优化 Prompt**：根据实际返回结果调整 prompt 内容

---

## 快速命令参考

```bash
# 规则模式
ai_router_off && python3 demo_news_driven.py

# LLM 模式（需要先设置 key）
ai_router_llm && python3 demo_news_driven.py

# 运行测试
pytest -xvs

# 查看当前配置
echo "LLM: $AI_PM_USE_LLM"
echo "Key: ${GEMINI_API_KEY:0:20}..."
echo "Model: ${GEMINI_MODEL:-gemini-2.0-flash-exp}"
```
