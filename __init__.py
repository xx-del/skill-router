"""技能智能路由器插件 - Hermes 标准插件入口"""

from typing import Optional

def register(ctx) -> None:
    """插件注册入口（Hermes 标准）
    
    Hermes 在加载插件时调用此函数，传入 PluginContext 对象。
    通过 ctx.register_hook() 注册生命周期钩子。
    """
    
    from .hook import on_user_message
    
    # 注册 pre_llm_call Hook
    ctx.register_hook("pre_llm_call", on_user_message)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info("skill-router plugin registered")
