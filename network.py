"""
Hermes Skill Router - 网络模块 (v2.0)
实现 skills.sh API 集成和降级处理
"""

import aiohttp
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional


class NetworkSkillClient:
    """网络技能库客户端（skills.sh API）"""
    
    API_ENDPOINT = "https://skills-api.mastra.cloud/api/skills"
    CACHE_TTL = 6 * 60 * 60  # 6小时缓存
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        初始化客户端
        
        Args:
            cache_dir: 缓存目录，默认 ~/.hermes/plugins/skill-router/
        """
        self.cache_dir = cache_dir or Path.home() / '.hermes' / 'plugins' / 'skill-router'
        self.cache_file = self.cache_dir / 'network_cache.json'
        self._session: Optional[aiohttp.ClientSession] = None
        
        # 确保目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def _load_cache(self) -> Dict:
        """加载本地缓存"""
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text(encoding='utf-8'))
                cached_at = data.get('cached_at', 0)
                
                # 检查 TTL
                if time.time() - cached_at < self.CACHE_TTL:
                    return data
            except Exception:
                pass
        return {}
    
    def _save_cache(self, data: Dict):
        """保存缓存"""
        try:
            data['cached_at'] = time.time()
            self.cache_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception:
            pass
    
    async def search_skills(
        self,
        query: str,
        page_size: int = 10,
        timeout: float = 2.0
    ) -> List[Dict]:
        """
        异步搜索 skills.sh API
        
        Args:
            query: 查询文本
            page_size: 返回结果数量（注意：API 使用 pageSize 驼峰式）
            timeout: 超时时间（秒）
            
        Returns:
            匹配结果列表，失败返回空列表
        """
        # 1. 尝试使用缓存
        cache = self._load_cache()
        cache_key = f"{query}:{page_size}"
        
        if cache_key in cache.get('results', {}):
            return cache['results'][cache_key]
        
        # 2. 网络请求
        try:
            session = await self._get_session()
            
            # API 参数使用 pageSize（驼峰式）
            params = {
                'query': query,
                'pageSize': page_size,
            }
            
            timeout_config = aiohttp.ClientTimeout(total=timeout)
            
            async with session.get(
                self.API_ENDPOINT,
                params=params,
                timeout=timeout_config
            ) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                
                # 解析结果
                results = self._parse_response(data)
                
                # 缓存结果
                if 'results' not in cache:
                    cache['results'] = {}
                cache['results'][cache_key] = results
                self._save_cache(cache)
                
                return results
                
        except asyncio.TimeoutError:
            # 超时降级
            return []
        except aiohttp.ClientError:
            # 网络错误降级
            return []
        except Exception:
            # 其他异常降级
            return []
    
    def _parse_response(self, data: Dict) -> List[Dict]:
        """解析 API 响应"""
        results = []
        
        # skills.sh API 响应格式
        skills = data.get('skills', []) or data.get('results', []) or []
        
        for skill in skills:
            # 提取技能信息
            name = skill.get('name', '') or skill.get('skillName', '')
            description = skill.get('description', '') or skill.get('summary', '')
            tags = skill.get('tags', [])
            
            if name:
                results.append({
                    'skill': {
                        'name': name,
                        'description': description,
                        'tags': tags,
                        'url': skill.get('url', ''),
                        'author': skill.get('author', ''),
                    },
                    'score': skill.get('score', 0.5),
                    'source': 'network',
                })
        
        return results


# ============ 同步包装器 ============

def search_skills_sync(
    query: str,
    page_size: int = 10,
    timeout: float = 2.0
) -> List[Dict]:
    """
    同步搜索包装器
    
    Args:
        query: 查询文本
        page_size: 返回结果数量
        timeout: 超时时间（秒）
        
    Returns:
        匹配结果列表
    """
    async def _search():
        client = NetworkSkillClient()
        try:
            return await client.search_skills(query, page_size, timeout)
        finally:
            await client.close()
    
    try:
        return asyncio.run(_search())
    except Exception:
        return []