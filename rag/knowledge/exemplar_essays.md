---
policy_id: exemplar_a3
scene_key: exemplar
title: A3 往届优秀作业（脱敏）
score: 0.85
retrieval_stage: hybrid
---

## 优秀片段一：冒泡 vs 快排

冒泡排序每轮比较相邻元素并交换，最坏 n(n-1)/2 次比较，O(n^2)。快速排序分治划分子区间，平均 O(n log n)。我引用了教材第三章大 O 定义（3.1 节），并指出大 O 是上界而非精确时间。最坏情况快排退化为 O(n^2)，例如输入已有序且选首元素为枢轴。空间上冒泡 O(1)，快排平均 O(log n) 栈。

## 优秀片段二：三种排序对比

冒泡最坏 O(n^2)、最好 O(n)；归并始终 O(n log n) 但需 O(n) 额外空间；快排平均 O(n log n) 最坏 O(n^2)。Python Timsort 对近乎有序数据近乎 O(n)。我讨论了递归栈深度对空间复杂度的影响，并引用课程讲义第 5 讲。
