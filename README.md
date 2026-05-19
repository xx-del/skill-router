# Skill Router - 技能智能路由器

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![bm25s](https://img.shields.io/badge/engine-bm25s-green.svg)](https://github.com/xhluca/bm25s)

**Hermes Agent 插件**：基于 BM25 算法的技能智能路由器，自动分析用户消息，推荐相关技能。

---

## 特性

- ⚡ **高性能**：首次 ~135ms，缓存后 ~5ms
- 🎯 **高准确率**：Hit@1 59%, Hit@3 82%
- 🔄 **完全自动化**：安装即生效，零配置
- 📦 **动态索引**：实时读取技能目录，自动更新
- 🔒 **零侵入**：不修改 Hermes 源代码

---

## 工作原理

```
用户消息
    ↓
pre_llm_call Hook 触发
    ↓
BM25 查询 Top 3 匹配技能
    ↓
返回 {"context": "推荐技能..."}
    ↓
Hermes 注入到用户消息末尾
    ↓
LLM 看到推荐技能
```

---

## 安装

### 前置要求

- Hermes Agent >= 0.13.0
- Python >= 3.8
- bm25s >= 0.3.0

### 方法 1：直接安装

```bash
# 1. 安装依赖
pip install 'bm25s>=0.3.0' PyYAML

# 2. 克隆仓库
git clone https://github.com/your-username/skill-router.git

# 3. 复制到 Hermes 插件目录
cp -r skill-router ~/.hermes/plugins/

# 4. 重启 Hermes
hermes gateway restart  # 或重启 CLI
```

### 方法 2：从 GitHub 安装

```bash
# 1. 安装依赖
pip install 'bm25s>=0.3.0' PyYAML

# 2. 直接克隆到插件目录
cd ~/.hermes/plugins
git clone https://github.com/your-username/skill-router.git

# 3. 重启 Hermes
hermes gateway restart
```

---

## 使用

安装后自动生效，无需配置。

### 示例

用户输入：
```
分析网站性能
```

LLM 看到的上下文：
```
[SKILL_ROUTER]
## 🎯 推荐技能

根据您的任务，智能推荐以下技能：

1. **dogfood** (匹配分数: 0.85)
   - 描述: Exploratory QA of web apps: find bugs, evidence, r...
   - 使用次数: 42

2. **deep-thinking** (匹配分数: 0.78)
   - 描述: Comprehensive deep reasoning framework that guides...
   - 使用次数: 45

3. **webapp-testing** (匹配分数: 0.72)
   - 描述: Exploratory QA of web apps...
   - 使用次数: 15
```

---

## 配置

编辑 `plugin.yaml`：

```yaml
settings:
  max_recommendations: 3      # 最多推荐技能数
  min_score: 0.3              # 最低匹配分数
  context_prefix: "[SKILL_ROUTER]"  # 上下文前缀
```

---

## 测试

```bash
cd ~/.hermes/plugins/skill-router

# 运行基准测试
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('benchmark', 'benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

result = benchmark.run_benchmark()
print(f'Hit@1: {result[\"hit@1_rate\"]:.1%}')
print(f'Hit@3: {result[\"hit@3_rate\"]:.1%}')
"

# 测试单个查询
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('scanner', 'scanner.py')
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)

spec2 = importlib.util.spec_from_file_location('indexer', 'indexer.py')
indexer = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(indexer)

skills = scanner.scan_skills()
idx = indexer.SkillIndexer()
idx.index(skills)

results = idx.query('分析网站性能', top_k=3)
for skill, score in results:
    print(f'{skill[\"name\"]}: {score:.2f}')
"
```

---

## 基准测试结果

| 指标 | 结果 | 目标 |
|------|------|------|
| **Hit@1** | 59.0% | ≥ 50% ✅ |
| **Hit@3** | 82.1% | ≥ 75% ✅ |

---

## 性能

| 操作 | 首次 | 缓存命中 |
|------|------|----------|
| 扫描技能目录 | ~20ms | - |
| 解析 SKILL.md | ~50ms | - |
| 建立 BM25 索引 | ~50ms | - |
| 查询匹配 | ~5ms | ~5ms |
| **总延迟** | **~135ms** | **~5ms** |

---

## 文件结构

```
skill-router/
├── __init__.py      # 插件入口（register函数）
├── plugin.yaml      # 插件配置
├── hook.py          # pre_llm_call 回调
├── scanner.py       # 动态技能扫描
├── indexer.py       # BM25 索引器
├── cache.py         # 内容哈希缓存
├── usage_reader.py  # 使用数据读取
├── benchmark.py     # 基准测试
├── test_cases.json  # 测试用例
├── .gitignore       # Git 忽略规则
└── README.md        # 本文档
```

---

## 技术细节

### 核心引擎

- **bm25s v0.3.0+**：500x 快于 rank_bm25
- 稀疏矩阵存储，低内存 (~1MB for 250 skills)
- 纯 Python，无跨语言开销

### Hook API

完全对齐 Hermes 官方 API：

```python
def on_user_message(
    session_id: str,
    user_message: str,
    conversation_history: List[Dict],
    is_first_turn: bool,
    model: str,
    platform: str,
    sender_id: str = "",
    **kwargs
) -> Optional[Dict[str, str]]:
    # ...
    return {"context": "推荐技能..."}
```

### 缓存机制

- 使用**内容哈希**（非 mtime）作为缓存键
- 技能目录变化时自动重建索引
- 跨会话复用缓存

---

## 与 Hermes 现有机制的关系

| Hermes 机制 | 插件操作 | 关系 |
|-------------|----------|------|
| skill_usage.py | 不使用 | 避免 import 核心模块 |
| .usage.json | 只读 | 直接读取 JSON |
| pre_llm_call Hook | 使用 | 官方支持 |
| find-skills 技能 | 互补 | 手动 vs 自动 |

---

## 禁用

```bash
# 方法 1：重命名配置文件
mv ~/.hermes/plugins/skill-router/plugin.yaml ~/.hermes/plugins/skill-router/plugin.yaml.disabled

# 方法 2：删除插件目录
rm -rf ~/.hermes/plugins/skill-router

# 重启 Hermes
hermes gateway restart
```

---

## 故障排查

### 插件未生效

1. 检查 Gateway 是否重启：`hermes gateway restart`
2. 检查插件目录：`ls ~/.hermes/plugins/skill-router/`
3. 检查日志：`hermes logs | grep skill-router`

### 匹配不准确

1. 调整 `plugin.yaml` 中的 `min_score` 阈值
2. 优化查询关键词（使用描述性词汇）
3. 检查技能目录是否有 SKILL.md

### 依赖缺失

```bash
pip install 'bm25s>=0.3.0' PyYAML
```

---

## 开发

### 添加测试用例

编辑 `test_cases.json`：

```json
[
  {"query": "查询描述", "expected": ["skill-name-1", "skill-name-2"]}
]
```

### 调整权重

编辑 `scanner.py` 中的检索文本构建：

```python
# 当前：标签重复2次
'text': f"{description} {' '.join(tags)} {' '.join(tags)}"

# 可调整：标签重复3次
'text': f"{description} {' '.join(tags)} {' '.join(tags)} {' '.join(tags)}"
```

---

## 后续优化

### Phase 2（可选）

1. **混合检索**：BM25 + 向量相似度（提升语义匹配）
2. **项目上下文**：扫描项目技术栈，增强感知维度
3. **增量索引**：监听文件变化，减少扫描开销

---

## 参考

### 核心引擎

- [bm25s](https://github.com/xhluca/bm25s) - Fast BM25 in pure Python
- [bm25s 论文](https://arxiv.org/abs/2407.03618) - BM25S: Orders of magnitude faster lexical search

### 学术研究

- [SkillRouter (Alibaba)](https://arxiv.org/abs/2603.22455) - 两阶段检索-重排
- [SkillReducer](https://arxiv.org/abs/2603.29919) - 技能 token 优化

---

## 许可证

MIT License

---

## 贡献

欢迎提交 Issue 和 Pull Request。

---

## 作者

OpenClaw Team
