-- Tables present in dev MySQL (ai_contract) but missing from SIT environment.
-- Run this AFTER 01_kb_schema.sql on the SIT database.

-- ============================================================
-- Part 1: Knowledge extraction layer (Python side)
-- ============================================================

CREATE TABLE IF NOT EXISTS `kb_section` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `section_id` varchar(128) NOT NULL,
  `parent_section_id` varchar(128) DEFAULT NULL,
  `section_title` varchar(512) DEFAULT NULL,
  `section_path` text,
  `section_level` int DEFAULT NULL,
  `section_type` varchar(128) DEFAULT NULL,
  `seq_start` int DEFAULT NULL,
  `seq_end` int DEFAULT NULL,
  `page_start` int DEFAULT NULL,
  `page_end` int DEFAULT NULL,
  `covered_chunk_ids_json` json DEFAULT NULL,
  `block_ids` json DEFAULT NULL,
  `metadata_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kb_section` (`kb_id`,`file_node_id`,`parse_generation`,`section_id`),
  KEY `idx_section_file` (`file_node_id`,`parse_generation`),
  KEY `idx_section_path` (`kb_id`,`section_type`),
  KEY `idx_parent_section` (`kb_id`,`file_node_id`,`parent_section_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `kb_section_summary` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `section_id` varchar(128) NOT NULL,
  `section_title` varchar(512) DEFAULT NULL,
  `section_path` text,
  `section_level` int DEFAULT NULL,
  `summary_type` varchar(64) NOT NULL DEFAULT 'node_summary',
  `node_summary` longtext,
  `structured_summary_json` json DEFAULT NULL,
  `covered_chunk_ids_json` json DEFAULT NULL,
  `summary_source` varchar(64) DEFAULT NULL,
  `confidence` varchar(32) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_section_summary_file` (`kb_id`,`file_node_id`,`parse_generation`),
  KEY `idx_section_summary_section` (`kb_id`,`file_node_id`,`section_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `kb_section_summary_evidence` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `summary_id` bigint NOT NULL,
  `section_id` varchar(128) NOT NULL,
  `chunk_id` bigint DEFAULT NULL,
  `revision_id` bigint DEFAULT NULL,
  `evidence_quote` longtext,
  `evidence_role` varchar(64) DEFAULT 'source_quote',
  `char_start` int DEFAULT NULL,
  `char_end` int DEFAULT NULL,
  `page_no` int DEFAULT NULL,
  `block_ids` json DEFAULT NULL,
  `bbox_json` json DEFAULT NULL,
  `alignment_status` varchar(32) DEFAULT NULL,
  `metadata_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_summary_evidence_summary` (`kb_id`,`file_node_id`,`parse_generation`,`summary_id`),
  KEY `idx_summary_evidence_section` (`kb_id`,`file_node_id`,`parse_generation`,`section_id`),
  KEY `idx_summary_evidence_chunk` (`kb_id`,`chunk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `kb_anchor_registry` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `anchor_id` varchar(128) NOT NULL,
  `anchor_type` varchar(64) NOT NULL,
  `anchor_name` varchar(512) NOT NULL,
  `normalized_name` varchar(512) DEFAULT NULL,
  `aliases_json` json DEFAULT NULL,
  `source_section_id` varchar(128) DEFAULT NULL,
  `source_chunk_id` bigint DEFAULT NULL,
  `evidence_quote` longtext,
  `confidence` decimal(6,4) DEFAULT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'active',
  `metadata_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_anchor` (`kb_id`,`file_node_id`,`parse_generation`,`anchor_id`),
  KEY `idx_anchor_scope` (`kb_id`,`anchor_type`,`normalized_name`(128)),
  KEY `idx_anchor_file` (`kb_id`,`file_node_id`,`parse_generation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `kb_knowledge_unit` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `unit_id` varchar(128) NOT NULL,
  `unit_type` varchar(64) NOT NULL,
  `unit_subtype` varchar(128) DEFAULT NULL,
  `anchor_id` varchar(128) DEFAULT NULL,
  `subject_text` varchar(512) DEFAULT NULL,
  `predicate_text` varchar(512) DEFAULT NULL,
  `object_text` longtext,
  `value_type` varchar(64) DEFAULT NULL,
  `normalized_json` json DEFAULT NULL,
  `source_section_id` varchar(128) DEFAULT NULL,
  `primary_chunk_id` bigint DEFAULT NULL,
  `evidence_quote` longtext,
  `confidence` decimal(6,4) DEFAULT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'active',
  `metadata_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_knowledge_unit` (`kb_id`,`file_node_id`,`parse_generation`,`unit_id`),
  KEY `idx_unit_type` (`kb_id`,`unit_type`,`unit_subtype`),
  KEY `idx_unit_anchor` (`kb_id`,`anchor_id`),
  KEY `idx_unit_chunk` (`kb_id`,`primary_chunk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `kb_knowledge_unit_evidence` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `unit_id` varchar(128) NOT NULL,
  `chunk_id` bigint NOT NULL,
  `revision_id` bigint DEFAULT NULL,
  `evidence_quote` longtext,
  `char_start` int DEFAULT NULL,
  `char_end` int DEFAULT NULL,
  `page_no` int DEFAULT NULL,
  `block_ids` json DEFAULT NULL,
  `bbox_json` json DEFAULT NULL,
  `alignment_status` varchar(32) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_unit_evidence_unit` (`kb_id`,`file_node_id`,`parse_generation`,`unit_id`),
  KEY `idx_unit_evidence_chunk` (`kb_id`,`chunk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `kb_relation` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `relation_id` varchar(128) NOT NULL,
  `relation_type` varchar(128) NOT NULL,
  `from_type` varchar(64) NOT NULL,
  `from_id` varchar(128) NOT NULL,
  `to_type` varchar(64) NOT NULL,
  `to_id` varchar(128) NOT NULL,
  `source_chunk_id` bigint DEFAULT NULL,
  `evidence_quote` longtext,
  `confidence` decimal(6,4) DEFAULT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'active',
  `metadata_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kb_relation` (`kb_id`,`file_node_id`,`parse_generation`,`relation_id`),
  KEY `idx_relation_from` (`kb_id`,`from_type`,`from_id`),
  KEY `idx_relation_to` (`kb_id`,`to_type`,`to_id`),
  KEY `idx_relation_type` (`kb_id`,`relation_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `kb_knowledge_candidate_pool` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `candidate_id` varchar(128) NOT NULL,
  `candidate_type` varchar(32) NOT NULL,
  `normalized_target_id` varchar(128) DEFAULT NULL,
  `candidate_status` varchar(32) NOT NULL DEFAULT 'validated',
  `merge_group_key` varchar(256) DEFAULT NULL,
  `review_status` varchar(32) NOT NULL DEFAULT 'auto_accepted',
  `confidence` decimal(6,4) DEFAULT NULL,
  `source_section_id` varchar(128) DEFAULT NULL,
  `source_chunk_id` bigint DEFAULT NULL,
  `evidence_quote` longtext,
  `raw_payload_json` json DEFAULT NULL,
  `decision_payload_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_knowledge_candidate` (`kb_id`,`file_node_id`,`parse_generation`,`candidate_id`),
  KEY `idx_candidate_type` (`kb_id`,`file_node_id`,`parse_generation`,`candidate_type`),
  KEY `idx_candidate_status` (`kb_id`,`candidate_status`,`review_status`),
  KEY `idx_candidate_merge` (`kb_id`,`merge_group_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
-- Part 2: Graph & field mention tables
-- (file_field_mentions was in 01_kb_schema but missing from SIT)
-- ============================================================

CREATE TABLE IF NOT EXISTS `file_field_mentions` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `field_id` bigint NOT NULL,
  `chunk_id` bigint NOT NULL,
  `revision_id` bigint DEFAULT NULL,
  `evidence_text` longtext,
  `page_no` int DEFAULT NULL,
  `block_ids` json DEFAULT NULL,
  `bbox_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `char_start` int DEFAULT NULL,
  `char_end` int DEFAULT NULL,
  `alignment_status` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_mentions_field` (`kb_id`,`file_node_id`,`parse_generation`,`field_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `file_graph_nodes` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `node_key` varchar(128) NOT NULL,
  `node_type` varchar(64) NOT NULL,
  `name_cn` varchar(512) DEFAULT NULL,
  `value_text` longtext,
  `source_field_id` bigint DEFAULT NULL,
  `source_chunk_id` bigint DEFAULT NULL,
  `properties_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_graph_node` (`kb_id`,`file_node_id`,`parse_generation`,`node_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `file_graph_edges` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `edge_type` varchar(64) NOT NULL,
  `from_node_key` varchar(128) NOT NULL,
  `to_node_key` varchar(128) NOT NULL,
  `source_field_id` bigint DEFAULT NULL,
  `source_chunk_id` bigint DEFAULT NULL,
  `properties_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_graph_edge_fact` (`kb_id`,`file_node_id`,`parse_generation`,`edge_type`,`from_node_key`,`to_node_key`),
  KEY `idx_graph_edge` (`kb_id`,`file_node_id`,`parse_generation`,`edge_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ============================================================
-- Part 3: Legacy business tables (Java side, contract/agent/task)
-- ============================================================

CREATE TABLE IF NOT EXISTS `agent_channel_config` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `agent_code` varchar(100) NOT NULL,
  `platform_code` varchar(50) NOT NULL,
  `platform_agent_id` varchar(200) DEFAULT NULL,
  `timeout_ms` int DEFAULT NULL,
  `retry_times` int DEFAULT NULL,
  `enabled` tinyint NOT NULL DEFAULT '1',
  `remark` varchar(500) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  `create_name` varchar(255) DEFAULT NULL,
  `update_name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_agent_code` (`agent_code`),
  KEY `idx_platform_code` (`platform_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `agent_info` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `agent_code` varchar(100) NOT NULL,
  `name` varchar(100) NOT NULL,
  `description` varchar(500) DEFAULT NULL,
  `param_doc` text,
  `tags` varchar(200) DEFAULT NULL,
  `icon_url` varchar(500) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  `create_name` varchar(255) DEFAULT NULL,
  `update_name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_agent_code` (`agent_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `agent_invoke_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `log_no` varchar(64) NOT NULL,
  `platform_code` varchar(50) NOT NULL,
  `agent_id` varchar(100) DEFAULT NULL,
  `request_body` text,
  `response_body` mediumtext,
  `http_status` int DEFAULT NULL,
  `invoke_status` varchar(20) NOT NULL,
  `error_msg` varchar(1000) DEFAULT NULL,
  `duration_ms` bigint DEFAULT NULL,
  `tenant_id` varchar(50) DEFAULT NULL,
  `session_id` varchar(200) DEFAULT NULL,
  `final_result` text,
  `create_time` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_log_no` (`log_no`),
  KEY `idx_platform_code` (`platform_code`),
  KEY `idx_agent_id` (`agent_id`),
  KEY `idx_create_time` (`create_time`),
  KEY `idx_tenant_id` (`tenant_id`),
  KEY `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `contract_field_config` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `contract_template_id` bigint NOT NULL,
  `field_key` varchar(255) NOT NULL,
  `field_key_eng` varchar(255) NOT NULL,
  `field_key_type` varchar(50) NOT NULL,
  `near_field_keys` text,
  `field_value_options` text,
  `description` text,
  `remark` text,
  `del_flag` tinyint(1) NOT NULL DEFAULT '0',
  `create_name` varchar(36) DEFAULT NULL,
  `update_name` varchar(36) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `contract_prompt_config` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `contract_template_id` bigint NOT NULL,
  `prompt_content` text NOT NULL,
  `version` int NOT NULL,
  `prompt_description` text,
  `remark` text,
  `del_flag` tinyint(1) NOT NULL DEFAULT '0',
  `create_name` varchar(36) DEFAULT NULL,
  `update_name` varchar(36) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  `priority` int NOT NULL DEFAULT '0',
  `ocr_model` varchar(20) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `contract_template` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `template_name` varchar(255) NOT NULL,
  `template_code` varchar(255) NOT NULL,
  `prompt_id` bigint DEFAULT NULL,
  `tenant_id` varchar(255) NOT NULL,
  `description` text,
  `template_type` int DEFAULT '1',
  `remark` text,
  `del_flag` tinyint(1) NOT NULL DEFAULT '0',
  `create_name` varchar(36) DEFAULT NULL,
  `update_name` varchar(36) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `file_classify_category_config` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `template_id` bigint NOT NULL,
  `parent_id` bigint DEFAULT '0',
  `level` int DEFAULT '1',
  `category_code` varchar(100) NOT NULL,
  `category_name` varchar(200) NOT NULL,
  `category_desc` varchar(500) DEFAULT NULL,
  `sort_order` int DEFAULT '0',
  `remark` varchar(500) DEFAULT NULL,
  `del_flag` int DEFAULT '0',
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  `create_name` varchar(255) DEFAULT NULL,
  `update_name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_template_id` (`template_id`),
  KEY `idx_parent_id` (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `task_evaluation` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_no` varchar(255) NOT NULL,
  `evaluation_grade` decimal(2,1) DEFAULT NULL,
  `evaluation_text` text,
  `evaluation_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `evaluator_name` varchar(255) DEFAULT NULL,
  `evaluation_description` text,
  `del_flag` tinyint(1) NOT NULL DEFAULT '0',
  `create_name` varchar(36) DEFAULT NULL,
  `update_name` varchar(36) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `task_no` (`task_no`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `task_file_message` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_no` varchar(255) DEFAULT NULL,
  `file_id` varchar(255) DEFAULT NULL,
  `file_name` varchar(255) DEFAULT NULL,
  `ocr_file_id` varchar(255) DEFAULT NULL,
  `type` varchar(255) DEFAULT NULL,
  `create_name` varchar(255) DEFAULT NULL,
  `update_name` varchar(255) DEFAULT NULL,
  `create_time` datetime DEFAULT NULL,
  `update_time` datetime DEFAULT NULL,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  `del_flag` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `task_record` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_no` varchar(255) DEFAULT NULL,
  `business_no` varchar(50) DEFAULT NULL,
  `status` varchar(50) NOT NULL,
  `contract_template_id` bigint NOT NULL,
  `contract_prompt_id` bigint DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `started_at` datetime DEFAULT NULL,
  `finished_at` datetime DEFAULT NULL,
  `duration` int DEFAULT NULL,
  `error_code` varchar(255) DEFAULT NULL,
  `error_msg` text,
  `tenant_id` varchar(255) NOT NULL,
  `ocr_file_id` varchar(255) DEFAULT NULL,
  `extract_result` text,
  `remark` text,
  `del_flag` tinyint(1) NOT NULL DEFAULT '0',
  `create_name` varchar(36) DEFAULT NULL,
  `update_name` varchar(36) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `creator` varchar(255) DEFAULT NULL,
  `updator` varchar(255) DEFAULT NULL,
  `task_type` varchar(3) DEFAULT '0',
  `business_form_json` text,
  `custom_prompt` text,
  `compare_result` text,
  `classify_result` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
