"""动态技能扫描器 - 实时读取 Hermes 技能目录"""

from pathlib import Path
from typing import List, Dict
import yaml
import logging

logger = logging.getLogger(__name__)

def scan_skills() -> List[Dict]:
    """动态扫描 Hermes 技能目录，提取 description + tags"""
    
    skills = []
    skills_dir = Path.home() / '.hermes' / 'skills'
    
    if not skills_dir.exists():
        return []
    
    for skill_md in skills_dir.rglob('SKILL.md'):
        # 跳过备份目录
        if '.backup' in skill_md.parts or '.bk' in skill_md.parts or '.archive' in skill_md.parts:
            continue
        
        try:
            content = skill_md.read_text(encoding='utf-8')
            frontmatter = parse_frontmatter(content)
            
            description = frontmatter.get('description', '')
            
            # 忽略无描述的技能
            if not description:
                continue
            
            tags = frontmatter.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]
            
            skill = {
                'name': frontmatter.get('name', skill_md.parent.name),
                'description': description,
                'tags': tags,
                'path': str(skill_md.parent),
                # 合并为检索文本（标签重复2次增加权重）
                'text': f"{description} {' '.join(tags)} {' '.join(tags)}"
            }
            
            skills.append(skill)
        
        except Exception as e:
            logger.debug("skill-router: skip %s: %s", skill_md, e)
            continue
    
    return skills

def parse_frontmatter(content: str) -> Dict:
    """解析 SKILL.md 的 YAML frontmatter"""
    
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                return yaml.safe_load(parts[1]) or {}
            except Exception:
                pass
    
    return {}
