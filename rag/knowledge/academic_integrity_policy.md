---
policy_id: academic_integrity
scene_key: policy
title: 学术不端处置政策
score: 1.0
retrieval_stage: pinned
---

## 认定标准

学术不端包括：抄袭、代写、伪造引用、未经授权的协作、篡改作业提交时间戳。相似度阈值 0.8 仅作初批参考信号，不直接构成处分依据。

## 处置流程

1. TA / 初批系统打 flagged
2. 主讲教师复核证据（作业正文 hash、相似度报告、学生历史）
3. instructor 本人作出 judge_academic_misconduct 判定
4. 判定结果通知学生并允许申诉

## 申诉机制

学生对学术不端判定有一次申诉机会。申诉走 grade_appeal 意图，直挂本政策域，不向量召回。申诉期间原判定暂缓执行。

## 边界

Grader 只做初批参考和 flagged 标记；judge_academic_misconduct 必须由 instructor 本人审批，系统不自动处分。
