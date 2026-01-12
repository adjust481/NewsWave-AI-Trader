# 🚀 Gemini LLM 集成 - 快速参考卡

## 📦 安装

```bash
python3 -m pip install --upgrade google-genai
```

## 🎯 快速测试

```bash
# 方式 1: 使用测试脚本
chmod +x quick_test.sh
./quick_test.sh all

# 方式 2: 手动测试
ai_router_off && python3 demo_news_driven.py  # 规则模式
ai_router_llm && python3 demo_news_driven.py  # LLM 模式
```

## 🔧 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_PM_USE_LLM` | `0` | 设为 `1` 启用 LLM |
| `GEMINI_API_KEY` | - | 必需：你的 API 密钥 |
| `GEMINI_MODEL` | `gemini-2.0-flash-exp` | 可选：模型名称 |

## 📝 可用模型

```bash
# 最新快速模型（默认）
export GEMINI_MODEL="gemini-2.0-flash-exp"

# 稳定版本
export GEMINI_MODEL="gemini-1.5-flash"

# 更强大的模型
export GEMINI_MODEL="gemini-1.5-pro"

# 推理增强版
export GEMINI_MODEL="gemini-2.0-flash-thinking-exp"
```

## ✅ 成功标志

### 规则模式
```
Analysis method:  rule_based
[Note] LLM error: LLM not enabled
```

### LLM 成功
```
Analysis method:  llm
[Note] LLM analysis: OK (model=gemini-2.0-flash-exp)
```

### LLM 降级
```
Analysis method:  rule_based
[Note] LLM error: RuntimeError: GEMINI_API_KEY not set
```

## 🔍 关键修改

### 1. SDK 迁移
```python
# 旧版 ❌
import google.generativeai as genai

# 新版 ✅
import google.genai as genai
```

### 2. 响应解析
```python
# 兼容多种结构
if hasattr(response, 'text'):
    text = response.text
elif hasattr(response, 'candidates') and response.candidates:
    text = response.candidates[0].content.parts[0].text
```

### 3. 错误处理
```python
# 截断长消息
error_msg = str(e)[:100]
```

## 🐛 故障排查

| 问题 | 解决方案 |
|------|----------|
| 404 NOT_FOUND | `export GEMINI_MODEL="gemini-1.5-flash"` |
| JSONDecodeError | 正常 fallback，无需处理 |
| TimeoutError | 检查代理或接受 fallback |
| GEMINI_API_KEY not set | 设置环境变量 |

## 📊 测试结果

```bash
pytest -xvs
# ✅ 103 passed in 0.56s
```

## 📚 文档

- [TEST_GUIDE.md](./TEST_GUIDE.md) - 详细测试指南
- [CHANGES.md](./CHANGES.md) - 完整修改记录
- [quick_test.sh](./quick_test.sh) - 快速测试脚本

## 🎓 使用示例

### 基础用法
```bash
# 1. 规则模式
ai_router_off
python3 demo_news_driven.py

# 2. LLM 模式
ai_router_llm
python3 demo_news_driven.py
```

### 高级用法
```bash
# 自定义模型
export AI_PM_USE_LLM=1
export GEMINI_API_KEY="your_key"
export GEMINI_MODEL="gemini-1.5-pro"
python3 demo_news_driven.py

# 查看配置
echo "LLM: $AI_PM_USE_LLM"
echo "Model: ${GEMINI_MODEL:-gemini-2.0-flash-exp}"
```

## 💡 最佳实践

1. **开发时**：使用规则模式（快速、免费）
2. **演示时**：使用 LLM 模式（展示 AI 能力）
3. **生产时**：配置 fallback（确保稳定性）
4. **调试时**：检查 `[Note]` 行（快速定位问题）

## 🔗 快速链接

```bash
# 进入项目
cd ~/Desktop/ai_quant_router

# 查看帮助
cat QUICK_REFERENCE.md

# 运行测试
./quick_test.sh

# 查看日志
python3 demo_news_driven.py 2>&1 | grep -E "(Analysis|Note|LLM)"
```

---

**最后更新：** 2025-01-11
**状态：** ✅ 生产就绪
**测试覆盖：** 103/103 通过
