-- ============================================================
-- V1.0.5 知识库平台新增 MinerU 模型服务代理配置
-- ============================================================

INSERT INTO common_proxy.app_info
(app_id, app_name, app_description, `type`, status, create_time, update_time, creator, updator, remark)
VALUES
('MINERU', 'MinerU文档解析', 'MinerU文档智能解析服务', '1', '1', NOW(), NOW(), NULL, NULL, NULL);

INSERT INTO common_proxy.app_relation_info
(out_app_id, out_app_interface_id, in_app_id, status, create_time, update_time, creator, updator, remark)
VALUES
('MINERU', 'mineru-parse', 'APP_KNOWLEDGE_SERVICE', '1', NOW(), NOW(), NULL, NULL, '知识库平台 -> MinerU OCR 调用关系');

INSERT INTO common_proxy.app_third_config
(app_id, app_name, interface_id, interface_name, interface_description, interface_domain, method_type, content_type, http_type, feign_client_name, feign_method_url, response_code_column, response_code, timeout, cost, is_token, is_secret, status, create_time, update_time, creator, updator, remark, charset)
VALUES
('MINERU', 'MinerU模型服务', 'mineru-parse', 'MinerU OCR解析', 'MinerU OCR解析接口', 'http://124.128.251.51:21189', 'POST', 'multipart/form-data', 1, NULL, NULL, NULL, NULL, 900, 0.0000, '2', '2', '1', NOW(), NOW(), NULL, NULL, '', NULL);
