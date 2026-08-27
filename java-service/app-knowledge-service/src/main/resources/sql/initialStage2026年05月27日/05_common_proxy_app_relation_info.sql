-- ============================================================
-- SIT first deployment: common_proxy.app_relation_info initialization
-- Do not insert auto-increment id values.
-- ============================================================

INSERT INTO common_proxy.app_relation_info
(out_app_id, out_app_interface_id, in_app_id, status, create_time, update_time, creator, updator, remark)
VALUES
('NEW_API', 'chat-completions', 'APP_KNOWLEDGE_SERVICE', '1', NOW(), NOW(), NULL, NULL, '知识库平台 -> new-api 调用关系');
