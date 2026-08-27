-- v1.0.4 问AI引用明细补充完整检索元数据
-- 用于历史会话回显 field_name_cn / route_name / rerank_score / source_file_id 等扩展字段。

ALTER TABLE `kb_chat_message_citation`
  ADD COLUMN `metadata_json` JSON DEFAULT NULL COMMENT '引用元数据（完整保留检索返回字段）'
  AFTER `page_num`;
