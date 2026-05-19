"""使用数据读取器

直接读取 ~/.hermes/skills/.usage.json
不导入 Hermes 核心模块 tools.skill_usage（插件无法访问核心模块）
"""

import json
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

_usage_cache = None
_usage_mtime = 0

def get_usage_data() -> Dict[str, Any]:
    """读取 Hermes 技能使用数据
    
    Returns:
        {skill_name: {use_count, last_used_at, ...}, ...}
    """
    
    global _usage_cache, _usage_mtime
    
    usage_file = Path.home() / '.hermes' / 'skills' / '.usage.json'
    
    if not usage_file.exists():
        return {}
    
    try:
        # 简单的 mtime 缓存
        mtime = usage_file.stat().st_mtime
        if _usage_cache is not None and mtime == _usage_mtime:
            return _usage_cache
        
        with open(usage_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        _usage_cache = data
        _usage_mtime = mtime
        return data
    
    except Exception as e:
        logger.debug("skill-router: usage read failed: %s", e)
        return {}
