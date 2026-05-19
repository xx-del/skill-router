"""
Hermes Skill Router - Hook 回调 (v2.0)
实现 pre_llm_call Hook 入口
"""

from typing import Dict, List, Optional


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
    pre_llm_call Hook 回调（7参数签名）
    
    Args:
        session_id: 会话 ID
        user_message: 用户消息
        conversation_history: 对话历史
        is_first_turn: 是否首轮对话
        model: 模型名称
        platform: 平台名称
        sender_id: 发送者 ID
        **kwargs: 其他参数
        
    Returns:
        Optional[Dict[str, str]]: 返回 {"context": "推荐内容"} 注入到用户消息末尾
    """
    # 只在首轮对话触发
    if not is_first_turn:
        return None
    
    # 消息太短不触发
    if len(user_message.strip()) < 5:
        return None
    
    try:
        from .router import get_cached_router
        
        router = get_cached_router()
        if not router:
            return None
        
        # 混合搜索：本地 + 网络
        results = router.search_with_network(user_message, top_k=3)
        
        if not results:
            return None
        
        # 构建推荐提示
        rec_prompt = "\n\n[SKILL_ROUTER]\n## 🎯 推荐技能\n\n"
        
        for i, result in enumerate(results, 1):
            skill = result.get('skill', {})
            name = skill.get('name', 'unknown')
            description = skill.get('description', '')
            source = result.get('source', 'local')
            score = result.get('score', 0)
            use_count = result.get('use_count', 0)
            
            # 来源标记
            source_icon = "📁" if source == 'local' else "🌐"
            
            # 使用次数标记
            use_info = f" (使用 {use_count} 次)" if use_count > 0 else ""
            
            # 截断描述
            desc_short = description[:80] + "..." if len(description) > 80 else description
            
            rec_prompt += f"{i}. {source_icon} **{name}**{use_info}\n"
            if desc_short:
                rec_prompt += f"   {desc_short}\n"
        
        rec_prompt += "\n> 💡 以上技能可能与当前任务相关，可考虑调用。\n"
        
        return {"context": rec_prompt}
        
    except Exception as e:
        # Hook 失败不影响主流程
        return None


# ============ 插件注册入口 ============

def register(ctx) -> None:
    """
    插件注册入口（Hermes 标准）
    
    Args:
        ctx: Hermes 插件上下文
    """
    ctx.register_hook("pre_llm_call", on_user_message)