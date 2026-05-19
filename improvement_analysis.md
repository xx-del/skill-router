# skill-router 插件改进方向深度分析

**分析日期**：2026-05-19  
**分析方法**：Deep Thinking Protocol  
**当前状态**：Hit@1 59%, Hit@3 82%

---

## 1. 问题分析

### 1.1 当前方案的根本局限

#### 核心问题：BM25 的词袋模型本质

BM25 算法基于词频统计（TF-IDF 变体），存在以下根本局限：

| 局限类型 | 具体表现 | 影响 |
|---------|---------|------|
| **无语义理解** | "LLM training" ≠ "model fine-tuning" | 同义表达无法匹配 |
| **词汇鸿沟** | "debug" 无法匹配 "troubleshooting" | 用户表达多样性导致漏检 |
| **词序无关** | "web search" = "search web" | 无法区分意图差异 |
| **长尾词惩罚** | 低频专业术语得分低 | 专业技能召回困难 |
| **跨语言障碍** | 中文查询无法匹配英文描述 | 多语言支持缺失 |

#### 实证分析：失败案例分析

从 test_cases.json 分析典型失败模式：

```
查询: "parallel agent execution"
期望: agent-pool, agent-team-orchestration
实际: 可能匹配不到（因为 SKILL.md 描述可能是 "concurrent task distribution"）
```

**根本原因**：用户查询词汇与技能描述词汇不重叠，但语义相同。

### 1.2 中文支持的深层障碍

#### 当前状态

- 测试用例：39/39 英文（0% 中文）
- 技能描述：中英文混合
- 分词器：bm25s.tokenize(stopwords='en') — 英文停用词

#### 中文支持的三个层次

| 层次 | 方案 | 效果预期 | 复杂度 |
|-----|------|---------|--------|
| **L1: 字符匹配** | 直接使用中文查询 | 30-40% Hit@1 | 低 |
| **L2: 中文分词** | jieba/pkuseg 分词 | 45-55% Hit@1 | 中 |
| **L3: 语义检索** | 向量模型（多语言） | 70-80% Hit@1 | 高 |

**关键洞察**：中文分词仅解决切分问题，无法解决语义鸿沟。真正的解决方案是向量检索。

### 1.3 架构层面的设计问题

#### 问题 1：重复实现

```python
# scanner.py 直接扫描目录
skills_dir = Path.home() / '.hermes' / 'skills'
for skill_md in skills_dir.rglob('SKILL.md'):
    ...
```

**对比 find-skills 技能**：
- find-skills 使用 `npx skills find` 命令
- 提供标准化搜索接口
- 支持远程技能库搜索

**问题**：skill-router 重复实现了技能发现逻辑，未复用 Hermes 生态。

#### 问题 2：静态索引

```python
# cache.py 基于内容哈希
def compute_hash(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()
```

**局限**：
- 技能新增/删除需要重启 Gateway
- 无法感知技能热更新
- 无增量索引机制

#### 问题 3：单一检索路径

当前架构：
```
用户查询 → BM25 → Top-K 技能
```

理想架构：
```
用户查询 → [BM25, 向量检索, 规则匹配] → 融合排序 → Top-K 技能
```

---

## 2. 改进方案

### 方案 A：渐进式优化（低风险，快速见效）

#### A1: 查询扩展 + 同义词注入

**原理**：在 BM25 索引前，扩展查询词汇。

```python
# 同义词词典（可从 WordNet 或手工构建）
SYNONYMS = {
    "debug": ["troubleshoot", "fix", "diagnose"],
    "LLM": ["language model", "GPT", "transformer"],
    "web": ["internet", "online", "http"],
    ...
}

def expand_query(query: str) -> str:
    words = query.split()
    expanded = []
    for word in words:
        expanded.append(word)
        if word in SYNONYMS:
            expanded.extend(SYNONYMS[word])
    return " ".join(expanded)
```

**预期收益**：Hit@1 提升至 65-70%

**实施成本**：低（~100 行代码 + 同义词词典）

#### A2: 技能描述增强

**原理**：在 SKILL.md 解析时，自动添加关键词。

```python
def enhance_skill_text(skill: Dict) -> str:
    text = skill['description']
    tags = skill.get('tags', [])
    
    # 添加标签（重复加权）
    text += " " + " ".join(tags) * 2
    
    # 添加技能名称（用户可能直接输入技能名）
    text += " " + skill['name']
    
    # 添加常见别名（从别名库）
    aliases = ALIAS_DB.get(skill['name'], [])
    text += " " + " ".join(aliases)
    
    return text
```

**预期收益**：Hit@1 提升至 68-72%

#### A3: 中文分词支持

```python
import jieba

def tokenize_chinese(text: str) -> List[str]:
    # 混合分词：中文用 jieba，英文按空格
    if any('\u4e00' <= ch <= '\u9fff' for ch in text):
        return list(jieba.cut(text))
    else:
        return text.split()
```

**预期收益**：中文查询 Hit@1 达到 45-55%

---

### 方案 B：混合检索（中等风险，显著提升）

#### B1: BM25 + 向量检索融合

**架构**：
```
用户查询
    ├─→ BM25 检索 → Top-50 候选
    ├─→ 向量检索 → Top-50 候选
    └─→ 融合排序（RRF） → Top-3 结果
```

**融合算法：Reciprocal Rank Fusion (RRF)**

```python
def rrf_fusion(bm25_results, vector_results, k=60):
    """
    RRF 公式：score(d) = Σ 1/(k + rank(d))
    """
    scores = defaultdict(float)
    
    for rank, (doc, _) in enumerate(bm25_results):
        scores[doc] += 1 / (k + rank)
    
    for rank, (doc, _) in enumerate(vector_results):
        scores[doc] += 1 / (k + rank)
    
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

**向量模型选择**：

| 模型 | 维度 | 多语言 | 速度 | 推荐度 |
|-----|------|--------|------|--------|
| all-MiniLM-L6-v2 | 384 | ❌ | 快 | ⭐⭐⭐ |
| paraphrase-multilingual-MiniLM | 384 | ✅ | 中 | ⭐⭐⭐⭐⭐ |
| bge-m3 | 1024 | ✅ | 慢 | ⭐⭐⭐⭐ |

**推荐**：paraphrase-multilingual-MiniLM（支持中英文，轻量级）

**预期收益**：
- 英文查询：Hit@1 提升至 75-80%
- 中文查询：Hit@1 提升至 65-70%

**实施成本**：中（~300 行代码 + 向量模型加载）

#### B2: 向量索引复用 Hermes 机制

**关键发现**：Hermes 已有向量存储组件！

```
~/.hermes/skills/openclaw-imports/agent-pool/src/
├── embedding.py      # Ollama API 嵌入
├── vector_store.py   # SQLite 向量存储
└── vector_indexer.py # 向量索引
```

**整合方案**：

```python
# 复用 agent-pool 的 embedding 模块
from agent_pool.src.embedding import get_embedding

# 或使用 sentence-transformers（已安装）
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
```

**优势**：
- 避免重复实现
- 与 Hermes 生态一致
- 共享向量缓存

---

### 方案 C：智能路由增强（高风险，最大收益）

#### C1: 查询意图分类

**原理**：先识别查询类型，再选择检索策略。

```python
INTENT_PATTERNS = {
    "技能发现": ["how do I", "find a skill", "is there a skill"],
    "任务执行": ["帮我", "create", "analyze", "debug"],
    "知识查询": ["what is", "explain", "tell me about"],
}

def classify_intent(query: str) -> str:
    for intent, patterns in INTENT_PATTERNS.items():
        if any(p in query.lower() for p in patterns):
            return intent
    return "通用"
```

**策略路由**：
- 技能发现 → 调用 find-skills 技能
- 任务执行 → BM25 + 向量检索
- 知识查询 → 向量检索优先

#### C2: 使用历史学习

**原理**：基于用户历史选择优化排序。

```python
def personalize_ranking(candidates, user_history):
    """
    根据用户历史使用频率调整排序
    """
    for skill, score in candidates:
        use_count = user_history.get(skill['name'], 0)
        # 使用频率加权
        score *= (1 + 0.1 * min(use_count, 10))
    return sorted(candidates, key=lambda x: x[1], reverse=True)
```

#### C3: 反馈学习机制

```python
# 用户选择记录
def record_selection(query, selected_skill, rejected_skills):
    """
    记录用户选择，用于后续优化
    """
    # 存储到 ~/.hermes/plugins/skill-router/feedback.json
    ...

# 定期重训练（可选）
def retrain_from_feedback():
    """
    从反馈数据学习查询-技能映射
    """
    ...
```

**预期收益**：Hit@1 提升至 80-85%（长期）

---

## 3. 实施优先级

### 阶段 1：快速优化（1-2 天）

| 任务 | 收益 | 成本 | 优先级 |
|-----|------|------|--------|
| A1: 查询扩展 | +5-10% Hit@1 | 低 | P0 |
| A2: 描述增强 | +3-5% Hit@1 | 低 | P0 |
| A3: 中文分词 | 中文支持 | 低 | P1 |

**实施顺序**：
1. 添加同义词词典（从 WordNet 或手工构建）
2. 修改 indexer.py 添加查询扩展
3. 修改 scanner.py 增强描述文本
4. 添加 jieba 分词支持

### 阶段 2：混合检索（3-5 天）

| 任务 | 收益 | 成本 | 优先级 |
|-----|------|------|--------|
| B1: BM25+向量融合 | +15-20% Hit@1 | 中 | P0 |
| B2: 复用 Hermes 向量组件 | 架构优化 | 中 | P1 |

**实施顺序**：
1. 加载 sentence-transformers 模型
2. 实现向量索引器
3. 实现 RRF 融合算法
4. 添加配置开关（BM25/向量/混合）

### 阶段 3：智能增强（1-2 周）

| 任务 | 收益 | 成本 | 优先级 |
|-----|------|------|--------|
| C1: 意图分类 | 精准路由 | 中 | P2 |
| C2: 使用历史学习 | 个性化 | 中 | P2 |
| C3: 反馈机制 | 长期优化 | 高 | P3 |

---

## 4. 预期收益

### 准确率提升路线图

```
当前:  Hit@1 59%, Hit@3 82%
  ↓
阶段1: Hit@1 68%, Hit@3 88%  (查询扩展 + 描述增强)
  ↓
阶段2: Hit@1 78%, Hit@3 92%  (混合检索)
  ↓
阶段3: Hit@1 85%, Hit@3 95%  (智能路由 + 个性化)
```

### 多语言支持

| 语言 | 当前 | 阶段1 | 阶段2 | 阶段3 |
|-----|------|-------|-------|-------|
| 英文 | 59% | 68% | 78% | 85% |
| 中文 | N/A | 45% | 68% | 75% |

### 性能影响

| 方案 | 延迟增加 | 内存增加 |
|-----|---------|---------|
| A1-A3 | +5ms | +10MB |
| B1 | +50ms | +200MB |
| C1-C3 | +10ms | +50MB |

---

## 5. 架构整合建议

### 5.1 复用 Hermes 现有机制

#### 技能发现：调用 find-skills 技能

```python
# 当前：直接扫描目录
skills = scan_skills()

# 改进：复用 find-skills 技能
import subprocess
result = subprocess.run(
    ["npx", "skills", "find", "--all"],
    capture_output=True, text=True
)
skills = parse_skills_output(result.stdout)
```

#### 向量存储：复用 agent-pool 组件

```python
# 当前：自实现 BM25 索引
from .indexer import SkillIndexer

# 改进：复用 agent-pool 向量存储
import sys
sys.path.insert(0, str(Path.home() / '.hermes/skills/openclaw-imports/agent-pool/src'))
from vector_store import VectorStore
from embedding import get_embedding
```

### 5.2 配置化设计

```yaml
# plugin.yaml
settings:
  # 检索模式
  retrieval_mode: "hybrid"  # bm25 / vector / hybrid
  
  # 向量模型
  embedding_model: "paraphrase-multilingual-MiniLM-L12-v2"
  
  # 融合权重
  bm25_weight: 0.4
  vector_weight: 0.6
  
  # 中文支持
  chinese_segmentation: true
  chinese_segmenter: "jieba"
  
  # 个性化
  use_history: true
  history_weight: 0.2
```

### 5.3 热更新机制

```python
# 监听技能目录变化
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class SkillUpdateHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('SKILL.md'):
            self.indexer.rebuild_index()

observer = Observer()
observer.schedule(SkillUpdateHandler(), str(skills_dir), recursive=True)
observer.start()
```

---

## 6. 风险评估

| 风险 | 影响 | 缓解措施 |
|-----|------|---------|
| 向量模型加载慢 | 首次启动延迟 | 异步加载 + 缓存 |
| 内存占用增加 | Gateway 负载 | 量化模型 + 索引压缩 |
| 依赖冲突 | 环境不稳定 | 虚拟环境隔离 |
| 过度优化 | 泛化能力下降 | 保留 BM25 作为兜底 |

---

## 7. 结论

### 核心洞察

1. **BM25 的根本局限是语义鸿沟**，而非算法本身
2. **向量检索是突破瓶颈的关键**，且 Hermes 已有基础设施
3. **复用优于重造**，应整合 find-skills 和 agent-pool 组件
4. **渐进式优化**，先快速见效，再深度改造

### 推荐实施路径

```
Week 1: A1 + A2 + A3  →  快速提升至 68%
Week 2: B1 + B2       →  混合检索达 78%
Week 3: C1 + C2       →  智能路由达 85%
```

### 关键成功因素

1. **保持轻量级**：优先使用已安装的 sentence-transformers
2. **不修改 Hermes 源码**：通过插件机制扩展
3. **复用现有组件**：agent-pool 的向量存储、find-skills 的搜索接口
4. **渐进式验证**：每个阶段都运行 benchmark.py 验证收益

---

**分析完成**：2026-05-19  
**下一步**：等待用户确认后开始实施阶段 1
