-- ============================================================
-- SIT first deployment: common_proxy.app_info initialization
-- Do not insert auto-increment id values.
-- ============================================================

INSERT INTO common_proxy.app_info
(app_id, app_name, app_description, `type`, status, create_time, update_time, creator, updator, remark)
VALUES
('NEW_API', '公司大模型网关', 'new-api 模型统一接入网关', '1', '1', NOW(), NOW(), NULL, NULL, '知识库平台调用配置'),
('APP_KNOWLEDGE_SERVICE', 'AI知识库平台', NULL, '2', '1', NOW(), NOW(), NULL, NULL, NULL);
