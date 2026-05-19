"""
Hermes Skill Router - 核心模块 (v2.0)
实现中文索引支持和本地技能搜索
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple
import bm25s

# ============ Tokenizer 协议（适配器模式）============

class Tokenizer(Protocol):
    """分词器协议，支持 jieba/pkuseg 等替换"""
    def tokenize(self, text: str) -> List[str]:
        """将文本分词为 token 列表"""
        ...


class JiebaTokenizer:
    """jieba 分词器实现（当前首选）"""
    
    # 中文停用词列表（70+词）
    STOPWORDS = {
        # 结构词
        '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
        '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
        '自己', '这', '那', '里', '为', '什么', '他', '她', '它', '们', '这个', '那个',
        # 介词/连词
        '与', '及', '或', '但', '而', '且', '因为', '所以', '如果', '虽然', '但是',
        '然后', '接着', '于是', '因此', '否则', '不过', '而且', '并且',
        # 助词
        '之', '乎', '者', '也', '矣', '焉', '哉', '兮', '吧', '呢', '吗', '啊', '哦',
        '嗯', '呀', '哪', '嘛', '罢', '而已', '罢了',
        # 常见动词/形容词
        '能', '可以', '应该', '必须', '需要', '想', '要', '得', '让', '把', '被',
        '给', '向', '从', '对', '比', '按', '照', '经', '通过', '关于', '对于',
        # 时间词
        '时', '候', '后', '前', '中', '间', '里面', '外面', '上面', '下面', '这里',
        '那里', '哪里', '什么时候', '现在', '已经', '正在', '将', '将要',
        # 数量词
        '些', '多', '少', '几', '第', '两', '二', '三', '四', '五', '六', '七', '八', '九', '十',
        # 其他常见无意义词
        '还', '又', '再', '更', '最', '太', '真', '怎', '怎么', '怎样', '如何', '为何',
        '何', '谁', '哪', '哪里', '哪个', '哪些', '多少', '几时',
    }
    
    # 技术词汇自定义词典
    TECH_WORDS = [
        '技能', '路由', 'API', 'Hook', 'HTTP', 'HTTPS', 'URL', 'JSON', 'YAML',
        'Python', 'JavaScript', 'TypeScript', 'Node', 'React', 'Vue', 'Angular',
        'Git', 'GitHub', 'GitLab', 'Docker', 'Kubernetes', 'K8s', 'Linux', 'Shell',
        'SQL', 'NoSQL', 'MongoDB', 'PostgreSQL', 'MySQL', 'Redis', 'Elasticsearch',
        'BM25', 'RAG', 'LLM', 'GPT', 'Claude', 'AI', 'ML', 'DL', 'NLP', 'CV',
        'OCR', 'PDF', 'CSV', 'Excel', 'Word', 'PowerPoint', 'Markdown', 'HTML',
        'CSS', 'REST', 'GraphQL', 'WebSocket', 'gRPC', 'MQTT', 'Kafka', 'RabbitMQ',
        'JWT', 'OAuth', 'SAML', 'LDAP', 'SSO', 'MFA', 'TLS', 'SSL', 'SSH', 'FTP',
        'S3', 'EC2', 'Lambda', 'Azure', 'GCP', 'AWS', 'Terraform', 'Ansible',
        'Jenkins', 'GitHub Actions', 'CI', 'CD', 'DevOps', 'SRE', 'KPI', 'SLA',
        '测试', '部署', '监控', '日志', '报警', '优化', '重构', '调试', '分析',
        '设计', '架构', '模式', '算法', '数据结构', '性能', '安全', '漏洞',
        '扫描', '攻击', '防御', '渗透', '逆向', '加密', '解密', '哈希', '签名',
    ]
    
    def __init__(self):
        """初始化 jieba 分词器"""
        import jieba
        self._jieba = jieba
        
        # 添加技术词汇到词典
        for word in self.TECH_WORDS:
            self._jieba.add_word(word)
    
    def tokenize(self, text: str) -> List[str]:
        """分词并过滤停用词"""
        tokens = list(self._jieba.cut(text))
        # 过滤停用词和空白
        return [t for t in tokens if t.strip() and t not in self.STOPWORDS]


# ============ SkillRouter 核心类 ============

class SkillRouter:
    """技能路由器（BM25 + jieba 中文支持）"""
    
    def __init__(self, skills_dir: Optional[Path] = None, tokenizer: Optional[Tokenizer] = None):
        """
        初始化路由器
        
        Args:
            skills_dir: 技能目录路径，默认 ~/.hermes/skills/
            tokenizer: 分词器实例，默认 JiebaTokenizer
        """
        self.skills_dir = skills_dir or Path.home() / '.hermes' / 'skills'
        self.tokenizer = tokenizer or JiebaTokenizer()
        
        # 缓存
        self._indexer = None
        self._skills_data: List[Dict] = []
        self._content_hash: str = ""
        self._usage_data: Dict = {}
        
        # 网络客户端（延迟初始化）
        self._network_client = None
    
    def _compute_hash(self) -> str:
        """计算技能目录内容哈希，用于检测变化"""
        skill_hashes = []
        
        for skill_md in sorted(self.skills_dir.rglob('SKILL.md')):
            try:
                content = skill_md.read_text(encoding='utf-8')
                h = hashlib.md5(content.encode()).hexdigest()[:8]
                relative = skill_md.relative_to(self.skills_dir)
                skill_hashes.append(f"{relative}:{h}")
            except Exception:
                continue
        
        # 包含 usage 数据的哈希
        usage_file = self.skills_dir / '.usage.json'
        if usage_file.exists():
            try:
                usage_hash = hashlib.md5(usage_file.read_bytes()).hexdigest()[:8]
                skill_hashes.append(f"usage:{usage_hash}")
            except Exception:
                pass
        
        return hashlib.md5("|".join(skill_hashes).encode()).hexdigest()
    
    def _load_usage_data(self) -> Dict:
        """加载使用数据"""
        usage_file = self.skills_dir / '.usage.json'
        if usage_file.exists():
            try:
                return json.loads(usage_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        return {}
    
    def _scan_skills(self) -> List[Dict]:
        """扫描技能目录，读取 SKILL.md 元数据"""
        skills = []
        
        for skill_md in self.skills_dir.rglob('SKILL.md'):
            try:
                content = skill_md.read_text(encoding='utf-8')
                
                # 解析 YAML frontmatter
                metadata = self._parse_frontmatter(content)
                
                # 获取技能路径
                skill_path = skill_md.parent
                skill_name = str(skill_path.relative_to(self.skills_dir))
                
                # 构建索引文本
                index_text = self._build_index_text(skill_name, metadata, content)
                
                skills.append({
                    'name': metadata.get('name', skill_name),
                    'description': metadata.get('description', ''),
                    'tags': metadata.get('tags', []),
                    'path': str(skill_path),
                    'text': index_text,
                })
            except Exception as e:
                continue
        
        return skills
    
    def _parse_frontmatter(self, content: str) -> Dict:
        """解析 YAML frontmatter"""
        metadata = {}
        
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    metadata = yaml.safe_load(parts[1]) or {}
                except Exception:
                    pass
        
        return metadata
    
    def _build_index_text(self, name: str, metadata: Dict, content: str) -> str:
        """构建索引文本（用于 BM25）"""
        parts = [
            name,
            metadata.get('name', ''),
            metadata.get('description', ''),
            ' '.join(metadata.get('tags', [])),
        ]
        
        # 提取正文前 500 字符
        if '---' in content:
            body_start = content.find('---', 3) + 3
            body = content[body_start:].strip()[:500]
            parts.append(body)
        
        return ' '.join(p for p in parts if p)
    
    def _build_index(self) -> bool:
        """使用 jieba 预分词 + bm25s 建立索引"""
        skills = self._scan_skills()
        
        if not skills:
            return False
        
        # 构建语料库
        corpus = [skill['text'] for skill in skills]
        
        # jieba 预分词（关键：分词后用空格连接）
        tokenized_corpus = []
        for text in corpus:
            tokens = self.tokenizer.tokenize(text)
            tokenized_corpus.append(' '.join(tokens))
        
        # bm25s 索引（stopwords=[] 因为已预处理）
        corpus_tokens = bm25s.tokenize(tokenized_corpus, stopwords=[])
        
        self._indexer = bm25s.BM25(corpus=skills)
        self._indexer.index(corpus_tokens)
        
        self._skills_data = skills
        self._content_hash = self._compute_hash()
        self._usage_data = self._load_usage_data()
        
        return True
    
    def _ensure_index(self) -> bool:
        """确保索引可用（自动检测变化重建）"""
        current_hash = self._compute_hash()
        
        if self._indexer is not None and current_hash == self._content_hash:
            return True
        
        return self._build_index()
    
    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        本地搜索技能
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            匹配结果列表，每项包含 skill 和 score
        """
        if not self._ensure_index():
            return []
        
        # jieba 预分词查询
        query_tokens = self.tokenizer.tokenize(query)
        query_text = ' '.join(query_tokens)
        
        # bm25s 检索
        query_tokens_bm25 = bm25s.tokenize([query_text], stopwords=[])
        results, scores = self._indexer.retrieve(query_tokens_bm25, k=top_k)
        
        # 格式化结果
        matched = []
        for i in range(min(top_k, len(results[0]))):
            skill = results[0, i]
            score = float(scores[0, i])
            
            if skill and score > 0:
                # 添加使用数据
                skill_name = skill.get('name', '')
                usage = self._usage_data.get(skill_name, {})
                
                matched.append({
                    'skill': skill,
                    'score': score,
                    'source': 'local',
                    'use_count': usage.get('use_count', 0),
                })
        
        return matched
    
    def search_with_network(self, query: str, top_k: int = 3, timeout: float = 2.0) -> List[Dict]:
        """
        混合搜索：本地 + 网络（本地优先，网络可降级）
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            timeout: 网络超时（秒）
            
        Returns:
            匹配结果列表，本地优先
        """
        import asyncio
        
        # 1. 本地搜索（核心，必须成功）
        local_results = self.search(query, top_k=top_k)
        
        # 2. 网络搜索（增强，可降级）
        network_results = []
        try:
            from .network import NetworkSkillClient
            
            if self._network_client is None:
                self._network_client = NetworkSkillClient()
            
            # 异步搜索
            network_results = asyncio.run(
                self._network_client.search_skills(query, page_size=top_k, timeout=timeout)
            )
        except Exception:
            # 降级：网络失败不影响本地结果
            network_results = []
        
        # 3. 合并结果（本地优先，去重）
        seen_names = set()
        combined = []
        
        for r in local_results:
            name = r.get('skill', {}).get('name', '')
            if name and name not in seen_names:
                seen_names.add(name)
                combined.append(r)
        
        for r in network_results:
            name = r.get('skill', {}).get('name', '')
            if name and name not in seen_names:
                seen_names.add(name)
                combined.append(r)
        
        return combined[:top_k * 2]  # 最多返回 top_k * 2
    
    def close(self):
        """清理资源"""
        if self._network_client:
            import asyncio
            try:
                asyncio.run(self._network_client.close())
            except Exception:
                pass
            self._network_client = None


# ============ 全局缓存实例 ============

_ROUTER_CACHE: Optional[SkillRouter] = None
_ROUTER_HASH: str = ""


def get_cached_router() -> Optional[SkillRouter]:
    """获取缓存的路由器实例"""
    global _ROUTER_CACHE, _ROUTER_HASH
    
    skills_dir = Path.home() / '.hermes' / 'skills'
    router = SkillRouter(skills_dir)
    current_hash = router._compute_hash()
    
    if _ROUTER_CACHE is not None and current_hash == _ROUTER_HASH:
        return _ROUTER_CACHE
    
    # 重建索引
    if router._build_index():
        _ROUTER_CACHE = router
        _ROUTER_HASH = current_hash
        return _ROUTER_CACHE
    
    return None