"""基准测试

验证 BM25 路由准确率。
目标：Hit@1 ≥ 50%, Hit@3 ≥ 75%（纯词法匹配的现实预期）
"""

import json
from pathlib import Path
from typing import List, Dict

def run_benchmark(test_cases: List[Dict] = None) -> Dict:
    """运行基准测试
    
    Args:
        test_cases: 测试用例列表，格式：
            [{"query": "分析网站性能", "expected": ["webapp-testing", "deep-thinking"]}, ...]
            如果为 None，从 test_cases.json 加载
    
    Returns:
        {
            "total": 50,
            "hit@1": 28,
            "hit@3": 42,
            "hit@1_rate": 0.56,
            "hit@3_rate": 0.84,
            "details": [...]
        }
    """
    
    # 加载测试用例
    if test_cases is None:
        test_file = Path(__file__).parent / 'test_cases.json'
        if test_file.exists():
            with open(test_file, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
        else:
            return {"error": "No test cases found"}
    
    # 构建索引
    from .scanner import scan_skills
    from .indexer import SkillIndexer
    
    skills = scan_skills()
    if not skills:
        return {"error": "No skills found"}
    
    indexer = SkillIndexer()
    indexer.index(skills)
    
    # 运行测试
    results = {
        "total": len(test_cases),
        "hit@1": 0,
        "hit@3": 0,
        "details": []
    }
    
    for case in test_cases:
        query = case['query']
        expected = case['expected']
        
        matched = indexer.query(query, top_k=3)
        matched_names = [skill['name'] for skill, _ in matched]
        
        hit_1 = matched_names[0] in expected if matched_names else False
        hit_3 = any(name in expected for name in matched_names)
        
        if hit_1:
            results['hit@1'] += 1
        if hit_3:
            results['hit@3'] += 1
        
        results['details'].append({
            "query": query,
            "expected": expected,
            "matched": matched_names,
            "hit@1": hit_1,
            "hit@3": hit_3
        })
    
    results['hit@1_rate'] = results['hit@1'] / results['total'] if results['total'] > 0 else 0
    results['hit@3_rate'] = results['hit@3'] / results['total'] if results['total'] > 0 else 0
    
    return results
