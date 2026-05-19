"""内容哈希缓存

使用技能目录内容哈希作为缓存键（而非 mtime），避免：
1. mtime 精度问题
2. 新增技能目录未触发更新
"""

from pathlib import Path
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 全局缓存
_indexer_cache = None
_cache_hash = ""

def _compute_skills_hash() -> str:
    """计算技能目录内容哈希"""
    
    skills_dir = Path.home() / '.hermes' / 'skills'
    
    if not skills_dir.exists():
        return ""
    
    skill_hashes = []
    for skill_md in sorted(skills_dir.rglob('SKILL.md')):
        # 跳过备份目录
        if '.backup' in skill_md.parts or '.bk' in skill_md.parts or '.archive' in skill_md.parts:
            continue
        
        try:
            content = skill_md.read_text(encoding='utf-8')
            h = hashlib.md5(content.encode()).hexdigest()[:8]
            skill_hashes.append(f"{skill_md.relative_to(skills_dir)}:{h}")
        except Exception:
            continue
    
    total = "|".join(skill_hashes)
    return hashlib.md5(total.encode()).hexdigest()

def get_cached_indexer():
    """获取缓存的索引器
    
    Returns:
        SkillIndexer 实例或 None
    """
    
    global _indexer_cache, _cache_hash
    
    current_hash = _compute_skills_hash()
    
    # 内容未变化，使用缓存
    if _indexer_cache is not None and current_hash == _cache_hash:
        return _indexer_cache
    
    # 重建索引
    from .scanner import scan_skills
    from .indexer import SkillIndexer
    
    skills = scan_skills()
    if not skills:
        return None
    
    try:
        _indexer_cache = SkillIndexer()
        _indexer_cache.index(skills)
        _cache_hash = current_hash
        
        logger.info("skill-router: rebuilt index (%d skills, hash=%s)", len(skills), current_hash[:8])
    except Exception as e:
        logger.error("skill-router: index build failed: %s", e)
        return None
    
    return _indexer_cache

def invalidate_cache():
    """手动使缓存失效"""
    
    global _indexer_cache, _cache_hash
    _indexer_cache = None
    _cache_hash = ""
