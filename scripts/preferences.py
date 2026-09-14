#!/usr/bin/env python3
"""Canonical optional features. Missing preferences preserve old lessons, explicit plans do not."""
import copy
DEFAULTS={'annotations':True,'dictionary':True,'classroom_tools':True,'quick_answers':True,'writing_transfer':True,
          'deep_reading':True,'culture_background':False}

def features(exam):
    value=exam.get('features',{})
    if not isinstance(value,dict):raise ValueError('features 必须是功能开关对象')
    unknown=set(value)-set(DEFAULTS)
    if unknown:raise ValueError('未知功能: '+', '.join(sorted(unknown)))
    if any(type(v) is not bool for v in value.values()):raise ValueError('功能选项必须是 true 或 false')
    return {**DEFAULTS,**value}

def apply_plan(exam,plan):
    if plan.get('confirmed') is not True:raise ValueError('请先询问老师生成范围和所需功能，不能默认开始')
    if plan.get('mode') not in ('lesson','intensive'):raise ValueError('请选择 lesson 或 intensive')
    if not isinstance(plan.get('sections'),str) or not plan['sections'].strip():raise ValueError('请选择板块')
    if set(plan.get('features',{}))!=set(DEFAULTS):raise ValueError('请记录全部可选功能的选择')
    if plan.get('profile') not in (None,'quick','full'):raise ValueError('profile 只能是 quick 或 full')
    from scope import select
    result=select(exam,plan['sections'],plan['mode']);result['features']=features(plan)
    result['generation_preferences']={'confirmed':True,'sections':plan['sections'],'mode':plan['mode'],'profile':plan.get('profile') or 'full','features':result['features']}
    return result
