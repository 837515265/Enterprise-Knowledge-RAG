-- ============================================================
-- 企业知识问答管理平台 — 数据库建表脚本
-- 版本: V4.0
-- 数据库: MySQL 8.0 / InnoDB / utf8mb4 / utf8mb4_general_ci
--
-- V4 变更摘要:
--   [1] 代际字段改为语义化字符串: file_{id}_{seq}
--   [2] kb_file_node.id 文件类型直接使用文件ID
--   [3] kb_file_node 移除 parse_result_url/parse_status_cache/parse_result_ref
--   [4] kb_file_node 移除 audit_status，审核粒度下沉到 chunk
--   [5] kb_file_node 新增 parse_status 解析状态
--   [6] kb_file_task 精简字段，stage 覆盖索引阶段
--   [7] kb_qa_pair 移除 evidence_chunk_id
--   [8] kb_audit_history 移除 round_no/file_node_id，重命名 approved/rejected
--   [9] kb_chunk 移除 draft_revision_id，仅保留 latest + published
--   [10] 解析结果由解析引擎直接写入 kb_chunk/kb_chunk_revision
-- ============================================================


-- ============================================================
-- 1. kb_knowledge_base  知识库主表
-- ============================================================
CREATE TABLE `kb_knowledge_base` (
  `id`                     BIGINT        NOT NULL                COMMENT '主键，雪花ID',
  `name`                   VARCHAR(256)  NOT NULL                COMMENT '知识库名称',
  `type`                   VARCHAR(64)   NOT NULL                COMMENT '知识库类型 general/faq/manual 等',
  `description`            VARCHAR(2000) DEFAULT NULL            COMMENT '知识库描述',
  `visibility`             VARCHAR(32)   NOT NULL DEFAULT 'private' COMMENT '公开性 public/private',
  `file_audit_enabled`     TINYINT       NOT NULL DEFAULT 0      COMMENT '文件审核开关 0=关 1=开',
  `qa_audit_enabled`       TINYINT       NOT NULL DEFAULT 0      COMMENT '问答审核开关 0=关 1=开',
  `status`                 VARCHAR(32)   NOT NULL DEFAULT 'active' COMMENT '状态 active/archived',
  `index_collection_id`    VARCHAR(64)   DEFAULT NULL            COMMENT '检索引擎索引集合ID，1KB=1集合',
  `member_count`           INT           NOT NULL DEFAULT 0      COMMENT '权限命中成员数缓存（定时刷新）',
  `parse_strategy_config_id` VARCHAR(64) DEFAULT NULL            COMMENT '默认解析策略配置ID，关联 kb_parse_strategy_config.id',
  `retrieval_config_id`    VARCHAR(64)   DEFAULT NULL            COMMENT '默认检索策略配置ID，关联 kb_retrieval_strategy_config.id',
  `model_profile`          JSON          DEFAULT NULL            COMMENT '默认模型配置引用JSON',
  `create_time`            DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`            DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`                VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`                VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`            VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`            VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`                TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_collection_id` (`index_collection_id`),
  KEY `idx_name` (`name`),
  KEY `idx_visibility_status` (`visibility`, `status`),
  KEY `idx_parse_strategy` (`parse_strategy_config_id`),
  KEY `idx_retrieval_strategy` (`retrieval_config_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库主表';


-- ============================================================
-- 1a. kb_retrieval_strategy_config  检索策略配置表
-- ============================================================
CREATE TABLE `kb_retrieval_strategy_config` (
  `id`                     VARCHAR(64)   NOT NULL                COMMENT '主键，策略配置ID（雪花字符串/UUID）',
  `name`                   VARCHAR(256)  NOT NULL                COMMENT '配置名称',
  `code`                   VARCHAR(64)   DEFAULT NULL            COMMENT '策略编码，便于程序引用',
  `scope_type`             VARCHAR(16)   NOT NULL DEFAULT 'kb' COMMENT '作用域 kb=绑定知识库 template=租户级模板',
  `kb_id`                  BIGINT        DEFAULT NULL            COMMENT 'scope_type=kb 时必填，模板可为空',
  `config_json`            JSON          NOT NULL                COMMENT '检索策略参数（top_k、阈值、混合模式等）',
  `status`                 VARCHAR(32)   NOT NULL DEFAULT 'active' COMMENT '状态 active/disabled',
  `remark`                 VARCHAR(500)  DEFAULT NULL            COMMENT '备注',
  `create_time`            DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`            DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`                VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`                VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`            VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`            VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`                TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_kb_status` (`kb_id`, `status`, `del_flag`),
  KEY `idx_scope_code` (`scope_type`, `code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='检索策略配置表';


-- ============================================================
-- 1b. kb_parse_strategy_config  解析策略配置表（与 1a 字段对称）
-- ============================================================
CREATE TABLE `kb_parse_strategy_config` (
  `id`                     VARCHAR(64)   NOT NULL                COMMENT '主键，策略配置ID（雪花字符串/UUID）',
  `name`                   VARCHAR(256)  NOT NULL                COMMENT '配置名称',
  `code`                   VARCHAR(64)   DEFAULT NULL            COMMENT '策略编码，便于程序引用（如 general/contract）',
  `scope_type`             VARCHAR(16)   NOT NULL DEFAULT 'kb' COMMENT '作用域 kb=绑定知识库 template=租户级模板',
  `kb_id`                  BIGINT        DEFAULT NULL            COMMENT 'scope_type=kb 时必填，模板可为空',
  `config_json`            JSON          NOT NULL                COMMENT '解析策略参数（分块、OCR、版面等）',
  `status`                 VARCHAR(32)   NOT NULL DEFAULT 'active' COMMENT '状态 active/disabled',
  `remark`                 VARCHAR(500)  DEFAULT NULL            COMMENT '备注',
  `create_time`            DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`            DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`                VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`                VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`            VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`            VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`                TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_kb_status` (`kb_id`, `status`, `del_flag`),
  KEY `idx_scope_code` (`scope_type`, `code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='解析策略配置表';


-- ============================================================
-- 2. kb_file_node  文件节点表（文件夹树 + 文件）
--
-- V4 变更:
--   [2] id: 文件类型直接使用文件ID，文件夹类型使用雪花ID
--   [3] 移除 parse_result_url / parse_status_cache / parse_result_ref
--   [4] 移除 audit_status（审核粒度下沉到 chunk）
--   [5] 新增 parse_status 解析状态
--   [1] 代际字段格式: file_{id}_{seq}
-- ============================================================
CREATE TABLE `kb_file_node` (
  `id`                          BIGINT        NOT NULL                COMMENT '主键: 文件类型=文件ID, 文件夹类型=雪花ID',
  `kb_id`                       BIGINT        NOT NULL                COMMENT '所属知识库ID',
  `parent_id`                   BIGINT        DEFAULT NULL            COMMENT '父节点ID，根目录下为空',
  `node_type`                   VARCHAR(16)   NOT NULL                COMMENT '节点类型 folder/file',
  `name`                        VARCHAR(512)  NOT NULL                COMMENT '节点名称（文件夹名或展示文件名）',
  `original_name`               VARCHAR(512)  DEFAULT NULL            COMMENT '用户上传原始文件名（仅file）',
  `file_id`                     VARCHAR(64)   DEFAULT NULL            COMMENT '对象存储中的原始文件ID（仅file）',
  `file_size`                   BIGINT        DEFAULT NULL            COMMENT '文件字节数（仅file）',
  `mime_type`                   VARCHAR(128)  DEFAULT NULL            COMMENT 'MIME类型（仅file）',
  `file_ext`                    VARCHAR(16)   DEFAULT NULL            COMMENT '扩展名 pdf/docx/xlsx（仅file）',
  `file_hash`                   VARCHAR(64)   DEFAULT NULL            COMMENT '文件SHA-256，去重防篡改（仅file）',
  `parse_strategy_config_id`    VARCHAR(64)   DEFAULT NULL            COMMENT '上传可选的解析策略配置ID，NULL 则解析时采用 kb_knowledge_base.parse_strategy_config_id',
  `parse_status`                VARCHAR(32)   NOT NULL DEFAULT 'none' COMMENT '解析状态 none/parsing/parsed/failed',
  `index_status`                VARCHAR(32)   NOT NULL DEFAULT 'none' COMMENT '索引状态 none/indexing/synced/failed',
  `current_parse_generation`    VARCHAR(128)  DEFAULT NULL            COMMENT '当前成功解析代际，格式: file_{id}_{seq}',
  `current_index_generation`    VARCHAR(128)  DEFAULT NULL            COMMENT '当前已发布索引代际，格式: file_{id}_{seq}',
  `create_time`                 DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`                 DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`                     VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`                     VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`                 VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`                 VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`                     TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kb_file_id` (`kb_id`, `file_id`),
  KEY `idx_kb_hash` (`kb_id`, `file_hash`),
  KEY `idx_kb_parent` (`kb_id`, `parent_id`),
  KEY `idx_kb_parse_status` (`kb_id`, `parse_status`),
  KEY `idx_kb_index_status` (`kb_id`, `index_status`),
  KEY `idx_file_parse_strategy` (`parse_strategy_config_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='文件节点表';


-- ============================================================
-- 3. kb_file_task  文件解析与索引任务表
--
-- V4 变更:
--   [6] stage 覆盖索引阶段；status 代表解析状态；index_sync_status 代表索引同步状态
--   [6] 移除 trace_id / idempotent_key / last_heartbeat_at / retry_count / max_retry
--   [1] 代际字段格式: file_{id}_{seq}
-- ============================================================
CREATE TABLE `kb_file_task` (
  `id`                  BIGINT        NOT NULL                COMMENT '主键，任务ID',
  `kb_id`               BIGINT        NOT NULL                COMMENT '知识库ID',
  `file_node_id`        BIGINT        NOT NULL                COMMENT '对应kb_file_node.id',
  `stage`               VARCHAR(32)   NOT NULL                COMMENT '当前阶段 parse/chunk/embed/index/done',
  `status`              VARCHAR(32)   NOT NULL DEFAULT 'pending' COMMENT '解析状态 pending/processing/success/failed',
  `error_msg`           VARCHAR(2000) DEFAULT NULL            COMMENT '最近一次失败原因',
  `parse_result_url`    VARCHAR(1024) DEFAULT NULL            COMMENT '解析产物JSON地址（引擎写入）',
  `indexed_chunk_count` INT           NOT NULL DEFAULT 0      COMMENT '已写入检索索引的Chunk数',
  `index_sync_status`   VARCHAR(32)   NOT NULL DEFAULT 'none' COMMENT '索引同步状态 none/syncing/synced/failed',
  `parse_generation`    VARCHAR(128)  DEFAULT NULL            COMMENT '本任务解析代际，格式: file_{id}_{seq}',
  `index_generation`    VARCHAR(128)  DEFAULT NULL            COMMENT '本任务索引代际，格式: file_{id}_{seq}',
  `engine_task_id`      VARCHAR(128)  DEFAULT NULL            COMMENT '解析检索服务内部任务ID',
  `parse_strategy_config_id` VARCHAR(64) DEFAULT NULL        COMMENT '本任务实际采用的解析策略配置ID（上传指定优先，否则知识库默认，创建任务时固化快照）',
  `model_profile`       JSON          DEFAULT NULL            COMMENT '本任务模型配置JSON快照（创建任务时从知识库复制，不再变更）',
  `create_time`         DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`         DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`             VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`             VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`         VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`         VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_file_node` (`file_node_id`),
  KEY `idx_kb_stage_status` (`kb_id`, `stage`, `status`),
  KEY `idx_status_time` (`status`, `update_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='文件解析与索引任务表';


-- ============================================================
-- 4. kb_qa_pair  知识库问答对表
--
-- V4 变更:
--   [7] 移除 evidence_chunk_id
-- ============================================================
CREATE TABLE `kb_qa_pair` (
  `id`                  BIGINT        NOT NULL                COMMENT '主键，问答ID',
  `kb_id`               BIGINT        NOT NULL                COMMENT '知识库ID',
  `question`            LONGTEXT      NOT NULL                COMMENT '问题',
  `answer`              LONGTEXT      NOT NULL                COMMENT '答案',
  `audit_status`        VARCHAR(32)   NOT NULL DEFAULT 'pending' COMMENT '审核状态 pending/approved/rejected',
  `index_sync_status`   VARCHAR(32)   NOT NULL DEFAULT 'none' COMMENT '索引同步状态 none/synced/failed',
  `index_record_id`     VARCHAR(64)   DEFAULT NULL            COMMENT '检索引擎中的记录ID',
  `sync_error_message`  VARCHAR(1000) DEFAULT NULL            COMMENT '同步失败原因',
  `extended_questions`  JSON          DEFAULT NULL            COMMENT '扩展问法列表',
  `create_time`         DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`         DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`             VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`             VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`         VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`         VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`             TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_kb_audit` (`kb_id`, `audit_status`),
  KEY `idx_kb_sync` (`kb_id`, `index_sync_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库问答对表';


-- ============================================================
-- 5. kb_chunk  Chunk 主数据表（当前态 SSOT）
--
-- V4 变更:
--   [9] 移除 draft_revision_id，仅保留 latest_revision_id + published_revision_id
--       开启审核时: latest_revision_id 即为待审核版本，无需额外提交节点
--   [10] 初始数据由解析引擎直接写入，编辑数据由业务系统写入
--   [1] 代际字段格式: file_{id}_{seq}
-- ============================================================
CREATE TABLE `kb_chunk` (
  `id`                      BIGINT        NOT NULL                COMMENT '主键，chunk业务主键',
  `kb_id`                   BIGINT        NOT NULL                COMMENT '知识库ID',
  `file_node_id`            BIGINT        NOT NULL                COMMENT '所属文件节点ID',
  `seq_no`                  INT           NOT NULL                COMMENT '文件内顺序号',
  `content`                 LONGTEXT      NOT NULL                COMMENT '当前展示内容（冗余published_revision内容）',
  `summary`                 VARCHAR(1000) DEFAULT NULL            COMMENT '当前展示摘要',
  `enabled`                 TINYINT       NOT NULL DEFAULT 0      COMMENT '是否参与检索 0=否 1=是',
  `audit_status`            VARCHAR(32)   NOT NULL DEFAULT 'pending' COMMENT '审核状态 pending/approved/rejected',
  `reject_reason`           VARCHAR(500)  DEFAULT NULL            COMMENT '驳回原因',
  `index_record_id`         VARCHAR(64)   DEFAULT NULL            COMMENT '检索引擎中的记录ID',
  `index_sync_status`       VARCHAR(32)   NOT NULL DEFAULT 'none' COMMENT '索引同步状态 none/synced/failed',
  `sync_error_msg`          VARCHAR(1000) DEFAULT NULL            COMMENT '同步失败原因',
  `published_revision_id`   BIGINT        DEFAULT NULL            COMMENT '当前已审核发布版本，关联kb_chunk_revision.id',
  `latest_revision_id`      BIGINT        DEFAULT NULL            COMMENT '最新版本（待审核或已发布），关联kb_chunk_revision.id',
  `parse_generation`        VARCHAR(128)  DEFAULT NULL            COMMENT '来源解析代际，格式: file_{id}_{seq}',
  `index_generation`        VARCHAR(128)  DEFAULT NULL            COMMENT '当前已同步索引代际，格式: file_{id}_{seq}',
  `content_hash`            VARCHAR(64)   DEFAULT NULL            COMMENT '当前发布内容hash',
  `page_start`              INT           DEFAULT NULL            COMMENT '起始页码',
  `page_end`                INT           DEFAULT NULL            COMMENT '结束页码',
  `chunk_type`              VARCHAR(32)   DEFAULT 'original'      COMMENT 'chunk类型 original/section_summary/clause/slide/table_row',
  `section_type`            VARCHAR(64)   DEFAULT NULL            COMMENT '业务章节类型 credit_limit/access_condition等',
  `section_id`              VARCHAR(128)  DEFAULT NULL            COMMENT '章节/条款/slide ID',
  `chunk_group_id`          VARCHAR(128)  DEFAULT NULL            COMMENT 'EvidenceGroup归并ID',
  `block_ids`               JSON          DEFAULT NULL            COMMENT 'OCR/版面block ID列表',
  `metadata_json`           JSON          DEFAULT NULL            COMMENT '解析输出扩展元数据（版面、章节等；解析策略以文件节点/任务侧 parse_strategy_config_id 为准）',
  `create_time`             DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`             DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`                 VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`                 VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`             VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`             VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`                 TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_file_seq` (`file_node_id`, `seq_no`),
  KEY `idx_kb_enabled` (`kb_id`, `enabled`),
  KEY `idx_kb_audit` (`kb_id`, `audit_status`),
  KEY `idx_sync` (`index_sync_status`),
  KEY `idx_chunk_group` (`chunk_group_id`),
  KEY `idx_parse_gen` (`parse_generation`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Chunk主数据表';


-- ============================================================
-- 6. kb_chunk_revision  Chunk 内容版本表
-- ============================================================
CREATE TABLE `kb_chunk_revision` (
  `id`                      BIGINT        NOT NULL                COMMENT '主键，revision ID',
  `kb_id`                   BIGINT        NOT NULL                COMMENT '知识库ID',
  `file_node_id`            BIGINT        NOT NULL                COMMENT '文件节点ID',
  `chunk_id`                BIGINT        NOT NULL                COMMENT '关联kb_chunk.id',
  `revision_no`             INT           NOT NULL                COMMENT '版本号，从1递增',
  `revision_source`         VARCHAR(32)   NOT NULL                COMMENT '版本来源 parse/manual_edit/audit_edit',
  `content`                 LONGTEXT      NOT NULL                COMMENT '本revision内容',
  `summary`                 VARCHAR(1000) DEFAULT NULL            COMMENT '本revision摘要',
  `content_for_embedding`   LONGTEXT      DEFAULT NULL            COMMENT '向量检索文本（含短前缀增强）',
  `content_for_bm25`        LONGTEXT      DEFAULT NULL            COMMENT 'BM25全文检索文本（含别名增强）',
  `title`                   VARCHAR(512)  DEFAULT NULL            COMMENT 'chunk标题',
  `title_path`              JSON          DEFAULT NULL            COMMENT '标题层级路径 ["服务方案","授信额度"]',
  `page_start`              INT           DEFAULT NULL            COMMENT '起始页码',
  `page_end`                INT           DEFAULT NULL            COMMENT '结束页码',
  `block_ids`               JSON          DEFAULT NULL            COMMENT 'OCR/版面block ID列表',
  `bbox_json`               JSON          DEFAULT NULL            COMMENT '来源坐标 [x1,y1,x2,y2]',
  `metadata_json`           JSON          DEFAULT NULL            COMMENT '扩展元数据（含section_type）',
  `editor_id`               VARCHAR(255)  DEFAULT NULL            COMMENT '编辑人ID',
  `editor_name`             VARCHAR(255)  DEFAULT NULL            COMMENT '编辑人姓名',
  `edit_reason`             VARCHAR(500)  DEFAULT NULL            COMMENT '编辑原因',
  `create_time`             DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`             DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`                 VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`                 VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`             VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`             VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chunk_revision` (`chunk_id`, `revision_no`),
  KEY `idx_chunk_id` (`chunk_id`),
  KEY `idx_kb_file` (`kb_id`, `file_node_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Chunk内容版本表';


-- ============================================================
-- 7. kb_audit_history  审核历史归档表
--
-- V4 变更:
--   [8] biz_type 区分 chunk / qa（不存在审文件的情况）
--   [8] biz_id = file_node_id（chunk审核时为文件节点ID）
--   [8] 移除 round_no
--   [8] approved_chunk_ids → approved_ids（可含chunk ID或QA ID）
--   [8] rejected_chunk_ids → rejected_ids
-- ============================================================
CREATE TABLE `kb_audit_history` (
  `id`                    BIGINT        NOT NULL                COMMENT '主键',
  `kb_id`                 BIGINT        NOT NULL                COMMENT '知识库ID',
  `biz_type`              VARCHAR(16)   NOT NULL                COMMENT '业务类型 chunk/qa',
  `biz_id`                BIGINT        NOT NULL                COMMENT '业务上下文ID（chunk类型=file_node_id, qa类型=qa_pair.id）',
  `status`                VARCHAR(32)   NOT NULL                COMMENT '本轮裁决 approved/partially_approved/rejected',
  `reviewer`              VARCHAR(255)  NOT NULL                COMMENT '审核人ID（system=自动通过）',
  `reviewer_name`         VARCHAR(255)  DEFAULT NULL            COMMENT '审核人姓名',
  `review_comment`        VARCHAR(1000) DEFAULT NULL            COMMENT '审核意见/驳回原因',
  `approved_ids`          JSON          DEFAULT NULL            COMMENT '通过的对象ID列表（chunk ID或QA pair ID）',
  `rejected_ids`          JSON          DEFAULT NULL            COMMENT '驳回的对象ID列表（chunk ID或QA pair ID）',
  `reviewed_at`           DATETIME(3)   NOT NULL                COMMENT '裁决时间',
  `create_time`           DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`           DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`               VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`               VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`           VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`           VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  KEY `idx_kb_time` (`kb_id`, `reviewed_at`),
  KEY `idx_biz` (`biz_type`, `biz_id`, `reviewed_at`),
  KEY `idx_reviewer_time` (`reviewer`, `reviewed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='审核历史归档表';


-- ============================================================
-- 8. kb_permission_rule  知识库权限分配表
-- ============================================================
CREATE TABLE `kb_permission_rule` (
  `id`            BIGINT        NOT NULL                COMMENT '主键',
  `kb_id`         BIGINT        NOT NULL                COMMENT '知识库ID',
  `rule_type`     VARCHAR(16)   NOT NULL                COMMENT '规则类型 dept/role/user',
  `target_id`     VARCHAR(128)  NOT NULL                COMMENT '目标对象ID（部门/角色/用户）',
  `grant_role`    VARCHAR(32)   NOT NULL                COMMENT '授予角色 admin/reviewer/editor/readonly',
  `create_time`   DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`   DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`       VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`       VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_rule` (`kb_id`, `rule_type`, `target_id`, `grant_role`),
  KEY `idx_target` (`rule_type`, `target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库权限分配表';


-- ============================================================
-- 9. kb_operation_log  操作日志表
-- ============================================================
CREATE TABLE `kb_operation_log` (
  `id`            BIGINT        NOT NULL                COMMENT '主键',
  `kb_id`         BIGINT        DEFAULT NULL            COMMENT '知识库ID（平台级动作可为空）',
  `operator_id`   BIGINT        NOT NULL                COMMENT '操作人ID',
  `action`        VARCHAR(64)   NOT NULL                COMMENT '动作标识 kb.create/chunk.update/audit.approve等',
  `object_type`   VARCHAR(64)   DEFAULT NULL            COMMENT '对象类型 kb/file/chunk/qa/member',
  `object_id`     VARCHAR(128)  DEFAULT NULL            COMMENT '对象ID',
  `summary`       VARCHAR(512)  DEFAULT NULL            COMMENT '摘要（列表直接展示）',
  `detail_json`   JSON          DEFAULT NULL            COMMENT '详情 {"before":{},"after":{},"reason":""}',
  `create_time`   DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`   DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`       VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`       VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  KEY `idx_kb_time` (`kb_id`, `create_time`),
  KEY `idx_operator_time` (`operator_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='操作日志表';


-- ============================================================
-- 10. kb_chat_session  问AI会话表
-- ============================================================
CREATE TABLE `kb_chat_session` (
  `id`                    BIGINT        NOT NULL                COMMENT '主键，会话ID',
  `kb_id`                 BIGINT        DEFAULT NULL            COMMENT '单库会话时填写，多库/全库时为空',
  `scope_type`            VARCHAR(16)   NOT NULL DEFAULT 'single' COMMENT '范围类型 single/multi/all',
  `scope_kb_ids`          JSON          DEFAULT NULL            COMMENT '多库选中时的kb_id列表',
  `user_id`               VARCHAR(64)   NOT NULL                COMMENT '用户ID',
  `session_scope_hash`    VARCHAR(128)  DEFAULT NULL            COMMENT '会话知识范围摘要哈希（后端统一计算）',
  `title`                 VARCHAR(256)  DEFAULT NULL            COMMENT '会话标题（通常自动生成）',
  `last_message_at`       DATETIME(3)   DEFAULT NULL            COMMENT '最近消息时间（列表排序）',
  `create_time`           DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`           DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`               VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`               VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`           VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`           VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`               TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  KEY `idx_user_time` (`user_id`, `last_message_at`),
  KEY `idx_scope_hash` (`session_scope_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='问AI会话表';


-- ============================================================
-- 11. kb_chat_message  问AI会话消息表
-- ============================================================
CREATE TABLE `kb_chat_message` (
  `id`                  BIGINT        NOT NULL                COMMENT '主键，消息ID',
  `session_id`          BIGINT        NOT NULL                COMMENT '所属会话ID',
  `kb_id`               BIGINT        DEFAULT NULL            COMMENT '知识库ID（冗余，便于按库查询/清理）',
  `role`                VARCHAR(16)   NOT NULL                COMMENT '角色 user/assistant/system',
  `seq_no`              INT           NOT NULL                COMMENT '会话内消息顺序号',
  `content`             LONGTEXT      DEFAULT NULL            COMMENT '消息内容',
  `status`              VARCHAR(32)   NOT NULL DEFAULT 'completed' COMMENT '状态 generating/completed/interrupted/failed',
  `token_usage`         JSON          DEFAULT NULL            COMMENT 'token消耗 {"prompt":N,"completion":N,"total":N}',
  `parent_message_id`   BIGINT        DEFAULT NULL            COMMENT '父消息ID（assistant指向对应user消息）',
  `feedback`            VARCHAR(16)   DEFAULT NULL            COMMENT '用户反馈 like/dislike',
  `feedback_comment`    VARCHAR(500)  DEFAULT NULL            COMMENT '反馈文本',
  `error_msg`           VARCHAR(1000) DEFAULT NULL            COMMENT '失败原因（status=failed时）',
  `trace_id`            VARCHAR(64)   DEFAULT NULL            COMMENT '链路追踪ID',
  `finished_at`         DATETIME(3)   DEFAULT NULL            COMMENT '完成时间（assistant消息有意义）',
  `create_time`         DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`         DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`             VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`             VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`         VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`         VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  `del_flag`             TINYINT       NOT NULL DEFAULT 0      COMMENT '逻辑删除 0=正常 1=已删除',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_seq` (`session_id`, `seq_no`),
  KEY `idx_session_time` (`session_id`, `create_time`),
  KEY `idx_parent` (`parent_message_id`),
  KEY `idx_kb_time` (`kb_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='问AI会话消息表';


-- ============================================================
-- 12. kb_chat_message_citation  消息召回/引用明细表
-- ============================================================
CREATE TABLE `kb_chat_message_citation` (
  `id`              BIGINT        NOT NULL                COMMENT '主键',
  `message_id`      BIGINT        NOT NULL                COMMENT '所属assistant消息ID',
  `session_id`      BIGINT        NOT NULL                COMMENT '所属会话ID（冗余）',
  `kb_id`           BIGINT        NOT NULL                COMMENT '所属知识库ID（冗余，聚合用）',
  `biz_type`        VARCHAR(16)   NOT NULL                COMMENT '业务类型 chunk/qa',
  `biz_id`          BIGINT        NOT NULL                COMMENT '业务对象ID（kb_chunk.id或kb_qa_pair.id）',
  `file_node_id`    BIGINT        DEFAULT NULL            COMMENT '所属文件节点ID（biz_type=chunk时填）',
  `rank_no`         INT           DEFAULT NULL            COMMENT '召回结果排序号',
  `score`           DECIMAL(10,6) DEFAULT NULL            COMMENT '召回分数',
  `retriever_type`  VARCHAR(16)   DEFAULT NULL            COMMENT '召回通路 vector/keyword/graph/rerank',
  `is_cited`        TINYINT       NOT NULL DEFAULT 0      COMMENT '是否被答案实际(citation:0)=仅召回 1=被引用',
  `cite_index`      INT           DEFAULT NULL            COMMENT '被引用时答案中的角标序号（is_cited=1时填）',
  `snippet`         VARCHAR(1000) DEFAULT NULL            COMMENT '命中片段快照',
  `page_num`        INT           DEFAULT NULL            COMMENT '源页码',
  `metadata_json`   JSON          DEFAULT NULL            COMMENT '引用元数据（完整保留检索返回字段）',
  `create_time`     DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`     DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`         VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`         VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`     VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`     VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_message_biz` (`message_id`, `biz_type`, `biz_id`),
  KEY `idx_message_cited` (`message_id`, `is_cited`),
  KEY `idx_kb_biz` (`kb_id`, `biz_type`, `biz_id`, `is_cited`),
  KEY `idx_file_node` (`file_node_id`, `is_cited`),
  KEY `idx_kb_cited_time` (`kb_id`, `is_cited`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='消息召回/引用明细表';


-- ============================================================
-- 13. kb_tag  知识库标签字典
-- ============================================================
CREATE TABLE `kb_tag` (
  `id`            BIGINT        NOT NULL                COMMENT '主键',
  `name`          VARCHAR(128)  NOT NULL                COMMENT '标签名称',
  `create_time`   DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`   DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`       VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`       VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_tag_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库标签字典';


-- ============================================================
-- 14. kb_kb_tag  知识库-标签关联表
-- ============================================================
CREATE TABLE `kb_kb_tag` (
  `id`            BIGINT        NOT NULL                COMMENT '主键',
  `kb_id`         BIGINT        NOT NULL                COMMENT '知识库ID',
  `tag_id`        BIGINT        NOT NULL                COMMENT '标签ID',
  `create_time`   DATETIME      DEFAULT NULL            COMMENT '创建时间',
  `update_time`   DATETIME      DEFAULT NULL            COMMENT '更新时间',
  `creator`       VARCHAR(255)  DEFAULT NULL            COMMENT '创建人ID',
  `updator`       VARCHAR(255)  DEFAULT NULL            COMMENT '更新人ID',
  `create_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '创建人姓名',
  `update_name`   VARCHAR(255)  DEFAULT NULL            COMMENT '更新人姓名',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kb_tag` (`kb_id`, `tag_id`),
  KEY `idx_tag_id` (`tag_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='知识库-标签关联表';


-- ============================================================
-- 已建库补丁：kb_file_node 增加对象存储文件ID
-- 说明：
-- 1. 新库请直接使用上面的 CREATE TABLE 定义。
-- 2. 已执行过旧版 v1.0.0.sql 的库，按需执行以下 ALTER。
-- 3. 如果索引不存在或已调整过，对应 ALTER 可跳过。
-- ============================================================
ALTER TABLE `kb_file_node`
  ADD COLUMN `file_id` VARCHAR(64) DEFAULT NULL COMMENT '对象存储中的原始文件ID（仅file）' AFTER `original_name`;

ALTER TABLE `kb_file_node`
  ADD UNIQUE KEY `uk_kb_file_id` (`kb_id`, `file_id`);

-- 前端当前 file_hash 可能传空字符串，唯一索引会导致同一知识库批量上传多个空 hash 文件失败。
ALTER TABLE `kb_file_node`
  DROP INDEX `uk_kb_hash`;

ALTER TABLE `kb_file_node`
  ADD KEY `idx_kb_hash` (`kb_id`, `file_hash`);

-- kb_file_task.model_profile 需要保存知识库级 JSON 快照，不能使用 VARCHAR(64)。
ALTER TABLE `kb_file_task`
  MODIFY COLUMN `model_profile` JSON DEFAULT NULL COMMENT '本任务模型配置JSON快照（创建任务时从知识库复制，不再变更）';
