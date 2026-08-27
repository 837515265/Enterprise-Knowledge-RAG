-- ============================================================
-- SIT first deployment: common_proxy.app_third_config initialization
-- Do not insert auto-increment id values.
-- ============================================================

INSERT INTO common_proxy.app_third_config
(app_id, app_name, interface_id, interface_name, interface_description, interface_domain, method_type, content_type, http_type, feign_client_name, feign_method_url, response_code_column, response_code, timeout, cost, is_token, is_secret, status, create_time, update_time, creator, updator, remark, charset)
VALUES
('NEW_API', '公司大模型网关', 'chat-completions', '模型对话调用', 'new-api Chat Completions 接口', 'http://124.128.251.51:20003', 'POST', 'application/json', 1, NULL, NULL, NULL, NULL, 300, 0.0000, '2', '2', '1', NOW(), NOW(), NULL, NULL, '知识库平台大模型调用', NULL);
