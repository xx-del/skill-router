"""BM25 技能索引器

使用 bm25s >= 0.3.0（arXiv:2407.03618）
- 500x 快于 rank_bm25
- 稀疏矩阵存储，低内存
- 纯 Python，仅依赖 Numpy + Scipy
"""

import bm25s
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class SkillIndexer:
    """BM25 技能索引器"""
    
    def __init__(self):
        self.retriever = None
        self.corpus = []
        self.skills = []
    
    def index(self, skills: List[Dict]) -> None:
        """索引技能列表
        
        Args:
            skills: scanner.scan_skills() 返回的技能列表
        """
        
        self.skills = skills
        self.corpus = [skill['text'] for skill in skills]
        
        # 分词并索引
        corpus_tokens = bm25s.tokenize(self.corpus, stopwords='en')
        
        # 传入 corpus 参数，使 retrieve 直接返回文档内容
        self.retriever = bm25s.BM25(corpus=self.corpus)
        self.retriever.index(corpus_tokens)
        
        logger.debug("skill-router: indexed %d skills", len(skills))
    
    def query(self, user_message: str, top_k: int = 3) -> List[Tuple[Dict, float]]:
        """查询匹配技能
        
        Args:
            user_message: 用户消息
            top_k: 返回前 K 个匹配
        
        Returns:
            [(skill_dict, score), ...] 列表
        """
        
        if not self.retriever or not self.corpus:
            return []
        
        # 分词并查询
        query_tokens = bm25s.tokenize([user_message], stopwords='en')
        results, scores = self.retriever.retrieve(query_tokens, k=min(top_k, len(self.corpus)))
        
        # 解析结果
        matched = []
        for i in range(results.shape[1]):
            doc = results[0, i]  # 直接是原始 corpus 项（因为创建时传了 corpus）
            score = float(scores[0, i])
            
            # 找到对应的技能
            try:
                idx = self.corpus.index(doc)
                skill = self.skills[idx]
                matched.append((skill, score))
            except ValueError:
                continue
        
        return matched
