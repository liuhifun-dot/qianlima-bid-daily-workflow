# lessons/（经验教训 — 长期规则）

## 是什么

从**已解决**的问题里提炼出的、以后仍要遵守的规则。  
不是某次 run 的流水账，也不是 open 工单。

完整分工见：`references/logging-and-records.md`。

## 文件

| 文件 | 用途 |
|:---|:---|
| `README.md` | 本说明 |
| `lessons_template.md` | 单条写法参考 |
| `lessons_log.md` | **实际追加内容**（按日期） |

## 何时写入

1. `issue-log` 中某条变为 `resolved`，且规则仍有用  
2. 同类问题出现两次以上  

## 怎么写

1. 打开 `lessons_log.md`  
2. 按模板追加一节：日期、问题一句话、规则（可执行句子）、链回 ISSUE  
3. 规则要写成「必须/禁止/默认」，避免故事流水账  

## 与 issue-log 的关系

- 先有 issue（工单）→ 修好 → 再提炼进 lessons（规则）  
- 不要只写 lessons 不写 issue（难追踪状态）  
- 不要只堆 issue 永不提炼（下次仍靠人肉回忆）  
