-- ============================================================
-- V1.0.2 知识库策略模板初始化
-- ============================================================
-- 说明：
-- 1. V1.0 正确基线 SQL 已包含 kb_knowledge_base 策略字段，以及解析/检索策略配置表。
-- 2. 本脚本只初始化内置模板数据，不再重复 ALTER TABLE / CREATE TABLE。
-- 3. 如果是从错误的旧 v1.0.0_kb_platform.sql 升级，请先执行一次结构修复脚本或直接按正确 V1.0 基线重建。

INSERT IGNORE INTO `kb_parse_strategy_config`
(`id`, `name`, `code`, `scope_type`, `config_json`, `status`, `remark`)
VALUES
('parse_general', '通用解析策略', 'general', 'template',
 JSON_OBJECT('ocrEnabled', false, 'tableMode', 'auto', 'chunkSize', 800, 'chunkOverlap', 120),
 'active', '适合普通文档、制度、说明类材料'),
('parse_ocr_enhanced', '增强 OCR 识别', 'ocr_enhanced', 'template',
 JSON_OBJECT('ocrEnabled', true, 'tableMode', 'auto', 'chunkSize', 800, 'chunkOverlap', 120),
 'active', '适合扫描件、图片型 PDF'),
('parse_table_first', '表格优先解析', 'table_first', 'template',
 JSON_OBJECT('ocrEnabled', true, 'tableMode', 'table_first', 'chunkSize', 600, 'chunkOverlap', 80),
 'active', '适合包含大量表格的文档');

INSERT IGNORE INTO `kb_retrieval_strategy_config`
(`id`, `name`, `code`, `scope_type`, `config_json`, `status`, `remark`)
VALUES
('retrieval_balanced', '均衡检索策略', 'balanced', 'template',
 JSON_OBJECT('topK', 8, 'scoreThreshold', 0.45, 'hybrid', true, 'rerankEnabled', true, 'qaWeight', 0.5, 'chunkWeight', 0.5),
 'active', '默认推荐，兼顾召回与精准度'),
('retrieval_precision', '精准优先策略', 'precision', 'template',
 JSON_OBJECT('topK', 5, 'scoreThreshold', 0.65, 'hybrid', true, 'rerankEnabled', true, 'qaWeight', 0.6, 'chunkWeight', 0.4),
 'active', '适合要求答案严格命中文档依据的场景'),
('retrieval_recall', '召回优先策略', 'recall', 'template',
 JSON_OBJECT('topK', 12, 'scoreThreshold', 0.35, 'hybrid', true, 'rerankEnabled', true, 'qaWeight', 0.4, 'chunkWeight', 0.6),
 'active', '适合需要覆盖更多候选材料的场景');
