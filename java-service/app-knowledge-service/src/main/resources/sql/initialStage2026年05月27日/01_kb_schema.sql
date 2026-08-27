-- MySQL dump 10.13  Distrib 5.7.18, for macos10.12 (x86_64)
--
-- Host: 10.10.20.92    Database: ai_contract
-- ------------------------------------------------------
-- Server version	8.0.22

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `kb_knowledge_base`
--

DROP TABLE IF EXISTS `kb_knowledge_base`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_knowledge_base` (
  `id` bigint NOT NULL COMMENT '主键，雪花ID',
  `name` varchar(256) COLLATE utf8mb4_general_ci NOT NULL COMMENT '知识库名称',
  `type` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '知识库类型 general/faq/manual 等',
  `description` varchar(2000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '知识库描述',
  `visibility` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'private' COMMENT '公开性 public/private',
  `file_audit_enabled` tinyint NOT NULL DEFAULT '0' COMMENT '文件审核开关 0=关 1=开',
  `qa_audit_enabled` tinyint NOT NULL DEFAULT '0' COMMENT '问答审核开关 0=关 1=开',
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'active' COMMENT '状态 active/archived',
  `index_collection_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '检索引擎索引集合ID，1KB=1集合',
  `member_count` int NOT NULL DEFAULT '0' COMMENT '权限命中成员数缓存（定时刷新）',
  `parse_strategy_config_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '默认解析策略配置ID，关联 kb_parse_strategy_config.id',
  `retrieval_config_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '默认检索策略配置ID，关联 kb_retrieval_strategy_config.id',
  `model_profile` json DEFAULT NULL COMMENT '默认模型配置引用JSON',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_collection_id` (`index_collection_id`),
  KEY `idx_name` (`name`),
  KEY `idx_visibility_status` (`visibility`,`status`),
  KEY `idx_parse_strategy` (`parse_strategy_config_id`),
  KEY `idx_retrieval_strategy` (`retrieval_config_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库主表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_retrieval_strategy_config`
--

DROP TABLE IF EXISTS `kb_retrieval_strategy_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_retrieval_strategy_config` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键，策略配置ID（雪花字符串/UUID）',
  `name` varchar(256) COLLATE utf8mb4_general_ci NOT NULL COMMENT '配置名称',
  `code` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '策略编码，便于程序引用',
  `scope_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'kb' COMMENT '作用域 kb=绑定知识库 template=租户级模板',
  `kb_id` bigint DEFAULT NULL COMMENT 'scope_type=kb 时必填，模板可为空',
  `config_json` json NOT NULL COMMENT '检索策略参数（top_k、阈值、混合模式等）',
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'active' COMMENT '状态 active/disabled',
  `remark` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '备注',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_kb_status` (`kb_id`,`status`,`del_flag`),
  KEY `idx_scope_code` (`scope_type`,`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='检索策略配置表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_parse_strategy_config`
--

DROP TABLE IF EXISTS `kb_parse_strategy_config`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_parse_strategy_config` (
  `id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '主键，策略配置ID（雪花字符串/UUID）',
  `name` varchar(256) COLLATE utf8mb4_general_ci NOT NULL COMMENT '配置名称',
  `code` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '策略编码，便于程序引用（如 general/contract）',
  `scope_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'kb' COMMENT '作用域 kb=绑定知识库 template=租户级模板',
  `kb_id` bigint DEFAULT NULL COMMENT 'scope_type=kb 时必填，模板可为空',
  `config_json` json NOT NULL COMMENT '解析策略参数（分块、OCR、版面等）',
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'active' COMMENT '状态 active/disabled',
  `remark` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '备注',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_kb_status` (`kb_id`,`status`,`del_flag`),
  KEY `idx_scope_code` (`scope_type`,`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='解析策略配置表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_file_node`
--

DROP TABLE IF EXISTS `kb_file_node`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_file_node` (
  `id` bigint NOT NULL COMMENT '主键: 文件类型=文件ID, 文件夹类型=雪花ID',
  `kb_id` bigint NOT NULL COMMENT '所属知识库ID',
  `parent_id` bigint DEFAULT NULL COMMENT '父节点ID，根目录下为空',
  `node_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL COMMENT '节点类型 folder/file',
  `name` varchar(512) COLLATE utf8mb4_general_ci NOT NULL COMMENT '节点名称（文件夹名或展示文件名）',
  `original_name` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '用户上传原始文件名（仅file）',
  `file_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '对象存储中的原始文件ID（仅file）',
  `file_size` bigint DEFAULT NULL COMMENT '文件字节数（仅file）',
  `mime_type` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'MIME类型（仅file）',
  `file_ext` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '扩展名 pdf/docx/xlsx（仅file）',
  `file_hash` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '文件SHA-256，去重防篡改（仅file）',
  `parse_strategy_config_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '上传可选的解析策略配置ID，NULL 则解析时采用 kb_knowledge_base.parse_strategy_config_id',
  `parse_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'none' COMMENT '解析状态 none/parsing/parsed/failed',
  `index_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'none' COMMENT '索引状态 none/indexing/synced/failed',
  `current_parse_generation` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当前成功解析代际，格式: file_{id}_{seq}',
  `current_index_generation` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当前已发布索引代际，格式: file_{id}_{seq}',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  `profile` varchar(64) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'guarantee_plan',
  `parse_result_ref` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `audit_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'approved',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kb_file_id` (`kb_id`,`file_id`),
  KEY `idx_kb_parent` (`kb_id`,`parent_id`),
  KEY `idx_kb_parse_status` (`kb_id`,`parse_status`),
  KEY `idx_kb_index_status` (`kb_id`,`index_status`),
  KEY `idx_file_parse_strategy` (`parse_strategy_config_id`),
  KEY `idx_kb_hash` (`kb_id`,`file_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='文件节点表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_file_task`
--

DROP TABLE IF EXISTS `kb_file_task`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_file_task` (
  `id` bigint NOT NULL COMMENT '主键，任务ID',
  `kb_id` bigint NOT NULL COMMENT '知识库ID',
  `file_node_id` bigint NOT NULL COMMENT '对应kb_file_node.id',
  `stage` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '当前阶段 parse/chunk/embed/index/done',
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'pending' COMMENT '解析状态 pending/processing/success/failed',
  `error_msg` varchar(2000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '最近一次失败原因',
  `parse_result_url` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '解析产物JSON地址（引擎写入）',
  `indexed_chunk_count` int NOT NULL DEFAULT '0' COMMENT '已写入检索索引的Chunk数',
  `index_sync_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'none' COMMENT '索引同步状态 none/syncing/synced/failed',
  `parse_generation` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '本任务解析代际，格式: file_{id}_{seq}',
  `index_generation` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '本任务索引代际，格式: file_{id}_{seq}',
  `engine_task_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '解析检索服务内部任务ID',
  `parse_strategy_config_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '本任务实际采用的解析策略配置ID（上传指定优先，否则知识库默认，创建任务时固化快照）',
  `model_profile` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '本次任务使用的模型/向量化等模型侧配置名（与解析策略配置解耦）',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_file_node` (`file_node_id`),
  KEY `idx_kb_stage_status` (`kb_id`,`stage`,`status`),
  KEY `idx_status_time` (`status`,`update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='文件解析与索引任务表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_file_task_history`
--

DROP TABLE IF EXISTS `kb_file_task_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_file_task_history` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `task_type` varchar(32) NOT NULL,
  `stage` varchar(32) NOT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'pending',
  `parse_generation` varchar(128) DEFAULT NULL,
  `index_generation` varchar(128) DEFAULT NULL,
  `engine_task_id` varchar(128) DEFAULT NULL,
  `error_msg` varchar(2000) DEFAULT NULL,
  `payload_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_task_history_file` (`kb_id`,`file_node_id`,`task_type`,`create_time`),
  KEY `idx_task_history_generation` (`kb_id`,`file_node_id`,`parse_generation`,`index_generation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_qa_pair`
--

DROP TABLE IF EXISTS `kb_qa_pair`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_qa_pair` (
  `id` bigint NOT NULL COMMENT '主键，问答ID',
  `kb_id` bigint NOT NULL COMMENT '知识库ID',
  `question` longtext COLLATE utf8mb4_general_ci NOT NULL COMMENT '问题',
  `answer` longtext COLLATE utf8mb4_general_ci NOT NULL COMMENT '答案',
  `audit_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'pending' COMMENT '审核状态 pending/approved/rejected',
  `index_sync_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'none' COMMENT '索引同步状态 none/synced/failed',
  `index_record_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '检索引擎中的记录ID',
  `sync_error_message` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '同步失败原因',
  `extended_questions` json DEFAULT NULL COMMENT '扩展问法列表',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  `file_node_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_kb_audit` (`kb_id`,`audit_status`),
  KEY `idx_kb_sync` (`kb_id`,`index_sync_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库问答对表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_chunk`
--

DROP TABLE IF EXISTS `kb_chunk`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_chunk` (
  `id` bigint NOT NULL COMMENT '主键，chunk业务主键',
  `kb_id` bigint NOT NULL COMMENT '知识库ID',
  `file_node_id` bigint NOT NULL COMMENT '所属文件节点ID',
  `seq_no` int NOT NULL COMMENT '文件内顺序号',
  `content` longtext COLLATE utf8mb4_general_ci NOT NULL COMMENT '当前展示内容（冗余published_revision内容）',
  `summary` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当前展示摘要',
  `enabled` tinyint NOT NULL DEFAULT '0' COMMENT '是否参与检索 0=否 1=是',
  `audit_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'pending' COMMENT '审核状态 pending/approved/rejected',
  `reject_reason` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '驳回原因',
  `index_record_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '检索引擎中的记录ID',
  `index_sync_status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'none' COMMENT '索引同步状态 none/synced/failed',
  `sync_error_msg` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '同步失败原因',
  `published_revision_id` bigint DEFAULT NULL COMMENT '当前已审核发布版本，关联kb_chunk_revision.id',
  `latest_revision_id` bigint DEFAULT NULL COMMENT '最新版本（待审核或已发布），关联kb_chunk_revision.id',
  `parse_generation` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '来源解析代际，格式: file_{id}_{seq}',
  `index_generation` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当前已同步索引代际，格式: file_{id}_{seq}',
  `content_hash` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '当前发布内容hash',
  `page_start` int DEFAULT NULL COMMENT '起始页码',
  `page_end` int DEFAULT NULL COMMENT '结束页码',
  `chunk_type` varchar(32) COLLATE utf8mb4_general_ci DEFAULT 'original' COMMENT 'chunk类型 original/section_summary/clause/slide/table_row',
  `section_type` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '业务章节类型 credit_limit/access_condition等',
  `section_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '章节/条款/slide ID',
  `chunk_group_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'EvidenceGroup归并ID',
  `block_ids` json DEFAULT NULL COMMENT 'OCR/版面block ID列表',
  `metadata_json` json DEFAULT NULL COMMENT '解析输出扩展元数据（版面、章节等；解析策略以文件节点/任务侧 parse_strategy_config_id 为准）',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  `draft_revision_id` bigint DEFAULT NULL,
  `sim_hash` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_file_seq` (`file_node_id`,`seq_no`),
  KEY `idx_kb_enabled` (`kb_id`,`enabled`),
  KEY `idx_kb_audit` (`kb_id`,`audit_status`),
  KEY `idx_sync` (`index_sync_status`),
  KEY `idx_chunk_group` (`chunk_group_id`),
  KEY `idx_parse_gen` (`parse_generation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Chunk主数据表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_chunk_revision`
--

DROP TABLE IF EXISTS `kb_chunk_revision`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_chunk_revision` (
  `id` bigint NOT NULL COMMENT '主键，revision ID',
  `kb_id` bigint NOT NULL COMMENT '知识库ID',
  `file_node_id` bigint NOT NULL COMMENT '文件节点ID',
  `chunk_id` bigint NOT NULL COMMENT '关联kb_chunk.id',
  `revision_no` int NOT NULL COMMENT '版本号，从1递增',
  `revision_source` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '版本来源 parse/manual_edit/audit_edit',
  `content` longtext COLLATE utf8mb4_general_ci NOT NULL COMMENT '本revision内容',
  `summary` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '本revision摘要',
  `content_for_embedding` longtext COLLATE utf8mb4_general_ci COMMENT '向量检索文本（含短前缀增强）',
  `content_for_bm25` longtext COLLATE utf8mb4_general_ci COMMENT 'BM25全文检索文本（含别名增强）',
  `title` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'chunk标题',
  `title_path` json DEFAULT NULL COMMENT '标题层级路径 ["服务方案","授信额度"]',
  `page_start` int DEFAULT NULL COMMENT '起始页码',
  `page_end` int DEFAULT NULL COMMENT '结束页码',
  `block_ids` json DEFAULT NULL COMMENT 'OCR/版面block ID列表',
  `bbox_json` json DEFAULT NULL COMMENT '来源坐标 [x1,y1,x2,y2]',
  `metadata_json` json DEFAULT NULL COMMENT '扩展元数据（含section_type）',
  `editor_id` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '编辑人ID',
  `editor_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '编辑人姓名',
  `edit_reason` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '编辑原因',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `base_revision_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chunk_revision` (`chunk_id`,`revision_no`),
  KEY `idx_chunk_id` (`chunk_id`),
  KEY `idx_kb_file` (`kb_id`,`file_node_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Chunk内容版本表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_audit_history`
--

DROP TABLE IF EXISTS `kb_audit_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_audit_history` (
  `id` bigint NOT NULL COMMENT '主键',
  `kb_id` bigint NOT NULL COMMENT '知识库ID',
  `biz_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL COMMENT '业务类型 chunk/qa',
  `biz_id` bigint NOT NULL COMMENT '业务上下文ID（chunk类型=file_node_id, qa类型=qa_pair.id）',
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '本轮裁决 approved/partially_approved/rejected',
  `reviewer` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '审核人ID（system=自动通过）',
  `reviewer_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '审核人姓名',
  `review_comment` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '审核意见/驳回原因',
  `approved_ids` json DEFAULT NULL COMMENT '通过的对象ID列表（chunk ID或QA pair ID）',
  `rejected_ids` json DEFAULT NULL COMMENT '驳回的对象ID列表（chunk ID或QA pair ID）',
  `reviewed_at` datetime(3) NOT NULL COMMENT '裁决时间',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  KEY `idx_kb_time` (`kb_id`,`reviewed_at`),
  KEY `idx_biz` (`biz_type`,`biz_id`,`reviewed_at`),
  KEY `idx_reviewer_time` (`reviewer`,`reviewed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='审核历史归档表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_permission_rule`
--

DROP TABLE IF EXISTS `kb_permission_rule`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_permission_rule` (
  `id` bigint NOT NULL COMMENT '主键',
  `kb_id` bigint NOT NULL COMMENT '知识库ID',
  `rule_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL COMMENT '规则类型 dept/role/user',
  `target_id` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '目标对象ID（部门/角色/用户）',
  `grant_role` varchar(32) COLLATE utf8mb4_general_ci NOT NULL COMMENT '授予角色 admin/reviewer/editor/readonly',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_rule` (`kb_id`,`rule_type`,`target_id`,`grant_role`),
  KEY `idx_target` (`rule_type`,`target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库权限分配表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_operation_log`
--

DROP TABLE IF EXISTS `kb_operation_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_operation_log` (
  `id` bigint NOT NULL COMMENT '主键',
  `kb_id` bigint DEFAULT NULL COMMENT '知识库ID（平台级动作可为空）',
  `operator_id` bigint NOT NULL COMMENT '操作人ID',
  `action` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '动作标识 kb.create/chunk.update/audit.approve等',
  `object_type` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '对象类型 kb/file/chunk/qa/member',
  `object_id` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '对象ID',
  `summary` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '摘要（列表直接展示）',
  `detail_json` json DEFAULT NULL COMMENT '详情 {"before":{},"after":{},"reason":""}',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  KEY `idx_kb_time` (`kb_id`,`create_time`),
  KEY `idx_operator_time` (`operator_id`,`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='操作日志表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_chat_session`
--

DROP TABLE IF EXISTS `kb_chat_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_chat_session` (
  `id` bigint NOT NULL COMMENT '主键，会话ID',
  `kb_id` bigint DEFAULT NULL COMMENT '单库会话时填写，多库/全库时为空',
  `scope_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'single' COMMENT '范围类型 single/multi/all',
  `scope_kb_ids` json DEFAULT NULL COMMENT '多库选中时的kb_id列表',
  `user_id` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '用户ID',
  `session_scope_hash` varchar(128) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '会话知识范围摘要哈希（后端统一计算）',
  `title` varchar(256) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '会话标题（通常自动生成）',
  `last_message_at` datetime(3) DEFAULT NULL COMMENT '最近消息时间（列表排序）',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_user_time` (`user_id`,`last_message_at`),
  KEY `idx_scope_hash` (`session_scope_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='问AI会话表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_chat_message`
--

DROP TABLE IF EXISTS `kb_chat_message`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_chat_message` (
  `id` bigint NOT NULL COMMENT '主键，消息ID',
  `session_id` bigint NOT NULL COMMENT '所属会话ID',
  `kb_id` bigint DEFAULT NULL COMMENT '知识库ID（冗余，便于按库查询/清理）',
  `role` varchar(16) COLLATE utf8mb4_general_ci NOT NULL COMMENT '角色 user/assistant/system',
  `seq_no` int NOT NULL COMMENT '会话内消息顺序号',
  `content` longtext COLLATE utf8mb4_general_ci COMMENT '消息内容',
  `status` varchar(32) COLLATE utf8mb4_general_ci NOT NULL DEFAULT 'completed' COMMENT '状态 generating/completed/interrupted/failed',
  `token_usage` json DEFAULT NULL COMMENT 'token消耗 {"prompt":N,"completion":N,"total":N}',
  `parent_message_id` bigint DEFAULT NULL COMMENT '父消息ID（assistant指向对应user消息）',
  `feedback` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '用户反馈 like/dislike',
  `feedback_comment` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '反馈文本',
  `error_msg` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '失败原因（status=failed时）',
  `trace_id` varchar(64) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '链路追踪ID',
  `finished_at` datetime(3) DEFAULT NULL COMMENT '完成时间（assistant消息有意义）',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  `del_flag` tinyint NOT NULL DEFAULT '0' COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_seq` (`session_id`,`seq_no`),
  KEY `idx_session_time` (`session_id`,`create_time`),
  KEY `idx_parent` (`parent_message_id`),
  KEY `idx_kb_time` (`kb_id`,`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='问AI会话消息表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_chat_message_citation`
--

DROP TABLE IF EXISTS `kb_chat_message_citation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_chat_message_citation` (
  `id` bigint NOT NULL COMMENT '主键',
  `message_id` bigint NOT NULL COMMENT '所属assistant消息ID',
  `session_id` bigint NOT NULL COMMENT '所属会话ID（冗余）',
  `kb_id` bigint NOT NULL COMMENT '所属知识库ID（冗余，聚合用）',
  `biz_type` varchar(16) COLLATE utf8mb4_general_ci NOT NULL COMMENT '业务类型 chunk/qa',
  `biz_id` bigint NOT NULL COMMENT '业务对象ID（kb_chunk.id或kb_qa_pair.id）',
  `file_node_id` bigint DEFAULT NULL COMMENT '所属文件节点ID（biz_type=chunk时填）',
  `rank_no` int DEFAULT NULL COMMENT '召回结果排序号',
  `score` decimal(10,6) DEFAULT NULL COMMENT '召回分数',
  `retriever_type` varchar(16) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '召回通路 vector/keyword/graph/rerank',
  `is_cited` tinyint NOT NULL DEFAULT '0' COMMENT '是否被答案实际(citation:0)=仅召回 1=被引用',
  `cite_index` int DEFAULT NULL COMMENT '被引用时答案中的角标序号（is_cited=1时填）',
  `snippet` varchar(1000) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '命中片段快照',
  `page_num` int DEFAULT NULL COMMENT '源页码',
  `metadata_json` json DEFAULT NULL COMMENT '引用元数据（完整保留检索返回字段）',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_message_biz` (`message_id`,`biz_type`,`biz_id`),
  KEY `idx_message_cited` (`message_id`,`is_cited`),
  KEY `idx_kb_biz` (`kb_id`,`biz_type`,`biz_id`,`is_cited`),
  KEY `idx_file_node` (`file_node_id`,`is_cited`),
  KEY `idx_kb_cited_time` (`kb_id`,`is_cited`,`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='消息召回/引用明细表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_tag`
--

DROP TABLE IF EXISTS `kb_tag`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_tag` (
  `id` bigint NOT NULL COMMENT '主键',
  `name` varchar(128) COLLATE utf8mb4_general_ci NOT NULL COMMENT '标签名称',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_tag_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库标签字典';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `kb_kb_tag`
--

DROP TABLE IF EXISTS `kb_kb_tag`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `kb_kb_tag` (
  `id` bigint NOT NULL COMMENT '主键',
  `kb_id` bigint NOT NULL COMMENT '知识库ID',
  `tag_id` bigint NOT NULL COMMENT '标签ID',
  `create_time` datetime DEFAULT NULL COMMENT '创建时间',
  `update_time` datetime DEFAULT NULL COMMENT '更新时间',
  `creator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人ID',
  `updator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人ID',
  `create_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '创建人姓名',
  `update_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kb_tag` (`kb_id`,`tag_id`),
  KEY `idx_tag_id` (`tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库-标签关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_parse_artifacts`
--

DROP TABLE IF EXISTS `file_parse_artifacts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_parse_artifacts` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `artifact_type` varchar(64) NOT NULL,
  `artifact_path` varchar(1024) DEFAULT NULL,
  `payload_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_artifact_file` (`kb_id`,`file_node_id`,`parse_generation`,`artifact_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_char_map`
--

DROP TABLE IF EXISTS `file_char_map`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_char_map` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `span_id` varchar(128) NOT NULL,
  `text_version` varchar(64) NOT NULL DEFAULT 'norm_v1',
  `global_char_start` int NOT NULL,
  `global_char_end` int NOT NULL,
  `page_no` int DEFAULT NULL,
  `block_id` varchar(128) DEFAULT NULL,
  `bbox_json` json DEFAULT NULL,
  `block_type` varchar(64) DEFAULT NULL,
  `text` longtext,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_char_map_file` (`kb_id`,`file_node_id`,`parse_generation`,`text_version`),
  KEY `idx_char_map_span` (`kb_id`,`file_node_id`,`parse_generation`,`span_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_tables`
--

DROP TABLE IF EXISTS `file_tables`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_tables` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `table_key` varchar(128) NOT NULL,
  `page_no` int DEFAULT NULL,
  `title` varchar(512) DEFAULT NULL,
  `markdown` longtext,
  `bbox_json` json DEFAULT NULL,
  `metadata_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_file_table` (`kb_id`,`file_node_id`,`parse_generation`,`table_key`),
  KEY `idx_file_tables_file` (`kb_id`,`file_node_id`,`parse_generation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_table_columns`
--

DROP TABLE IF EXISTS `file_table_columns`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_table_columns` (
  `id` bigint NOT NULL,
  `table_id` bigint NOT NULL,
  `column_index` int NOT NULL,
  `column_name` varchar(512) DEFAULT NULL,
  `normalized_name` varchar(256) DEFAULT NULL,
  `data_type` varchar(64) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_table_column` (`table_id`,`column_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_table_rows`
--

DROP TABLE IF EXISTS `file_table_rows`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_table_rows` (
  `id` bigint NOT NULL,
  `table_id` bigint NOT NULL,
  `row_index` int NOT NULL,
  `row_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_table_row` (`table_id`,`row_index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_structured_field`
--

DROP TABLE IF EXISTS `file_structured_field`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_structured_field` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `field_code` varchar(64) NOT NULL,
  `field_name_cn` varchar(128) NOT NULL,
  `value_text` longtext,
  `aliases_json` json DEFAULT NULL,
  `normalized_json` json DEFAULT NULL,
  `source_chunk_id` bigint DEFAULT NULL,
  `source_revision_id` bigint DEFAULT NULL,
  `source_section_type` varchar(64) DEFAULT NULL,
  `metadata_json` json DEFAULT NULL,
  `del_flag` tinyint NOT NULL DEFAULT '0',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `field_key` varchar(128) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_field_file` (`kb_id`,`file_node_id`,`parse_generation`,`field_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `field_review_history`
--

DROP TABLE IF EXISTS `field_review_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `field_review_history` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `field_id` bigint NOT NULL,
  `old_value_text` longtext,
  `new_value_text` longtext,
  `old_normalized_json` json DEFAULT NULL,
  `new_normalized_json` json DEFAULT NULL,
  `reason` varchar(512) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `reviewer` varchar(128) DEFAULT NULL,
  `review_status` varchar(32) DEFAULT NULL,
  `evidence_chunk_id` bigint DEFAULT NULL,
  `evidence_quote` longtext,
  PRIMARY KEY (`id`),
  KEY `idx_field_review` (`kb_id`,`file_node_id`,`field_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_field_mentions`
--

DROP TABLE IF EXISTS `file_field_mentions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_field_mentions` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_graph_nodes`
--

DROP TABLE IF EXISTS `file_graph_nodes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_graph_nodes` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_graph_edges`
--

DROP TABLE IF EXISTS `file_graph_edges`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_graph_edges` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_chunk_relations`
--

DROP TABLE IF EXISTS `file_chunk_relations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_chunk_relations` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) NOT NULL,
  `from_chunk_id` bigint NOT NULL,
  `to_chunk_id` bigint NOT NULL,
  `relation_type` varchar(64) NOT NULL,
  `weight` decimal(10,4) NOT NULL DEFAULT '1.0000',
  `properties_json` json DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chunk_relation` (`kb_id`,`file_node_id`,`parse_generation`,`from_chunk_id`,`to_chunk_id`,`relation_type`),
  KEY `idx_chunk_relation_from` (`kb_id`,`file_node_id`,`parse_generation`,`from_chunk_id`),
  KEY `idx_chunk_relation_to` (`kb_id`,`file_node_id`,`parse_generation`,`to_chunk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_index_pointer`
--

DROP TABLE IF EXISTS `file_index_pointer`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_index_pointer` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `current_parse_generation` varchar(128) DEFAULT NULL,
  `current_index_generation` varchar(128) DEFAULT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'none',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `previous_index_generation` varchar(128) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_file_pointer` (`kb_id`,`file_node_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `retrieve_index_state`
--

DROP TABLE IF EXISTS `retrieve_index_state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `retrieve_index_state` (
  `id` bigint NOT NULL,
  `kb_id` bigint NOT NULL,
  `file_node_id` bigint NOT NULL,
  `parse_generation` varchar(128) DEFAULT NULL,
  `index_generation` varchar(128) NOT NULL,
  `target_type` varchar(32) NOT NULL,
  `status` varchar(32) NOT NULL DEFAULT 'pending',
  `indexed_count` int NOT NULL DEFAULT '0',
  `error_msg` varchar(2000) DEFAULT NULL,
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_index_state` (`kb_id`,`file_node_id`,`index_generation`,`target_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-13 14:48:35
