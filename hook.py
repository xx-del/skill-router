"""pre_llm_call Hook 回调

Hermes 实际调用签名（conversation_loop.py:506-515）：
    _invoke_hook(
        "pre_llm_call",
        session_id=agent.session_id,
        user_message=original_user_message,
        conversation_history=list(messages),
        is_first_turn=(not bool(conversation_history)),
        model=agent.model,
        platform=getattr(agent, "platform", None) or "",
        sender_id=getattr(agent, "_user_id", None) or "",
    )

返回值处理（conversation_loop.py:521-528）：
    for r in _pre_results:
        if isinstance(r, dict) and r.get("context"):
            _ctx_parts.append(str(r["context"]))
        elif isinstance(r, str) and r.strip():
            _ctx_parts.append(r)
"""

from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)

# 配置常量
MAX_RECOMMENDATIONS = 3
MIN_SCORE = 0.3
CONTEXT_PREFIX = "\n\n[SKILL_ROUTER]\n"

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
    """
    pre_llm_call Hook 回调
    
    参数：
        session_id: 会话唯一标识符
        user_message: 用户原始消息
        conversation_history: 完整消息列表副本
        is_first_turn: 是否为新会话第一轮
        model: 模型标识符
        platform: 运行平台（"cli"/"telegram"/"discord"等）
        sender_id: 发送者ID
        **kwargs: 未来扩展参数
    
    返回：
        {"context": "推荐技能..."} 或 None
    """
    
    try:
        # 1. 获取缓存索引器
        from .cache import get_cached_indexer
        indexer = get_cached_indexer()
        
        if not indexer:
            return None
        
        # 2. 查询匹配技能
        matched = indexer.query(user_message, top_k=MAX_RECOMMENDATIONS)
        
        if not matched:
            return None
        
        # 3. 过滤低分匹配
        matched = [(skill, score) for skill, score in matched if score >= MIN_SCORE]
        
        if not matched:
            return None
        
        # 4. 读取使用数据（直接读 JSON，不导入核心模块）
        from .usage_reader import get_usage_data
        usage_data = get_usage_data()
        
        # 5. 生成推荐提示
        #    使用 [SKILL_ROUTER] 前缀，与其他插件 context 区分
        rec_prompt = CONTEXT_PREFIX
        rec_prompt += "## 🎯 推荐技能\n\n"
        rec_prompt += "根据您的任务，智能推荐以下技能：\n\n"
        
        for i, (skill, score) in enumerate(matched, 1):
            skill_name = skill['name']
            use_count = usage_data.get(skill_name, {}).get('use_count', 0)
            
            rec_prompt += f"{i}. **{skill_name}** (匹配分数: {score:.2f})\n"
            rec_prompt += f"   - 描述: {skill['description'][:50]}...\n"
            rec_prompt += f"   - 使用次数: {use_count}\n\n"
        
        # 6. 返回 dict 格式（Hermes 推荐格式）
        return {"context": rec_prompt}
    
    except MemoryError:
        logger.error("skill-router: MemoryError during indexing")
        return None
    except ImportError as e:
        logger.error("skill-router: Missing dependency: %s", e)
        return None
    except Exception as e:
        logger.warning("skill-router hook failed: %s", e, exc_info=True)
        return None
