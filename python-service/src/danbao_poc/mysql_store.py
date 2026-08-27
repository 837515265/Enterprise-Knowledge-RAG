from __future__ import annotations

import json
import os
import hashlib
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import unquote

import pymysql
from pymysql.cursors import DictCursor

from .anchor_deduper import extract_anchor_merge_candidates
from .ids import new_id
from .validation import validate_relation_payload


def connect():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "danbao"),
        password=os.getenv("MYSQL_PASSWORD", "danbao123456"),
        database=os.getenv("MYSQL_DATABASE", "danbao"),
        charset="utf8mb4",
        collation=os.getenv("MYSQL_COLLATION", "utf8mb4_general_ci"),
        init_command=f"SET NAMES utf8mb4 COLLATE {os.getenv('MYSQL_COLLATION', 'utf8mb4_general_ci')}",
        cursorclass=DictCursor,
        autocommit=False,
    )


def _j(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def clean_identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return "_".join(part for part in text.replace("-", "_").split() if part)[:256] or None


def init_db() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS kb_knowledge_base (
          id BIGINT PRIMARY KEY,
          name VARCHAR(256) NOT NULL,
          type VARCHAR(64) NOT NULL DEFAULT 'general',
          file_audit_enabled TINYINT NOT NULL DEFAULT 0,
          retrieval_config_id VARCHAR(64) DEFAULT NULL,
          model_profile JSON DEFAULT NULL,
          del_flag TINYINT NOT NULL DEFAULT 0,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_file_node (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          node_type VARCHAR(16) NOT NULL DEFAULT 'file',
          name VARCHAR(512) NOT NULL,
          original_name VARCHAR(512) DEFAULT NULL,
          file_id VARCHAR(128) DEFAULT NULL,
          file_size BIGINT DEFAULT NULL,
          mime_type VARCHAR(128) DEFAULT NULL,
          file_ext VARCHAR(16) DEFAULT NULL,
          profile VARCHAR(64) NOT NULL DEFAULT 'guarantee_plan',
          parse_result_ref VARCHAR(1024) DEFAULT NULL,
          file_hash VARCHAR(64) DEFAULT NULL,
          audit_status VARCHAR(32) NOT NULL DEFAULT 'approved',
          parse_status VARCHAR(32) NOT NULL DEFAULT 'none',
          index_status VARCHAR(32) NOT NULL DEFAULT 'none',
          current_parse_generation VARCHAR(128) DEFAULT NULL,
          current_index_generation VARCHAR(128) DEFAULT NULL,
          del_flag TINYINT NOT NULL DEFAULT 0,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY idx_kb_parse (kb_id, parse_status),
          KEY idx_kb_index (kb_id, index_status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_file_task (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL UNIQUE,
          stage VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'pending',
          error_msg VARCHAR(2000) DEFAULT NULL,
          parse_result_url VARCHAR(1024) DEFAULT NULL,
          indexed_chunk_count INT NOT NULL DEFAULT 0,
          index_sync_status VARCHAR(32) NOT NULL DEFAULT 'none',
          parse_generation VARCHAR(128) DEFAULT NULL,
          index_generation VARCHAR(128) DEFAULT NULL,
          engine_task_id VARCHAR(128) DEFAULT NULL,
          parse_strategy_config_id VARCHAR(64) DEFAULT NULL,
          model_profile VARCHAR(64) DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_file_task_history (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          task_type VARCHAR(32) NOT NULL,
          stage VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'pending',
          parse_generation VARCHAR(128) DEFAULT NULL,
          index_generation VARCHAR(128) DEFAULT NULL,
          engine_task_id VARCHAR(128) DEFAULT NULL,
          error_msg VARCHAR(2000) DEFAULT NULL,
          payload_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY idx_task_history_file (kb_id, file_node_id, task_type, create_time),
          KEY idx_task_history_generation (kb_id, file_node_id, parse_generation, index_generation)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_qa_pair (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT DEFAULT NULL,
          question LONGTEXT NOT NULL,
          answer LONGTEXT NOT NULL,
          audit_status VARCHAR(32) NOT NULL DEFAULT 'pending',
          index_sync_status VARCHAR(32) NOT NULL DEFAULT 'none',
          index_record_id VARCHAR(64) DEFAULT NULL,
          sync_error_message VARCHAR(1000) DEFAULT NULL,
          extended_questions JSON DEFAULT NULL,
          answer_type VARCHAR(64) DEFAULT 'manual_qa',
          generation_source VARCHAR(64) DEFAULT 'manual_import',
          source_type VARCHAR(64) DEFAULT NULL,
          source_chunk_ids_json JSON DEFAULT NULL,
          source_field_ids_json JSON DEFAULT NULL,
          evidence_quotes_json JSON DEFAULT NULL,
          confidence DECIMAL(6,4) DEFAULT NULL,
          priority INT NOT NULL DEFAULT 0,
          manual_override TINYINT NOT NULL DEFAULT 0,
          metadata_json JSON DEFAULT NULL,
          del_flag TINYINT NOT NULL DEFAULT 0,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY idx_qa_kb_audit (kb_id, audit_status, del_flag),
          KEY idx_qa_file_source (kb_id, file_node_id, generation_source, del_flag)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_chunk (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          seq_no INT NOT NULL,
          content LONGTEXT NOT NULL,
          summary VARCHAR(1000) DEFAULT NULL,
          enabled TINYINT NOT NULL DEFAULT 0,
          audit_status VARCHAR(32) NOT NULL DEFAULT 'pending',
          index_sync_status VARCHAR(32) NOT NULL DEFAULT 'none',
          published_revision_id BIGINT DEFAULT NULL,
          latest_revision_id BIGINT DEFAULT NULL,
          draft_revision_id BIGINT DEFAULT NULL,
          parse_generation VARCHAR(128) DEFAULT NULL,
          index_generation VARCHAR(128) DEFAULT NULL,
          content_hash VARCHAR(64) DEFAULT NULL,
          sim_hash VARCHAR(64) DEFAULT NULL,
          reject_reason VARCHAR(1000) DEFAULT NULL,
          page_start INT DEFAULT NULL,
          page_end INT DEFAULT NULL,
          chunk_type VARCHAR(32) DEFAULT 'original',
          section_type VARCHAR(64) DEFAULT NULL,
          section_id VARCHAR(128) DEFAULT NULL,
          primary_chunk_id BIGINT DEFAULT NULL,
          parent_chunk_id BIGINT DEFAULT NULL,
          chunk_group_id VARCHAR(128) DEFAULT NULL,
          block_ids JSON DEFAULT NULL,
          metadata_json JSON DEFAULT NULL,
          del_flag TINYINT NOT NULL DEFAULT 0,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY idx_chunk_file (file_node_id, seq_no),
          KEY idx_chunk_parse (kb_id, file_node_id, parse_generation),
          KEY idx_chunk_primary (kb_id, primary_chunk_id),
          KEY idx_chunk_enabled (kb_id, enabled, audit_status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_chunk_revision (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          chunk_id BIGINT NOT NULL,
          base_revision_id BIGINT DEFAULT NULL,
          revision_no INT NOT NULL,
          revision_source VARCHAR(32) NOT NULL,
          editor_id VARCHAR(128) DEFAULT NULL,
          editor_name VARCHAR(128) DEFAULT NULL,
          edit_reason VARCHAR(512) DEFAULT NULL,
          content LONGTEXT NOT NULL,
          summary VARCHAR(1000) DEFAULT NULL,
          content_for_embedding LONGTEXT DEFAULT NULL,
          content_for_bm25 LONGTEXT DEFAULT NULL,
          title VARCHAR(512) DEFAULT NULL,
          title_path JSON DEFAULT NULL,
          page_start INT DEFAULT NULL,
          page_end INT DEFAULT NULL,
          block_ids JSON DEFAULT NULL,
          bbox_json JSON DEFAULT NULL,
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_chunk_revision (chunk_id, revision_no),
          KEY idx_revision_file (kb_id, file_node_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_section (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          section_id VARCHAR(128) NOT NULL,
          parent_section_id VARCHAR(128) DEFAULT NULL,
          section_title VARCHAR(512) DEFAULT NULL,
          section_path TEXT DEFAULT NULL,
          section_level INT DEFAULT NULL,
          section_type VARCHAR(128) DEFAULT NULL,
          seq_start INT DEFAULT NULL,
          seq_end INT DEFAULT NULL,
          page_start INT DEFAULT NULL,
          page_end INT DEFAULT NULL,
          covered_chunk_ids_json JSON DEFAULT NULL,
          block_ids JSON DEFAULT NULL,
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_kb_section (kb_id, file_node_id, parse_generation, section_id),
          KEY idx_section_file (file_node_id, parse_generation),
          KEY idx_section_path (kb_id, section_type),
          KEY idx_parent_section (kb_id, file_node_id, parent_section_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_section_summary (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          section_id VARCHAR(128) NOT NULL,
          section_title VARCHAR(512) DEFAULT NULL,
          section_path TEXT DEFAULT NULL,
          section_level INT DEFAULT NULL,
          summary_type VARCHAR(64) NOT NULL DEFAULT 'node_summary',
          node_summary LONGTEXT DEFAULT NULL,
          structured_summary_json JSON DEFAULT NULL,
          covered_chunk_ids_json JSON DEFAULT NULL,
          summary_source VARCHAR(64) DEFAULT NULL,
          confidence VARCHAR(32) DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY idx_section_summary_file (kb_id, file_node_id, parse_generation),
          KEY idx_section_summary_section (kb_id, file_node_id, section_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_section_summary_evidence (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          summary_id BIGINT NOT NULL,
          section_id VARCHAR(128) NOT NULL,
          chunk_id BIGINT DEFAULT NULL,
          revision_id BIGINT DEFAULT NULL,
          evidence_quote LONGTEXT DEFAULT NULL,
          evidence_role VARCHAR(64) DEFAULT 'source_quote',
          char_start INT DEFAULT NULL,
          char_end INT DEFAULT NULL,
          page_no INT DEFAULT NULL,
          block_ids JSON DEFAULT NULL,
          bbox_json JSON DEFAULT NULL,
          alignment_status VARCHAR(32) DEFAULT NULL,
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_summary_evidence_summary (kb_id, file_node_id, parse_generation, summary_id),
          KEY idx_summary_evidence_section (kb_id, file_node_id, parse_generation, section_id),
          KEY idx_summary_evidence_chunk (kb_id, chunk_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_anchor_registry (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          anchor_id VARCHAR(128) NOT NULL,
          anchor_type VARCHAR(64) NOT NULL,
          anchor_name VARCHAR(512) NOT NULL,
          normalized_name VARCHAR(512) DEFAULT NULL,
          aliases_json JSON DEFAULT NULL,
          source_section_id VARCHAR(128) DEFAULT NULL,
          source_chunk_id BIGINT DEFAULT NULL,
          evidence_quote LONGTEXT DEFAULT NULL,
          confidence DECIMAL(6,4) DEFAULT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'active',
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_anchor (kb_id, file_node_id, parse_generation, anchor_id),
          KEY idx_anchor_scope (kb_id, anchor_type, normalized_name(128)),
          KEY idx_anchor_file (kb_id, file_node_id, parse_generation)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_knowledge_unit (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          unit_id VARCHAR(128) NOT NULL,
          unit_type VARCHAR(64) NOT NULL,
          unit_subtype VARCHAR(128) DEFAULT NULL,
          anchor_id VARCHAR(128) DEFAULT NULL,
          subject_text VARCHAR(512) DEFAULT NULL,
          predicate_text VARCHAR(512) DEFAULT NULL,
          object_text LONGTEXT DEFAULT NULL,
          value_type VARCHAR(64) DEFAULT NULL,
          normalized_json JSON DEFAULT NULL,
          source_section_id VARCHAR(128) DEFAULT NULL,
          primary_chunk_id BIGINT DEFAULT NULL,
          evidence_quote LONGTEXT DEFAULT NULL,
          confidence DECIMAL(6,4) DEFAULT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'active',
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_knowledge_unit (kb_id, file_node_id, parse_generation, unit_id),
          KEY idx_unit_type (kb_id, unit_type, unit_subtype),
          KEY idx_unit_anchor (kb_id, anchor_id),
          KEY idx_unit_chunk (kb_id, primary_chunk_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_knowledge_unit_evidence (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          unit_id VARCHAR(128) NOT NULL,
          chunk_id BIGINT NOT NULL,
          revision_id BIGINT DEFAULT NULL,
          evidence_quote LONGTEXT DEFAULT NULL,
          char_start INT DEFAULT NULL,
          char_end INT DEFAULT NULL,
          page_no INT DEFAULT NULL,
          block_ids JSON DEFAULT NULL,
          bbox_json JSON DEFAULT NULL,
          alignment_status VARCHAR(32) DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_unit_evidence_unit (kb_id, file_node_id, parse_generation, unit_id),
          KEY idx_unit_evidence_chunk (kb_id, chunk_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_relation (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          relation_id VARCHAR(128) NOT NULL,
          relation_type VARCHAR(128) NOT NULL,
          from_type VARCHAR(64) NOT NULL,
          from_id VARCHAR(128) NOT NULL,
          to_type VARCHAR(64) NOT NULL,
          to_id VARCHAR(128) NOT NULL,
          source_chunk_id BIGINT DEFAULT NULL,
          evidence_quote LONGTEXT DEFAULT NULL,
          confidence DECIMAL(6,4) DEFAULT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'active',
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_kb_relation (kb_id, file_node_id, parse_generation, relation_id),
          KEY idx_relation_from (kb_id, from_type, from_id),
          KEY idx_relation_to (kb_id, to_type, to_id),
          KEY idx_relation_type (kb_id, relation_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_knowledge_candidate_pool (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          candidate_id VARCHAR(128) NOT NULL,
          candidate_type VARCHAR(32) NOT NULL,
          normalized_target_id VARCHAR(128) DEFAULT NULL,
          candidate_status VARCHAR(32) NOT NULL DEFAULT 'validated',
          merge_group_key VARCHAR(256) DEFAULT NULL,
          review_status VARCHAR(32) NOT NULL DEFAULT 'auto_accepted',
          confidence DECIMAL(6,4) DEFAULT NULL,
          source_section_id VARCHAR(128) DEFAULT NULL,
          source_chunk_id BIGINT DEFAULT NULL,
          evidence_quote LONGTEXT DEFAULT NULL,
          raw_payload_json JSON DEFAULT NULL,
          decision_payload_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_knowledge_candidate (kb_id, file_node_id, parse_generation, candidate_id),
          KEY idx_candidate_type (kb_id, file_node_id, parse_generation, candidate_type),
          KEY idx_candidate_status (kb_id, candidate_status, review_status),
          KEY idx_candidate_merge (kb_id, merge_group_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS knowledge_anchor_merge_candidate (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          left_anchor_id VARCHAR(128) NOT NULL,
          right_anchor_id VARCHAR(128) NOT NULL,
          left_anchor_name VARCHAR(512) DEFAULT NULL,
          right_anchor_name VARCHAR(512) DEFAULT NULL,
          left_anchor_type VARCHAR(64) DEFAULT NULL,
          right_anchor_type VARCHAR(64) DEFAULT NULL,
          similarity_score DECIMAL(8,4) DEFAULT NULL,
          similarity_reason VARCHAR(256) DEFAULT NULL,
          decision VARCHAR(32) NOT NULL DEFAULT 'pending_review',
          status VARCHAR(32) NOT NULL DEFAULT 'pending',
          reviewer VARCHAR(128) DEFAULT NULL,
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_anchor_merge_candidate (kb_id, file_node_id, parse_generation, left_anchor_id, right_anchor_id),
          KEY idx_anchor_merge_status (kb_id, decision, status),
          KEY idx_anchor_merge_left (kb_id, left_anchor_id),
          KEY idx_anchor_merge_right (kb_id, right_anchor_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_parse_artifacts (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          artifact_type VARCHAR(64) NOT NULL,
          artifact_path VARCHAR(1024) DEFAULT NULL,
          payload_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_artifact_file (kb_id, file_node_id, parse_generation, artifact_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_parse_cache (
          id BIGINT PRIMARY KEY,
          file_hash VARCHAR(128) NOT NULL,
          parser_profile VARCHAR(64) NOT NULL,
          parser_name VARCHAR(128) NOT NULL,
          parser_version VARCHAR(128) NOT NULL,
          parse_options_hash VARCHAR(128) NOT NULL,
          source_file_name VARCHAR(512) DEFAULT NULL,
          middle_document_json LONGTEXT NOT NULL,
          raw_payload_json LONGTEXT DEFAULT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'success',
          hit_count INT NOT NULL DEFAULT 0,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_file_parse_cache (file_hash, parser_profile, parser_name, parser_version, parse_options_hash),
          KEY idx_file_parse_cache_hash (file_hash, parser_profile, parser_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_char_map (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          span_id VARCHAR(128) NOT NULL,
          text_version VARCHAR(64) NOT NULL DEFAULT 'norm_v1',
          global_char_start INT NOT NULL,
          global_char_end INT NOT NULL,
          page_no INT DEFAULT NULL,
          block_id VARCHAR(128) DEFAULT NULL,
          line_no INT DEFAULT NULL,
          bbox_json JSON DEFAULT NULL,
          positions_json JSON DEFAULT NULL,
          source_type VARCHAR(64) DEFAULT NULL,
          block_type VARCHAR(64) DEFAULT NULL,
          text LONGTEXT DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_char_map_file (kb_id, file_node_id, parse_generation, text_version),
          KEY idx_char_map_span (kb_id, file_node_id, parse_generation, span_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_tables (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          table_key VARCHAR(128) NOT NULL,
          page_no INT DEFAULT NULL,
          title VARCHAR(512) DEFAULT NULL,
          markdown LONGTEXT DEFAULT NULL,
          bbox_json JSON DEFAULT NULL,
          metadata_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uk_file_table (kb_id, file_node_id, parse_generation, table_key),
          KEY idx_file_tables_file (kb_id, file_node_id, parse_generation)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_table_columns (
          id BIGINT PRIMARY KEY,
          table_id BIGINT NOT NULL,
          column_index INT NOT NULL,
          column_name VARCHAR(512) DEFAULT NULL,
          normalized_name VARCHAR(256) DEFAULT NULL,
          data_type VARCHAR(64) DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uk_table_column (table_id, column_index)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_table_rows (
          id BIGINT PRIMARY KEY,
          table_id BIGINT NOT NULL,
          row_index INT NOT NULL,
          row_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uk_table_row (table_id, row_index)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_structured_field (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          field_key VARCHAR(128) DEFAULT NULL,
          field_code VARCHAR(64) NOT NULL,
          field_name_cn VARCHAR(128) NOT NULL,
          value_text LONGTEXT DEFAULT NULL,
          aliases_json JSON DEFAULT NULL,
          normalized_json JSON DEFAULT NULL,
          source_chunk_id BIGINT DEFAULT NULL,
          source_revision_id BIGINT DEFAULT NULL,
          source_section_type VARCHAR(64) DEFAULT NULL,
          metadata_json JSON DEFAULT NULL,
          del_flag TINYINT NOT NULL DEFAULT 0,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          KEY idx_field_file (kb_id, file_node_id, parse_generation, field_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS field_review_history (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          field_id BIGINT NOT NULL,
          old_value_text LONGTEXT DEFAULT NULL,
          new_value_text LONGTEXT DEFAULT NULL,
          old_normalized_json JSON DEFAULT NULL,
          new_normalized_json JSON DEFAULT NULL,
          reason VARCHAR(512) DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_field_review (kb_id, file_node_id, field_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_field_mentions (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          field_id BIGINT NOT NULL,
          chunk_id BIGINT NOT NULL,
          revision_id BIGINT DEFAULT NULL,
          evidence_text LONGTEXT DEFAULT NULL,
          char_start INT DEFAULT NULL,
          char_end INT DEFAULT NULL,
          alignment_status VARCHAR(32) DEFAULT NULL,
          page_no INT DEFAULT NULL,
          block_ids JSON DEFAULT NULL,
          bbox_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_mentions_field (kb_id, file_node_id, parse_generation, field_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_graph_nodes (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          node_key VARCHAR(128) NOT NULL,
          node_type VARCHAR(64) NOT NULL,
          name_cn VARCHAR(512) DEFAULT NULL,
          value_text LONGTEXT DEFAULT NULL,
          source_field_id BIGINT DEFAULT NULL,
          source_chunk_id BIGINT DEFAULT NULL,
          properties_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uk_graph_node (kb_id, file_node_id, parse_generation, node_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_graph_edges (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          edge_type VARCHAR(64) NOT NULL,
          from_node_key VARCHAR(128) NOT NULL,
          to_node_key VARCHAR(128) NOT NULL,
          source_field_id BIGINT DEFAULT NULL,
          source_chunk_id BIGINT DEFAULT NULL,
          properties_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          KEY idx_graph_edge (kb_id, file_node_id, parse_generation, edge_type),
          UNIQUE KEY uk_graph_edge_fact (kb_id, file_node_id, parse_generation, edge_type, from_node_key, to_node_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_chunk_relations (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) NOT NULL,
          from_chunk_id BIGINT NOT NULL,
          to_chunk_id BIGINT NOT NULL,
          relation_type VARCHAR(64) NOT NULL,
          weight DECIMAL(10,4) NOT NULL DEFAULT 1.0,
          properties_json JSON DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uk_chunk_relation (kb_id, file_node_id, parse_generation, from_chunk_id, to_chunk_id, relation_type),
          KEY idx_chunk_relation_from (kb_id, file_node_id, parse_generation, from_chunk_id),
          KEY idx_chunk_relation_to (kb_id, file_node_id, parse_generation, to_chunk_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS file_index_pointer (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          current_parse_generation VARCHAR(128) DEFAULT NULL,
          current_index_generation VARCHAR(128) DEFAULT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'none',
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_file_pointer (kb_id, file_node_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS retrieve_index_state (
          id BIGINT PRIMARY KEY,
          kb_id BIGINT NOT NULL,
          file_node_id BIGINT NOT NULL,
          parse_generation VARCHAR(128) DEFAULT NULL,
          index_generation VARCHAR(128) NOT NULL,
          target_type VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'pending',
          indexed_count INT NOT NULL DEFAULT 0,
          error_msg VARCHAR(2000) DEFAULT NULL,
          create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
          update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uk_index_state (kb_id, file_node_id, index_generation, target_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                try:
                    cur.execute(statement)
                except pymysql.err.OperationalError as exc:
                    if exc.args[0] in (1050, 1142):
                        continue
                    raise
            for ddl in [
                "ALTER TABLE file_index_pointer ADD COLUMN previous_index_generation VARCHAR(128) DEFAULT NULL",
                "ALTER TABLE kb_file_node ADD COLUMN profile VARCHAR(64) NOT NULL DEFAULT 'guarantee_plan'",
                "ALTER TABLE kb_file_node ADD COLUMN parse_result_ref VARCHAR(1024) DEFAULT NULL",
                "ALTER TABLE kb_file_node ADD COLUMN file_id VARCHAR(128) DEFAULT NULL",
                "ALTER TABLE kb_file_node ADD COLUMN file_hash VARCHAR(64) DEFAULT NULL",
                "ALTER TABLE kb_file_node ADD COLUMN audit_status VARCHAR(32) NOT NULL DEFAULT 'approved'",
                "ALTER TABLE kb_file_task ADD COLUMN parse_strategy_config_id VARCHAR(64) DEFAULT NULL",
                "ALTER TABLE kb_chunk ADD COLUMN draft_revision_id BIGINT DEFAULT NULL",
                "ALTER TABLE kb_chunk ADD COLUMN sim_hash VARCHAR(64) DEFAULT NULL",
                "ALTER TABLE kb_chunk ADD COLUMN reject_reason VARCHAR(1000) DEFAULT NULL",
                "ALTER TABLE kb_chunk ADD COLUMN primary_chunk_id BIGINT DEFAULT NULL",
                "ALTER TABLE kb_chunk ADD COLUMN parent_chunk_id BIGINT DEFAULT NULL",
                "ALTER TABLE kb_chunk ADD KEY idx_chunk_primary (kb_id, primary_chunk_id)",
                "ALTER TABLE kb_chunk_revision ADD COLUMN base_revision_id BIGINT DEFAULT NULL",
                "ALTER TABLE kb_chunk_revision ADD COLUMN editor_id VARCHAR(128) DEFAULT NULL",
                "ALTER TABLE kb_chunk_revision ADD COLUMN editor_name VARCHAR(128) DEFAULT NULL",
                "ALTER TABLE kb_chunk_revision ADD COLUMN edit_reason VARCHAR(512) DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD COLUMN file_node_id BIGINT DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD COLUMN answer_type VARCHAR(64) DEFAULT 'manual_qa'",
                "ALTER TABLE kb_qa_pair ADD COLUMN generation_source VARCHAR(64) DEFAULT 'manual_import'",
                "ALTER TABLE kb_qa_pair ADD COLUMN source_type VARCHAR(64) DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD COLUMN source_chunk_ids_json JSON DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD COLUMN source_field_ids_json JSON DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD COLUMN evidence_quotes_json JSON DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD COLUMN confidence DECIMAL(6,4) DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD COLUMN priority INT NOT NULL DEFAULT 0",
                "ALTER TABLE kb_qa_pair ADD COLUMN manual_override TINYINT NOT NULL DEFAULT 0",
                "ALTER TABLE kb_qa_pair ADD COLUMN metadata_json JSON DEFAULT NULL",
                "ALTER TABLE kb_qa_pair ADD INDEX idx_qa_file_source (kb_id, file_node_id, generation_source, del_flag)",
                "ALTER TABLE file_structured_field ADD COLUMN field_key VARCHAR(128) DEFAULT NULL",
                "ALTER TABLE field_review_history ADD COLUMN reviewer VARCHAR(128) DEFAULT NULL",
                "ALTER TABLE field_review_history ADD COLUMN review_status VARCHAR(32) DEFAULT NULL",
                "ALTER TABLE field_review_history ADD COLUMN evidence_chunk_id BIGINT DEFAULT NULL",
                "ALTER TABLE field_review_history ADD COLUMN evidence_quote LONGTEXT DEFAULT NULL",
                "ALTER TABLE file_field_mentions ADD COLUMN char_start INT DEFAULT NULL",
                "ALTER TABLE file_field_mentions ADD COLUMN char_end INT DEFAULT NULL",
                "ALTER TABLE file_field_mentions ADD COLUMN alignment_status VARCHAR(32) DEFAULT NULL",
                "ALTER TABLE file_char_map ADD COLUMN line_no INT DEFAULT NULL",
                "ALTER TABLE file_char_map ADD COLUMN positions_json JSON DEFAULT NULL",
                "ALTER TABLE file_char_map ADD COLUMN source_type VARCHAR(64) DEFAULT NULL",
                "ALTER TABLE file_graph_edges ADD UNIQUE KEY uk_graph_edge_fact (kb_id, file_node_id, parse_generation, edge_type, from_node_key, to_node_key)",
            ]:
                try:
                    cur.execute(ddl)
                except Exception:
                    pass
        conn.commit()


def next_parse_generation(file_node_id: int) -> str:
    prefix = f"file_{file_node_id}_"
    candidates: list[str] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_parse_generation FROM kb_file_node WHERE id = %s", (file_node_id,))
            row = cur.fetchone()
            if row and row.get("current_parse_generation"):
                candidates.append(row["current_parse_generation"])
            for table in [
                "kb_chunk",
                "kb_section",
                "kb_section_summary",
                "kb_section_summary_evidence",
                "kb_anchor_registry",
                "kb_knowledge_unit",
                "kb_knowledge_unit_evidence",
                "kb_relation",
                "kb_knowledge_candidate_pool",
                "file_structured_field",
                "file_parse_artifacts",
                "file_field_mentions",
                "file_graph_nodes",
                "file_graph_edges",
            ]:
                cur.execute(
                    f"""
                    SELECT parse_generation
                    FROM {table}
                    WHERE file_node_id = %s AND parse_generation LIKE %s
                    """,
                    (file_node_id, f"{prefix}%"),
                )
                candidates.extend(item["parse_generation"] for item in cur.fetchall() if item.get("parse_generation"))
    max_seq = 0
    for candidate in candidates:
        if not candidate.startswith(prefix):
            continue
        suffix = candidate[len(prefix) :]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    seq = max_seq + 1
    return f"file_{file_node_id}_{seq:03d}"


def find_file_node_by_file_id(kb_id: int, file_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, kb_id, file_id, name, parse_status, index_status, del_flag
                FROM kb_file_node
                WHERE kb_id=%s AND file_id=%s AND del_flag=0
                LIMIT 1
                """,
                (kb_id, file_id),
            )
            return cur.fetchone()


def load_parse_cache(
    *,
    file_hash: str,
    parser_profile: str,
    parser_name: str,
    parser_version: str,
    parse_options_hash: str,
) -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM file_parse_cache
                WHERE file_hash=%s
                  AND parser_profile=%s
                  AND parser_name=%s
                  AND parser_version=%s
                  AND parse_options_hash=%s
                  AND status='success'
                LIMIT 1
                """,
                (file_hash, parser_profile, parser_name, parser_version, parse_options_hash),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("UPDATE file_parse_cache SET hit_count=hit_count+1 WHERE id=%s", (row["id"],))
        conn.commit()
    try:
        middle_document = json.loads(row.get("middle_document_json") or "{}")
        raw_payload = json.loads(row.get("raw_payload_json") or "{}")
    except Exception:
        return None
    return {
        "source_file_name": row.get("source_file_name"),
        "middle_document": middle_document,
        "raw_payload": raw_payload,
        "hit_count": row.get("hit_count") or 0,
    }


def save_parse_cache(
    *,
    file_hash: str,
    parser_profile: str,
    parser_name: str,
    parser_version: str,
    parse_options_hash: str,
    source_file_name: str,
    middle_document: dict[str, Any],
    raw_payload: dict[str, Any],
) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_parse_cache(
                  id, file_hash, parser_profile, parser_name, parser_version,
                  parse_options_hash, source_file_name, middle_document_json,
                  raw_payload_json, status
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'success')
                ON DUPLICATE KEY UPDATE
                  source_file_name=VALUES(source_file_name),
                  middle_document_json=VALUES(middle_document_json),
                  raw_payload_json=VALUES(raw_payload_json),
                  status='success',
                  update_time=CURRENT_TIMESTAMP
                """,
                (
                    new_id(),
                    file_hash,
                    parser_profile,
                    parser_name,
                    parser_version,
                    parse_options_hash,
                    source_file_name,
                    json.dumps(middle_document, ensure_ascii=False),
                    json.dumps(raw_payload, ensure_ascii=False),
                ),
            )
        conn.commit()


def next_index_generation(file_node_id: int) -> str:
    prefix = f"index_{file_node_id}_"
    candidates: list[str] = []
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_index_generation FROM kb_file_node WHERE id = %s", (file_node_id,))
            row = cur.fetchone()
            if row and row.get("current_index_generation"):
                candidates.append(row["current_index_generation"])
            for table, column in [
                ("kb_chunk", "index_generation"),
                ("retrieve_index_state", "index_generation"),
                ("file_index_pointer", "current_index_generation"),
            ]:
                cur.execute(
                    f"""
                    SELECT {column} AS index_generation
                    FROM {table}
                    WHERE file_node_id = %s AND {column} LIKE %s
                    """,
                    (file_node_id, f"{prefix}%"),
                )
                candidates.extend(item["index_generation"] for item in cur.fetchall() if item.get("index_generation"))
    max_seq = 0
    for candidate in candidates:
        if not candidate.startswith(prefix):
            continue
        suffix = candidate[len(prefix) :]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    seq = max_seq + 1
    return f"index_{file_node_id}_{seq:03d}"


def mark_parse_failed(kb_id: int, file_node_id: int, parse_generation: str | None, error_msg: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kb_file_task(id, kb_id, file_node_id, stage, status, parse_generation, error_msg)
                VALUES (%s, %s, %s, 'parse', 'failed', %s, %s)
                ON DUPLICATE KEY UPDATE stage='parse', status='failed', parse_generation=VALUES(parse_generation), error_msg=VALUES(error_msg), update_time=CURRENT_TIMESTAMP
                """,
                (new_id(), kb_id, file_node_id, parse_generation, error_msg[:2000]),
            )
            cur.execute(
                """
                UPDATE kb_file_node
                SET parse_status='failed', index_status='none', current_parse_generation=%s
                WHERE id=%s AND kb_id=%s
                """,
                (parse_generation, file_node_id, kb_id),
            )
        conn.commit()


def save_parse_result(payload: dict[str, Any]) -> dict[str, Any]:
    kb_id = payload["kb_id"]
    file_node_id = payload["file_node_id"]
    parse_generation = payload["parse_generation"]
    engine_task_id = str(payload.get("engine_task_id") or parse_generation)
    parse_strategy_config_id = payload.get("parse_strategy_config_id")
    parse_result_url = payload.get("parse_result_url")
    model_profile_name = payload.get("model_profile_name")
    platform_task_id = payload.get("platform_task_id")
    try:
        task_row_id = int(platform_task_id) if platform_task_id is not None and str(platform_task_id).isdigit() else new_id()
    except Exception:
        task_row_id = new_id()
    chunks = payload["chunks"]
    sections = payload.get("sections") or []
    section_summaries = payload.get("section_summaries") or []
    fields = payload["fields"]
    qa_pairs = payload.get("qa_pairs") or []
    anchors = payload.get("anchors") or []
    knowledge_units = payload.get("knowledge_units") or []
    knowledge_relations = payload.get("relations") or []
    parse_options = payload.get("parse_options") or {}
    graph_nodes = payload["graph_nodes"]
    graph_edges = payload["graph_edges"]
    artifacts = payload["artifacts"]
    tables = payload.get("tables") or []
    char_map_payload = payload.get("char_map") or {}
    char_spans = char_map_payload.get("spans") or []
    normalized_text = "\n".join(str(span.get("text") or "") for span in char_spans)

    def _nested_option(path: str, default: Any = None) -> Any:
        current: Any = parse_options
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current.get(part)
        return current

    try:
        candidate_auto_accept_confidence = float(
            _nested_option("knowledge.min_auto_accept_confidence", _nested_option("knowledge.candidate_review_threshold", 0.5))
        )
    except (TypeError, ValueError):
        candidate_auto_accept_confidence = 0.5

    def _align_evidence(evidence_text: str | None) -> tuple[int | None, int | None, str | None]:
        evidence = (evidence_text or "").strip()
        if not evidence or not normalized_text:
            return None, None, "missing_text"
        pos = normalized_text.find(evidence)
        if pos >= 0:
            return pos, pos + len(evidence), "exact"
        compact_norm = "".join(normalized_text.split())
        compact_evidence = "".join(evidence.split())
        if compact_evidence:
            compact_pos = compact_norm.find(compact_evidence)
            if compact_pos >= 0:
                return None, None, "compact_matched"
        offset = 0
        best: tuple[float, int, int] = (0.0, -1, -1)
        for line in normalized_text.splitlines(keepends=True):
            line_text = line.rstrip("\r\n")
            if line_text:
                ratio = SequenceMatcher(None, evidence, line_text).ratio()
                if ratio > best[0]:
                    best = (ratio, offset, offset + len(line_text))
            offset += len(line)
        if best[0] >= 0.78:
            return best[1], best[2], "fuzzy"
        return None, None, "not_found"
    with connect() as conn:
        with conn.cursor() as cur:
            # 知识库必须由上游先创建。文件解析只读取 KB 配置，绝不创建或回写
            # kb_knowledge_base，避免单个文件反向改变整个知识库的 profile。
            cur.execute(
                "SELECT file_audit_enabled FROM kb_knowledge_base WHERE id = %s AND del_flag = 0",
                (kb_id,),
            )
            knowledge_base = cur.fetchone()
            if not knowledge_base:
                raise RuntimeError(f"knowledge base not found: kb_id={kb_id}")
            file_audit_enabled = int(knowledge_base.get("file_audit_enabled") or 0)
            enabled = 0 if file_audit_enabled else 1
            audit_status = "pending" if file_audit_enabled else "approved"

            cur.execute(
                """
                INSERT INTO kb_file_node(id, kb_id, node_type, name, original_name, file_id, file_size, mime_type, file_ext, profile, file_hash, audit_status, parse_status, index_status, current_parse_generation, current_index_generation)
                VALUES (%s, %s, 'file', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'parsing', 'none', %s, NULL)
                ON DUPLICATE KEY UPDATE
                    kb_id = VALUES(kb_id),
                    node_type = 'file',
                    file_id = VALUES(file_id),
                    file_size = VALUES(file_size),
                    mime_type = VALUES(mime_type),
                    file_ext = VALUES(file_ext),
                    profile = VALUES(profile),
                    file_hash = VALUES(file_hash),
                    audit_status = VALUES(audit_status),
                    parse_status = 'parsing',
                    current_parse_generation = VALUES(current_parse_generation),
                    current_index_generation = NULL,
                    update_time = CURRENT_TIMESTAMP
                """,
                (
                    file_node_id,
                    kb_id,
                    payload["file_name"],
                    payload["file_name"],
                    payload.get("file_id"),
                    payload.get("file_size"),
                    payload.get("mime_type"),
                    payload.get("file_ext"),
                    payload.get("profile") or "guarantee_plan",
                    payload.get("file_hash"),
                    audit_status,
                    parse_generation,
                ),
            )
            cur.execute(
                """
                INSERT INTO kb_file_task(id, kb_id, file_node_id, stage, status, parse_generation, engine_task_id, parse_strategy_config_id, model_profile)
                VALUES (%s, %s, %s, 'parse', 'processing', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE stage='parse', status='processing', error_msg=NULL, parse_generation=VALUES(parse_generation), engine_task_id=VALUES(engine_task_id), parse_strategy_config_id=VALUES(parse_strategy_config_id), model_profile=VALUES(model_profile), update_time=CURRENT_TIMESTAMP
                """,
                (task_row_id, kb_id, file_node_id, parse_generation, engine_task_id, parse_strategy_config_id, model_profile_name),
            )
            cur.execute(
                """
                INSERT INTO kb_file_task_history(id, kb_id, file_node_id, task_type, stage, status, parse_generation, engine_task_id, payload_json)
                VALUES (%s, %s, %s, 'parse', 'parse', 'success', %s, %s, %s)
                """,
                (
                    new_id(),
                    kb_id,
                    file_node_id,
                    parse_generation,
                    engine_task_id,
                    _j(
                        {
                            "file_name": payload.get("file_name"),
                            "profile": payload.get("profile"),
                            "platform_task_id": platform_task_id,
                            "parse_strategy_config_id": parse_strategy_config_id,
                        }
                    ),
                ),
            )
            cur.execute("UPDATE kb_chunk SET del_flag = 1, enabled = 0, index_sync_status = 'none', index_generation = NULL WHERE kb_id = %s AND file_node_id = %s AND del_flag = 0", (kb_id, file_node_id))
            cur.execute("UPDATE file_structured_field SET del_flag = 1 WHERE kb_id = %s AND file_node_id = %s AND del_flag = 0", (kb_id, file_node_id))
            cur.execute(
                """
                DELETE r FROM file_table_rows r
                JOIN file_tables t ON t.id = r.table_id
                WHERE t.kb_id = %s AND t.file_node_id = %s AND t.parse_generation = %s
                """,
                (kb_id, file_node_id, parse_generation),
            )
            cur.execute(
                """
                DELETE c FROM file_table_columns c
                JOIN file_tables t ON t.id = c.table_id
                WHERE t.kb_id = %s AND t.file_node_id = %s AND t.parse_generation = %s
                """,
                (kb_id, file_node_id, parse_generation),
            )
            for table in ["kb_section", "kb_section_summary", "kb_section_summary_evidence", "kb_anchor_registry", "kb_knowledge_unit", "kb_knowledge_unit_evidence", "kb_relation", "kb_knowledge_candidate_pool", "knowledge_anchor_merge_candidate", "file_parse_artifacts", "file_char_map", "file_tables", "file_field_mentions", "file_graph_nodes", "file_graph_edges", "file_chunk_relations"]:
                cur.execute(f"DELETE FROM {table} WHERE kb_id = %s AND file_node_id = %s AND parse_generation = %s", (kb_id, file_node_id, parse_generation))

            chunk_map: dict[str, tuple[int, int]] = {}
            chunks_by_key: dict[str, dict[str, Any]] = {}
            chunk_rows_for_relations: list[dict[str, Any]] = []
            for chunk in chunks:
                chunk_id, revision_id = new_id(), new_id()
                chunk_map[chunk["chunk_key"]] = (chunk_id, revision_id)
                chunks_by_key[str(chunk["chunk_key"])] = chunk
                if chunk.get("chunk_type") == "small_chunk" or (chunk.get("metadata") or {}).get("retrieval_role") != "context":
                    chunk_rows_for_relations.append({**chunk, "id": chunk_id})
                cur.execute(
                    """
                    INSERT INTO kb_chunk(id, kb_id, file_node_id, seq_no, content, summary, enabled, audit_status, published_revision_id, latest_revision_id, draft_revision_id, parse_generation, index_generation, content_hash, sim_hash, page_start, page_end, chunk_type, section_type, section_id, chunk_group_id, block_ids, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk_id,
                        kb_id,
                        file_node_id,
                        chunk["seq_no"],
                        chunk["content"],
                        chunk.get("summary"),
                        enabled,
                        audit_status,
                        revision_id if enabled else None,
                        revision_id,
                        parse_generation,
                        chunk.get("content_hash"),
                        chunk.get("sim_hash") or chunk.get("content_hash"),
                        chunk.get("page_start"),
                        chunk.get("page_end"),
                        chunk.get("chunk_type"),
                        chunk.get("section_type"),
                        chunk.get("section_id"),
                        chunk.get("chunk_group_id"),
                        _j(chunk.get("block_ids")),
                        _j(chunk.get("metadata")),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO kb_chunk_revision(id, kb_id, file_node_id, chunk_id, revision_no, revision_source, content, summary, content_for_embedding, content_for_bm25, title, title_path, page_start, page_end, block_ids, bbox_json, metadata_json)
                    VALUES (%s, %s, %s, %s, 1, 'parse', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (revision_id, kb_id, file_node_id, chunk_id, chunk["content"], chunk.get("summary"), chunk.get("content_for_embedding"), chunk.get("content_for_bm25"), chunk.get("title"), _j(chunk.get("title_path")), chunk.get("page_start"), chunk.get("page_end"), _j(chunk.get("block_ids")), _j(chunk.get("bbox")), _j(chunk.get("metadata"))),
                )

            child_context_by_key: dict[str, str] = {}
            for chunk in chunks:
                metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
                if chunk.get("chunk_type") not in {"section_chunk", "parent_chunk"}:
                    continue
                for child_key in metadata.get("child_chunk_keys") or []:
                    if child_key in chunk_map:
                        child_context_by_key[str(child_key)] = str(chunk.get("chunk_key"))
            for chunk in chunks:
                chunk_key = str(chunk.get("chunk_key") or "")
                if chunk_key not in chunk_map:
                    continue
                metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
                chunk_id = chunk_map[chunk_key][0]
                primary_key = metadata.get("primary_chunk_key")
                if not primary_key and chunk.get("chunk_type") == "small_chunk":
                    primary_key = chunk_key
                if not primary_key:
                    child_keys = metadata.get("child_chunk_keys") or []
                    primary_key = child_keys[0] if child_keys else None
                primary_chunk_id = chunk_map.get(str(primary_key or ""), (None, None))[0] or (chunk_id if chunk.get("chunk_type") == "small_chunk" else None)
                parent_key = child_context_by_key.get(chunk_key)
                parent_chunk_id = chunk_map.get(str(parent_key or ""), (None, None))[0] if parent_key else None
                cur.execute(
                    """
                    UPDATE kb_chunk
                    SET primary_chunk_id=%s, parent_chunk_id=%s
                    WHERE id=%s AND kb_id=%s
                    """,
                    (primary_chunk_id, parent_chunk_id, chunk_id, kb_id),
                )

            section_id_map: dict[str, int] = {}
            for section in sections:
                section_row_id = new_id()
                section_id_map[str(section.get("section_id"))] = section_row_id
                covered_chunk_ids = [
                    chunk_map[key][0]
                    for key in (section.get("chunk_keys") or [])
                    if key in chunk_map
                ]
                cur.execute(
                    """
                    INSERT INTO kb_section(
                      id, kb_id, file_node_id, parse_generation, section_id, parent_section_id,
                      section_title, section_path, section_level, section_type,
                      seq_start, seq_end, page_start, page_end,
                      covered_chunk_ids_json, block_ids, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      parent_section_id=VALUES(parent_section_id),
                      section_title=VALUES(section_title),
                      section_path=VALUES(section_path),
                      section_level=VALUES(section_level),
                      section_type=VALUES(section_type),
                      seq_start=VALUES(seq_start),
                      seq_end=VALUES(seq_end),
                      page_start=VALUES(page_start),
                      page_end=VALUES(page_end),
                      covered_chunk_ids_json=VALUES(covered_chunk_ids_json),
                      block_ids=VALUES(block_ids),
                      metadata_json=VALUES(metadata_json),
                      update_time=CURRENT_TIMESTAMP
                    """,
                    (
                        section_row_id,
                        kb_id,
                        file_node_id,
                        parse_generation,
                        section.get("section_id"),
                        section.get("parent_section_id"),
                        section.get("section_title"),
                        " > ".join(str(item) for item in (section.get("section_path") or []) if item),
                        section.get("section_level"),
                        section.get("section_type"),
                        section.get("seq_start"),
                        section.get("seq_end"),
                        section.get("page_start"),
                        section.get("page_end"),
                        _j(covered_chunk_ids),
                        _j(section.get("block_ids") or []),
                        _j(section.get("metadata") or {}),
                    ),
                )

            section_summary_evidence_count = 0
            for summary in section_summaries:
                covered_chunk_ids = [
                    chunk_map[key][0]
                    for key in (summary.get("covered_chunk_keys") or [])
                    if key in chunk_map
                ]
                summary_id = new_id()
                cur.execute(
                    """
                    INSERT INTO kb_section_summary(
                      id, kb_id, file_node_id, parse_generation, section_id, section_title,
                      section_path, section_level, summary_type, node_summary,
                      structured_summary_json, covered_chunk_ids_json, summary_source, confidence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        summary_id,
                        kb_id,
                        file_node_id,
                        parse_generation,
                        summary.get("section_id"),
                        summary.get("section_title"),
                        " > ".join(str(item) for item in (summary.get("section_path") or []) if item),
                        summary.get("section_level"),
                        summary.get("summary_type") or "node_summary",
                        summary.get("node_summary"),
                        _j(summary.get("structured_summary") or {}),
                        _j(covered_chunk_ids),
                        summary.get("summary_source"),
                        summary.get("confidence"),
                    ),
                )
                for evidence in summary.get("evidence_quotes") or []:
                    if isinstance(evidence, str):
                        evidence_quote = evidence
                        evidence_chunk_key = None
                        evidence_role = "source_quote"
                        metadata = {}
                    elif isinstance(evidence, dict):
                        evidence_quote = evidence.get("quote") or evidence.get("evidence_quote") or evidence.get("text")
                        evidence_chunk_key = evidence.get("chunk_key")
                        evidence_role = evidence.get("evidence_role") or "source_quote"
                        metadata = {key: value for key, value in evidence.items() if key not in {"quote", "evidence_quote", "text", "chunk_key", "evidence_role"}}
                    else:
                        continue
                    evidence_quote = str(evidence_quote or "").strip()
                    if not evidence_quote:
                        continue
                    source_chunk = chunks_by_key.get(str(evidence_chunk_key or ""))
                    if source_chunk is None:
                        source_chunk = next((chunk for chunk in chunks if evidence_quote in str(chunk.get("content") or "")), None)
                        if source_chunk is not None:
                            evidence_chunk_key = source_chunk.get("chunk_key")
                    source_chunk_id, source_revision_id = chunk_map.get(str(evidence_chunk_key or ""), (None, None))
                    char_start, char_end, alignment_status = _align_evidence(evidence_quote)
                    cur.execute(
                        """
                        INSERT INTO kb_section_summary_evidence(
                          id, kb_id, file_node_id, parse_generation, summary_id, section_id,
                          chunk_id, revision_id, evidence_quote, evidence_role,
                          char_start, char_end, page_no, block_ids, bbox_json,
                          alignment_status, metadata_json
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            new_id(),
                            kb_id,
                            file_node_id,
                            parse_generation,
                            summary_id,
                            summary.get("section_id"),
                            source_chunk_id,
                            source_revision_id,
                            evidence_quote,
                            evidence_role,
                            char_start,
                            char_end,
                            source_chunk.get("page_start") if source_chunk else None,
                            _j((source_chunk.get("block_ids") or []) if source_chunk else []),
                            _j((source_chunk.get("bbox") or []) if source_chunk else []),
                            alignment_status,
                            _j(metadata),
                        ),
                    )
                    section_summary_evidence_count += 1

            field_map: dict[str, int] = {}
            for index, field in enumerate(fields, 1):
                field_id = new_id()
                field_key = field.get("field_key") or f"field_{index}"
                field_map[field_key] = field_id
                source_chunk_id, source_revision_id = chunk_map.get(field.get("source_chunk_key") or "", (None, None))
                cur.execute(
                    """
                    INSERT INTO file_structured_field(id, kb_id, file_node_id, parse_generation, field_key, field_code, field_name_cn, value_text, aliases_json, normalized_json, source_chunk_id, source_revision_id, source_section_type, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (field_id, kb_id, file_node_id, parse_generation, field_key, field["field_code"], field["field_name_cn"], field.get("value_text"), _j(field.get("aliases")), _j(field.get("normalized_json")), source_chunk_id, source_revision_id, field.get("source_section_type"), _j(field.get("metadata"))),
                )
                if source_chunk_id:
                    mention = field.get("mention") or {}
                    char_start, char_end, alignment_status = _align_evidence(mention.get("evidence_text") or field.get("value_text"))
                    cur.execute(
                        """
                        INSERT INTO file_field_mentions(id, kb_id, file_node_id, parse_generation, field_id, chunk_id, revision_id, evidence_text, char_start, char_end, alignment_status, page_no, block_ids, bbox_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (new_id(), kb_id, file_node_id, parse_generation, field_id, source_chunk_id, source_revision_id, mention.get("evidence_text"), char_start, char_end, alignment_status, mention.get("page_no"), _j(mention.get("block_ids")), _j(mention.get("bbox"))),
                    )

            knowledge_candidate_count = 0
            pending_knowledge_candidate_count = 0
            candidate_review_by_target: dict[tuple[str, str], str] = {}
            pending_candidate_target_ids: set[str] = set()

            def _insert_candidate(candidate_type: str, payload_row: dict[str, Any], target_id: str | None, source_chunk_key: str | None, merge_key: str) -> None:
                nonlocal knowledge_candidate_count, pending_knowledge_candidate_count
                source_chunk_id, _source_revision_id = chunk_map.get(source_chunk_key or "", (None, None))
                confidence = payload_row.get("confidence")
                try:
                    confidence_value = float(confidence or 0)
                except Exception:
                    confidence_value = 0.0
                review_status = "pending_review" if confidence is not None and confidence_value < candidate_auto_accept_confidence else "auto_accepted"
                if target_id:
                    candidate_review_by_target[(candidate_type, str(target_id))] = review_status
                    if review_status == "pending_review":
                        pending_candidate_target_ids.add(str(target_id))
                candidate_id = f"cand_{candidate_type}_{hashlib.sha1((target_id or json.dumps(payload_row, ensure_ascii=False, sort_keys=True)).encode('utf-8')).hexdigest()[:18]}"
                cur.execute(
                    """
                    INSERT INTO kb_knowledge_candidate_pool(
                      id, kb_id, file_node_id, parse_generation, candidate_id, candidate_type,
                      normalized_target_id, candidate_status, merge_group_key, review_status,
                      confidence, source_section_id, source_chunk_id, evidence_quote,
                      raw_payload_json, decision_payload_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'validated', %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      normalized_target_id=VALUES(normalized_target_id),
                      candidate_status=VALUES(candidate_status),
                      merge_group_key=VALUES(merge_group_key),
                      review_status=VALUES(review_status),
                      confidence=VALUES(confidence),
                      source_section_id=VALUES(source_section_id),
                      source_chunk_id=VALUES(source_chunk_id),
                      evidence_quote=VALUES(evidence_quote),
                      raw_payload_json=VALUES(raw_payload_json),
                      decision_payload_json=VALUES(decision_payload_json),
                      update_time=CURRENT_TIMESTAMP
                    """,
                    (
                        new_id(),
                        kb_id,
                        file_node_id,
                        parse_generation,
                        candidate_id,
                        candidate_type,
                        target_id,
                        merge_key,
                        review_status,
                        confidence,
                        payload_row.get("source_section_id"),
                        source_chunk_id,
                        payload_row.get("evidence_quote"),
                        _j(payload_row),
                        _j({"decision": "store_formal" if review_status == "auto_accepted" else "pending_review"}),
                    ),
                )
                knowledge_candidate_count += 1
                if review_status == "pending_review":
                    pending_knowledge_candidate_count += 1

            for anchor in anchors:
                _insert_candidate("anchor", anchor, anchor.get("anchor_id"), anchor.get("source_chunk_key"), clean_identifier(anchor.get("normalized_name") or anchor.get("anchor_name")) or "")
            for unit in knowledge_units:
                _insert_candidate("unit", unit, unit.get("unit_id"), unit.get("primary_chunk_key"), clean_identifier(f"{unit.get('unit_type')} {unit.get('subject_text')} {unit.get('predicate_text')} {unit.get('object_text')}") or "")
            for relation in knowledge_relations:
                _insert_candidate("relation", relation, relation.get("relation_id"), relation.get("source_chunk_key"), clean_identifier(f"{relation.get('relation_type')} {relation.get('from_id')} {relation.get('to_id')}") or "")

            anchor_merge_candidate_count = 0
            for candidate in extract_anchor_merge_candidates(
                anchors,
                kb_id=kb_id,
                file_node_id=file_node_id,
                parse_generation=parse_generation,
            ):
                cur.execute(
                    """
                    INSERT INTO knowledge_anchor_merge_candidate(
                      id, kb_id, file_node_id, parse_generation,
                      left_anchor_id, right_anchor_id, left_anchor_name, right_anchor_name,
                      left_anchor_type, right_anchor_type, similarity_score, similarity_reason,
                      decision, status, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      left_anchor_name=VALUES(left_anchor_name),
                      right_anchor_name=VALUES(right_anchor_name),
                      left_anchor_type=VALUES(left_anchor_type),
                      right_anchor_type=VALUES(right_anchor_type),
                      similarity_score=VALUES(similarity_score),
                      similarity_reason=VALUES(similarity_reason),
                      decision=VALUES(decision),
                      status=VALUES(status),
                      metadata_json=VALUES(metadata_json)
                    """,
                    (
                        new_id(),
                        candidate["kb_id"],
                        candidate["file_node_id"],
                        candidate["parse_generation"],
                        candidate["left_anchor_id"],
                        candidate["right_anchor_id"],
                        candidate.get("left_anchor_name"),
                        candidate.get("right_anchor_name"),
                        candidate.get("left_anchor_type"),
                        candidate.get("right_anchor_type"),
                        candidate.get("similarity_score"),
                        candidate.get("similarity_reason"),
                        candidate.get("decision") or "pending_review",
                        candidate.get("status") or "pending",
                        _j(candidate.get("metadata") or {}),
                    ),
                )
                anchor_merge_candidate_count += 1

            anchor_count = 0
            for anchor in anchors:
                if candidate_review_by_target.get(("anchor", str(anchor.get("anchor_id")))) == "pending_review":
                    continue
                source_chunk_id, _source_revision_id = chunk_map.get(anchor.get("source_chunk_key") or "", (None, None))
                cur.execute(
                    """
                    INSERT INTO kb_anchor_registry(
                      id, kb_id, file_node_id, parse_generation, anchor_id, anchor_type,
                      anchor_name, normalized_name, aliases_json, source_section_id,
                      source_chunk_id, evidence_quote, confidence, status, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      anchor_type=VALUES(anchor_type),
                      anchor_name=VALUES(anchor_name),
                      normalized_name=VALUES(normalized_name),
                      aliases_json=VALUES(aliases_json),
                      source_section_id=VALUES(source_section_id),
                      source_chunk_id=VALUES(source_chunk_id),
                      evidence_quote=VALUES(evidence_quote),
                      confidence=VALUES(confidence),
                      status=VALUES(status),
                      metadata_json=VALUES(metadata_json)
                    """,
                    (
                        new_id(),
                        kb_id,
                        file_node_id,
                        parse_generation,
                        anchor.get("anchor_id"),
                        anchor.get("anchor_type") or "other",
                        anchor.get("anchor_name"),
                        anchor.get("normalized_name"),
                        _j(anchor.get("aliases") or []),
                        anchor.get("source_section_id"),
                        source_chunk_id,
                        anchor.get("evidence_quote"),
                        anchor.get("confidence"),
                        anchor.get("status") or "active",
                        _j(anchor.get("metadata") or {}),
                    ),
                )
                anchor_count += 1

            knowledge_unit_count = 0
            for unit in knowledge_units:
                if candidate_review_by_target.get(("unit", str(unit.get("unit_id")))) == "pending_review":
                    continue
                source_chunk_id, source_revision_id = chunk_map.get(unit.get("primary_chunk_key") or "", (None, None))
                cur.execute(
                    """
                    INSERT INTO kb_knowledge_unit(
                      id, kb_id, file_node_id, parse_generation, unit_id, unit_type,
                      unit_subtype, anchor_id, subject_text, predicate_text, object_text,
                      value_type, normalized_json, source_section_id, primary_chunk_id,
                      evidence_quote, confidence, status, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      unit_type=VALUES(unit_type),
                      unit_subtype=VALUES(unit_subtype),
                      anchor_id=VALUES(anchor_id),
                      subject_text=VALUES(subject_text),
                      predicate_text=VALUES(predicate_text),
                      object_text=VALUES(object_text),
                      value_type=VALUES(value_type),
                      normalized_json=VALUES(normalized_json),
                      source_section_id=VALUES(source_section_id),
                      primary_chunk_id=VALUES(primary_chunk_id),
                      evidence_quote=VALUES(evidence_quote),
                      confidence=VALUES(confidence),
                      status=VALUES(status),
                      metadata_json=VALUES(metadata_json)
                    """,
                    (
                        new_id(),
                        kb_id,
                        file_node_id,
                        parse_generation,
                        unit.get("unit_id"),
                        unit.get("unit_type") or "other",
                        unit.get("unit_subtype"),
                        unit.get("anchor_id"),
                        unit.get("subject_text"),
                        unit.get("predicate_text"),
                        unit.get("object_text"),
                        unit.get("value_type") or "text",
                        _j(unit.get("normalized_json") or {}),
                        unit.get("source_section_id"),
                        source_chunk_id,
                        unit.get("evidence_quote"),
                        unit.get("confidence"),
                        unit.get("status") or "active",
                        _j(unit.get("metadata") or {}),
                    ),
                )
                if source_chunk_id:
                    char_start, char_end, alignment_status = _align_evidence(unit.get("evidence_quote"))
                    source_chunk = next((chunk for chunk in chunks if chunk.get("chunk_key") == unit.get("primary_chunk_key")), {})
                    cur.execute(
                        """
                        INSERT INTO kb_knowledge_unit_evidence(
                          id, kb_id, file_node_id, parse_generation, unit_id, chunk_id, revision_id,
                          evidence_quote, char_start, char_end, page_no, block_ids, bbox_json, alignment_status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            new_id(),
                            kb_id,
                            file_node_id,
                            parse_generation,
                            unit.get("unit_id"),
                            source_chunk_id,
                            source_revision_id,
                            unit.get("evidence_quote"),
                            char_start,
                            char_end,
                            source_chunk.get("page_start"),
                            _j(source_chunk.get("block_ids") or []),
                            _j(source_chunk.get("bbox") or []),
                            alignment_status,
                        ),
                    )
                knowledge_unit_count += 1

            knowledge_relation_count = 0
            for relation in knowledge_relations:
                if candidate_review_by_target.get(("relation", str(relation.get("relation_id")))) == "pending_review":
                    continue
                if str(relation.get("from_id")) in pending_candidate_target_ids or str(relation.get("to_id")) in pending_candidate_target_ids:
                    continue
                source_chunk_id, _source_revision_id = chunk_map.get(relation.get("source_chunk_key") or "", (None, None))
                cur.execute(
                    """
                    INSERT INTO kb_relation(
                      id, kb_id, file_node_id, parse_generation, relation_id, relation_type,
                      from_type, from_id, to_type, to_id, source_chunk_id, evidence_quote,
                      confidence, status, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      relation_type=VALUES(relation_type),
                      from_type=VALUES(from_type),
                      from_id=VALUES(from_id),
                      to_type=VALUES(to_type),
                      to_id=VALUES(to_id),
                      source_chunk_id=VALUES(source_chunk_id),
                      evidence_quote=VALUES(evidence_quote),
                      confidence=VALUES(confidence),
                      status=VALUES(status),
                      metadata_json=VALUES(metadata_json)
                    """,
                    (
                        new_id(),
                        kb_id,
                        file_node_id,
                        parse_generation,
                        relation.get("relation_id"),
                        relation.get("relation_type") or "related_to",
                        relation.get("from_type") or "unknown",
                        relation.get("from_id"),
                        relation.get("to_type") or "unknown",
                        relation.get("to_id"),
                        source_chunk_id,
                        relation.get("evidence_quote"),
                        relation.get("confidence"),
                        relation.get("status") or "active",
                        _j(relation.get("metadata") or {}),
                    ),
                )
                knowledge_relation_count += 1

            prebuilt_qa_count = 0
            if qa_pairs:
                cur.execute(
                    """
                    UPDATE kb_qa_pair
                    SET del_flag=1, index_sync_status='none', update_time=CURRENT_TIMESTAMP
                    WHERE kb_id=%s
                      AND file_node_id=%s
                      AND generation_source='auto_pregenerated'
                      AND manual_override=0
                      AND del_flag=0
                    """,
                    (kb_id, file_node_id),
                )
            seen_auto_questions: set[str] = set()
            for qa in qa_pairs:
                question = str(qa.get("question") or "").strip()
                answer = str(qa.get("answer") or "").strip()
                if not question or not answer:
                    continue
                question_hash = hashlib.sha1(question.lower().encode("utf-8")).hexdigest()
                if question_hash in seen_auto_questions:
                    continue
                seen_auto_questions.add(question_hash)
                source_chunk_keys = [str(item) for item in (qa.get("source_chunk_keys") or []) if str(item).strip()]
                source_chunk_ids = [
                    chunk_map[key][0]
                    for key in source_chunk_keys
                    if key in chunk_map
                ]
                evidence_quotes = [str(item).strip() for item in (qa.get("evidence_quotes") or []) if str(item).strip()]
                if not source_chunk_ids or not evidence_quotes:
                    continue
                try:
                    confidence = float(qa.get("confidence")) if qa.get("confidence") is not None else None
                except (TypeError, ValueError):
                    confidence = None
                metadata = qa.get("metadata") if isinstance(qa.get("metadata"), dict) else {}
                metadata = {
                    **metadata,
                    "parse_generation": parse_generation,
                    "source_chunk_keys": source_chunk_keys,
                    "source": "parse_answer_prebuild",
                }
                cur.execute(
                    """
                    INSERT INTO kb_qa_pair(
                      id, kb_id, file_node_id, question, answer, audit_status, index_sync_status,
                      extended_questions, answer_type, generation_source, source_type,
                      source_chunk_ids_json, source_field_ids_json, evidence_quotes_json,
                      confidence, priority, manual_override, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'none', %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
                    """,
                    (
                        new_id(),
                        kb_id,
                        file_node_id,
                        question,
                        answer,
                        audit_status,
                        _j(qa.get("extended_questions") or []),
                        qa.get("answer_type") or "auto_qa",
                        qa.get("generation_source") or "auto_pregenerated",
                        qa.get("source_type") or "parse_answer_prebuild",
                        _j(source_chunk_ids),
                        _j(qa.get("source_field_ids") or []),
                        _j(evidence_quotes),
                        confidence,
                        int(qa.get("priority") or 0),
                        _j(metadata),
                    ),
                )
                prebuilt_qa_count += 1

            relation_type_counts: dict[str, int] = {}

            def _insert_chunk_relation(from_chunk: dict[str, Any], to_chunk: dict[str, Any], relation_type: str, weight: float, properties: dict[str, Any]) -> None:
                if validate_relation_payload(from_chunk, to_chunk, relation_type, weight, properties):
                    return
                if "confidence" not in properties:
                    properties = {**properties, "confidence": "INFERRED"}
                cur.execute(
                    """
                    INSERT INTO file_chunk_relations(id, kb_id, file_node_id, parse_generation, from_chunk_id, to_chunk_id, relation_type, weight, properties_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE weight=VALUES(weight), properties_json=VALUES(properties_json)
                    """,
                    (new_id(), kb_id, file_node_id, parse_generation, from_chunk["id"], to_chunk["id"], relation_type, weight, _j(properties)),
                )
                relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1

            def _metadata(chunk: dict[str, Any]) -> dict[str, Any]:
                metadata = chunk.get("metadata") or {}
                return metadata if isinstance(metadata, dict) else {}

            def _title_parent(chunk: dict[str, Any]) -> str | None:
                title_path = chunk.get("title_path") or []
                if isinstance(title_path, str):
                    try:
                        title_path = json.loads(title_path)
                    except Exception:
                        title_path = [title_path]
                if isinstance(title_path, list) and len(title_path) >= 2:
                    return str(title_path[-2])
                return None

            def _int_metadata_value(metadata: dict[str, Any], key: str) -> int | None:
                try:
                    value = metadata.get(key)
                    return int(value) if value not in (None, "") else None
                except (TypeError, ValueError):
                    return None

            chunk_rows_by_key = {
                str(chunk.get("chunk_key")): {**chunk, "id": chunk_map[str(chunk.get("chunk_key"))][0]}
                for chunk in chunks
                if chunk.get("chunk_key") and str(chunk.get("chunk_key")) in chunk_map
            }
            for context_chunk in chunks:
                if context_chunk.get("chunk_type") not in {"section_chunk", "parent_chunk"}:
                    continue
                context_row = chunk_rows_by_key.get(str(context_chunk.get("chunk_key")))
                if not context_row:
                    continue
                context_meta = _metadata(context_chunk)
                relation_type = "section_context" if context_chunk.get("chunk_type") == "section_chunk" else "parent_context"
                weight = 0.92 if relation_type == "section_context" else 0.74
                for child_key in context_meta.get("child_chunk_keys") or []:
                    child_row = chunk_rows_by_key.get(str(child_key))
                    if child_row:
                        _insert_chunk_relation(
                            child_row,
                            context_row,
                            relation_type,
                            weight,
                            {
                                "context_level": context_meta.get("context_level"),
                                "context_chunk_key": context_chunk.get("chunk_key"),
                                "confidence": "GENERATED",
                            },
                        )

            for idx, chunk in enumerate(chunk_rows_for_relations):
                if idx > 0:
                    prev = chunk_rows_for_relations[idx - 1]
                    prev_meta = _metadata(prev)
                    chunk_meta_for_adjacent = _metadata(chunk)
                    _insert_chunk_relation(
                        prev,
                        chunk,
                        "adjacent_next",
                        1.0,
                        {"from_seq_no": prev.get("seq_no"), "to_seq_no": chunk.get("seq_no")},
                    )
                    prev_clause_order = _int_metadata_value(prev_meta, "clause_order")
                    chunk_clause_order = _int_metadata_value(chunk_meta_for_adjacent, "clause_order")
                    if prev_clause_order is not None and chunk_clause_order is not None:
                        if prev_clause_order + 1 == chunk_clause_order:
                            _insert_chunk_relation(
                                prev,
                                chunk,
                                "adjacent_clause",
                                0.82,
                                {
                                    "from_clause_id": prev_meta.get("clause_id"),
                                    "to_clause_id": chunk_meta_for_adjacent.get("clause_id"),
                                    "confidence": "EXTRACTED",
                                },
                            )
                for other in chunk_rows_for_relations[:idx]:
                    if other.get("section_type") and other.get("section_type") == chunk.get("section_type") and chunk.get("section_type") != "other":
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_section_type",
                            0.6,
                            {"section_type": chunk.get("section_type")},
                        )
                    if other.get("chunk_group_id") and other.get("chunk_group_id") == chunk.get("chunk_group_id"):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_group",
                            0.85,
                            {"chunk_group_id": chunk.get("chunk_group_id")},
                        )
                    other_meta = _metadata(other)
                    chunk_meta = _metadata(chunk)
                    other_business_block = other_meta.get("business_block_id")
                    chunk_business_block = chunk_meta.get("business_block_id")
                    if other_business_block and other_business_block == chunk_business_block:
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_business_block",
                            0.78,
                            {
                                "business_block_id": chunk_business_block,
                                "business_block_title": chunk_meta.get("business_block_title") or other_meta.get("business_block_title"),
                                "confidence": "EXTRACTED",
                            },
                        )
                    if other_meta.get("clause_id") and other_meta.get("clause_id") == chunk_meta.get("clause_id"):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_clause",
                            0.9,
                            {"clause_id": chunk_meta.get("clause_id")},
                        )
                    if other_meta.get("clause_id") and other_meta.get("clause_id") == chunk_meta.get("parent_clause_id"):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "parent_clause",
                            0.95,
                            {"parent_clause_id": other_meta.get("clause_id"), "child_item_id": chunk_meta.get("item_id"), "confidence": "EXTRACTED"},
                        )
                    if chunk_meta.get("clause_id") and chunk_meta.get("clause_id") == other_meta.get("parent_clause_id"):
                        _insert_chunk_relation(
                            chunk,
                            other,
                            "parent_clause",
                            0.95,
                            {"parent_clause_id": chunk_meta.get("clause_id"), "child_item_id": other_meta.get("item_id"), "confidence": "EXTRACTED"},
                        )
                    if other_meta.get("chapter_id") and other_meta.get("chapter_id") == chunk_meta.get("chapter_id"):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_chapter",
                            0.7,
                            {"chapter_id": chunk_meta.get("chapter_id"), "confidence": "EXTRACTED"},
                        )
                    if other_meta.get("table_key") and other_meta.get("table_key") == chunk_meta.get("table_key"):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_table",
                            0.8,
                            {"table_key": chunk_meta.get("table_key")},
                        )
                    if _title_parent(other) and _title_parent(other) == _title_parent(chunk):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_title_parent",
                            0.65,
                            {"title_parent": _title_parent(chunk)},
                        )
                    other_module_key = other_meta.get("module_key") or other_meta.get("module")
                    chunk_module_key = chunk_meta.get("module_key") or chunk_meta.get("module")
                    if other_module_key and other_module_key == chunk_module_key:
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_module",
                            0.72,
                            {"module": chunk_meta.get("module"), "module_key": chunk_module_key, "confidence": "INFERRED"},
                        )
                    other_api_key = other_meta.get("api_key") or other_meta.get("api_group_id")
                    chunk_api_key = chunk_meta.get("api_key") or chunk_meta.get("api_group_id")
                    if other_api_key and other_api_key == chunk_api_key:
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_api",
                            0.9,
                            {"api_group_id": chunk_meta.get("api_group_id"), "api_key": chunk_api_key, "confidence": "EXTRACTED"},
                        )
                    api_pair = {str(other.get("section_type") or ""), str(chunk.get("section_type") or "")}
                    same_api_identity = bool(other_api_key and chunk_api_key and other_api_key == chunk_api_key)
                    if same_api_identity and {"api_spec", "api_param"}.issubset(api_pair):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "api_param",
                            0.86,
                            {"api_group_id": chunk_meta.get("api_group_id") or other_meta.get("api_group_id"), "confidence": "EXTRACTED"},
                        )
                    if same_api_identity and {"api_spec", "api_example"}.issubset(api_pair):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "api_example",
                            0.8,
                            {"api_group_id": chunk_meta.get("api_group_id") or other_meta.get("api_group_id"), "confidence": "EXTRACTED"},
                        )
                    if same_api_identity and {"api_spec", "api_error_code"}.issubset(api_pair):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "api_error_code",
                            0.84,
                            {"api_group_id": chunk_meta.get("api_group_id") or other_meta.get("api_group_id"), "confidence": "EXTRACTED"},
                        )
                    other_table_key = other_meta.get("table_key") or other_meta.get("table_name")
                    chunk_table_key = chunk_meta.get("table_key") or chunk_meta.get("table_name")
                    if other_table_key and other_table_key == chunk_table_key:
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "db_schema_related",
                            0.88,
                            {"table_name": chunk_meta.get("table_name"), "table_key": chunk_table_key, "confidence": "EXTRACTED"},
                        )
                    if other.get("section_type") == "config_item" and chunk.get("section_type") == "config_item" and other_meta.get("module") == chunk_meta.get("module"):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "config_related",
                            0.78,
                            {"module": chunk_meta.get("module"), "confidence": "INFERRED"},
                        )
                    section_pair = {str(other.get("section_type") or ""), str(chunk.get("section_type") or "")}
                    if {"payment_term", "breach_clause"}.issubset(section_pair):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "payment_breach_related",
                            0.75,
                            {"section_types": sorted(section_pair), "confidence": "INFERRED"},
                        )
                    if "breach_clause" in section_pair and section_pair.intersection({"term_effective", "delivery_acceptance", "payment_term"}):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "term_breach_related",
                            0.72,
                            {"section_types": sorted(section_pair), "confidence": "INFERRED"},
                        )
                    other_obligation_key = other_meta.get("obligation_subject_key") or other_meta.get("obligation_subject")
                    chunk_obligation_key = chunk_meta.get("obligation_subject_key") or chunk_meta.get("obligation_subject")
                    if other_obligation_key and other_obligation_key == chunk_obligation_key:
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "related_obligation",
                            0.74,
                            {"obligation_subject": chunk_meta.get("obligation_subject"), "obligation_subject_key": chunk_obligation_key, "confidence": "INFERRED"},
                        )
                    other_parties = set((other_meta.get("contract_party_keys") or {}).values()) or set(other_meta.get("contract_parties") or [])
                    chunk_parties = set((chunk_meta.get("contract_party_keys") or {}).values()) or set(chunk_meta.get("contract_parties") or [])
                    if other_parties and chunk_parties and other_parties.intersection(chunk_parties):
                        _insert_chunk_relation(
                            other,
                            chunk,
                            "same_party",
                            0.68,
                            {"contract_parties": sorted(other_parties.intersection(chunk_parties)), "confidence": "INFERRED"},
                        )

            for node in graph_nodes:
                cur.execute(
                    """
                    INSERT INTO file_graph_nodes(id, kb_id, file_node_id, parse_generation, node_key, node_type, name_cn, value_text, source_field_id, source_chunk_id, properties_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (new_id(), kb_id, file_node_id, parse_generation, node["node_key"], node["node_type"], node.get("name_cn"), node.get("value_text"), field_map.get(node.get("source_field_key") or ""), chunk_map.get(node.get("source_chunk_key") or "", (None, None))[0], _j(node.get("properties"))),
                )
            for edge in graph_edges:
                cur.execute(
                    """
                    INSERT INTO file_graph_edges(id, kb_id, file_node_id, parse_generation, edge_type, from_node_key, to_node_key, source_field_id, source_chunk_id, properties_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (new_id(), kb_id, file_node_id, parse_generation, edge["edge_type"], edge["from_node_key"], edge["to_node_key"], field_map.get(edge.get("source_field_key") or ""), chunk_map.get(edge.get("source_chunk_key") or "", (None, None))[0], _j(edge.get("properties"))),
                )
            for artifact in artifacts:
                cur.execute(
                    "INSERT INTO file_parse_artifacts(id, kb_id, file_node_id, parse_generation, artifact_type, artifact_path, payload_json) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (new_id(), kb_id, file_node_id, parse_generation, artifact["artifact_type"], artifact.get("artifact_path"), _j(artifact.get("payload"))),
                )
            for index, table in enumerate(tables, 1):
                table_key = table.get("table_key") or table.get("table_id") or f"table_{index:03d}"
                table_id = new_id()
                cur.execute(
                    """
                    INSERT INTO file_tables(id, kb_id, file_node_id, parse_generation, table_key, page_no, title, markdown, bbox_json, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE page_no=VALUES(page_no), title=VALUES(title), markdown=VALUES(markdown), bbox_json=VALUES(bbox_json), metadata_json=VALUES(metadata_json)
                    """,
                    (
                        table_id,
                        kb_id,
                        file_node_id,
                        parse_generation,
                        table_key,
                        table.get("page_no"),
                        table.get("title"),
                        table.get("markdown") or table.get("text"),
                        _j(table.get("bbox")),
                        _j(table.get("metadata") or {key: value for key, value in table.items() if key not in {"rows", "columns"}}),
                    ),
                )
                columns = table.get("columns") or []
                for column_index, column in enumerate(columns, 1):
                    name = column.get("name") if isinstance(column, dict) else str(column)
                    cur.execute(
                        "INSERT INTO file_table_columns(id, table_id, column_index, column_name, normalized_name, data_type) VALUES (%s, %s, %s, %s, %s, %s)",
                        (new_id(), table_id, column_index, name, clean_identifier(name), column.get("data_type") if isinstance(column, dict) else None),
                    )
                for row_index, row in enumerate(table.get("rows") or [], 1):
                    cur.execute(
                        "INSERT INTO file_table_rows(id, table_id, row_index, row_json) VALUES (%s, %s, %s, %s)",
                        (new_id(), table_id, row_index, _j(row)),
                    )
            text_version = char_map_payload.get("text_version") or "norm_v1"
            for span in char_spans:
                cur.execute(
                    """
                    INSERT INTO file_char_map(id, kb_id, file_node_id, parse_generation, span_id, text_version, global_char_start, global_char_end, page_no, block_id, line_no, bbox_json, positions_json, source_type, block_type, text)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        new_id(),
                        kb_id,
                        file_node_id,
                        parse_generation,
                        span.get("span_id"),
                        text_version,
                        span.get("global_char_start") or 0,
                        span.get("global_char_end") or 0,
                        span.get("page_no"),
                        span.get("block_id"),
                        span.get("line_no"),
                        _j(span.get("bbox")),
                        _j(span.get("positions")),
                        span.get("source_type"),
                        span.get("block_type"),
                        span.get("text"),
                    ),
                )

            cur.execute(
                """
                INSERT INTO file_index_pointer(id, kb_id, file_node_id, current_parse_generation, current_index_generation, status)
                VALUES (%s, %s, %s, %s, NULL, 'parsed')
                ON DUPLICATE KEY UPDATE current_parse_generation=VALUES(current_parse_generation), current_index_generation=NULL, status='parsed', update_time=CURRENT_TIMESTAMP
                """,
                (new_id(), kb_id, file_node_id, parse_generation),
            )
            result_path = parse_result_url or next((item.get("artifact_path") for item in artifacts if item["artifact_type"] == "middle_document"), None)
            cur.execute("UPDATE kb_file_node SET parse_status='parsed', index_status='none', current_parse_generation=%s, current_index_generation=NULL, parse_result_ref=%s WHERE id=%s", (parse_generation, result_path, file_node_id))
            cur.execute("UPDATE kb_file_task SET stage='done', status='success', parse_result_url=%s, parse_generation=%s, index_sync_status='none', index_generation=NULL WHERE file_node_id=%s", (result_path, parse_generation, file_node_id))
        conn.commit()
    return {
        "chunk_count": len(chunks),
        "section_count": len(sections),
        "section_summary_count": len(section_summaries),
        "section_summary_evidence_count": section_summary_evidence_count if "section_summary_evidence_count" in locals() else 0,
        "field_count": len(fields),
        "anchor_count": anchor_count if "anchor_count" in locals() else 0,
        "knowledge_unit_count": knowledge_unit_count if "knowledge_unit_count" in locals() else 0,
        "knowledge_relation_count": knowledge_relation_count if "knowledge_relation_count" in locals() else 0,
        "knowledge_candidate_count": knowledge_candidate_count if "knowledge_candidate_count" in locals() else 0,
        "pending_knowledge_candidate_count": pending_knowledge_candidate_count if "pending_knowledge_candidate_count" in locals() else 0,
        "anchor_merge_candidate_count": anchor_merge_candidate_count if "anchor_merge_candidate_count" in locals() else 0,
        "prebuilt_qa_count": prebuilt_qa_count if "prebuilt_qa_count" in locals() else 0,
        "graph_node_count": len(graph_nodes),
        "graph_edge_count": len(graph_edges),
        "relation_count": sum(relation_type_counts.values()) if "relation_type_counts" in locals() else 0,
        "relation_type_counts": relation_type_counts if "relation_type_counts" in locals() else {},
    }


def load_index_snapshot(kb_id: int, file_node_id: int, parse_generation: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM kb_file_node WHERE id = %s AND kb_id = %s AND del_flag = 0", (file_node_id, kb_id))
            file_node = cur.fetchone()
            if not file_node:
                raise RuntimeError(f"file_node not found: kb_id={kb_id}, file_node_id={file_node_id}")
            effective = parse_generation or file_node["current_parse_generation"]
            cur.execute(
                """
                SELECT c.*, r.id AS revision_id, r.title, r.title_path, r.content_for_embedding, r.content_for_bm25
                FROM kb_chunk c
                JOIN kb_chunk_revision r ON r.id = COALESCE(c.published_revision_id, c.latest_revision_id)
                WHERE c.kb_id=%s AND c.file_node_id=%s AND c.parse_generation=%s AND c.del_flag=0 AND c.enabled=1 AND c.audit_status='approved'
                ORDER BY c.seq_no
                """,
                (kb_id, file_node_id, effective),
            )
            chunks = cur.fetchall()
            cur.execute("SELECT * FROM kb_section WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s ORDER BY seq_start, id", (kb_id, file_node_id, effective))
            sections = cur.fetchall()
            cur.execute("SELECT * FROM kb_section_summary WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s ORDER BY id", (kb_id, file_node_id, effective))
            section_summaries = cur.fetchall()
            cur.execute("SELECT * FROM kb_section_summary_evidence WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s ORDER BY id", (kb_id, file_node_id, effective))
            section_summary_evidence = cur.fetchall()
            cur.execute("SELECT * FROM file_structured_field WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s AND del_flag=0 ORDER BY id", (kb_id, file_node_id, effective))
            fields = cur.fetchall()
            cur.execute("SELECT * FROM file_field_mentions WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s ORDER BY id", (kb_id, file_node_id, effective))
            mentions = cur.fetchall()
            cur.execute("SELECT * FROM file_graph_nodes WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s ORDER BY id", (kb_id, file_node_id, effective))
            graph_nodes = cur.fetchall()
            cur.execute("SELECT * FROM file_graph_edges WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s ORDER BY id", (kb_id, file_node_id, effective))
            graph_edges = cur.fetchall()
            cur.execute(
                """
                SELECT * FROM kb_qa_pair
                WHERE kb_id=%s AND audit_status='approved' AND del_flag=0
                  AND (file_node_id IS NULL OR file_node_id=%s)
                ORDER BY id
                """,
                (kb_id, file_node_id),
            )
            qa_rows = cur.fetchall()
            cur.execute("SELECT * FROM kb_anchor_registry WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s AND status='active' ORDER BY id", (kb_id, file_node_id, effective))
            anchors = cur.fetchall()
            cur.execute("SELECT * FROM kb_knowledge_unit WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s AND status='active' ORDER BY id", (kb_id, file_node_id, effective))
            knowledge_units = cur.fetchall()
            cur.execute("SELECT * FROM kb_relation WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s AND status='active' ORDER BY id", (kb_id, file_node_id, effective))
            relations = cur.fetchall()
    profile = file_node.get("profile") or "guarantee_plan"
    doc_name = unquote(file_node.get("name") or "") or unquote(file_node.get("original_name") or "") or ""
    for row in chunks:
        row["profile"] = profile
        row["doc_name"] = doc_name
    for row in fields:
        row["profile"] = profile
        row["doc_name"] = doc_name
    for row in sections:
        row["profile"] = profile
        row["doc_name"] = doc_name
    for row in qa_rows:
        row["profile"] = profile
        row["doc_name"] = doc_name
    section_by_id = {row.get("section_id"): row for row in sections}
    chunk_by_id = {row["id"]: row for row in chunks}

    def _json_ids(value: Any) -> set[int]:
        if not value:
            return set()
        try:
            rows = json.loads(value) if isinstance(value, str) else value
            return {int(item) for item in rows or [] if item}
        except Exception:
            return set()

    def _section_path_text(section_row: dict[str, Any] | None) -> str:
        if not section_row:
            return ""
        raw_path = section_row.get("section_path")
        try:
            path = json.loads(raw_path) if isinstance(raw_path, str) else raw_path
        except Exception:
            path = []
        if not isinstance(path, list):
            path = []
        return " > ".join(str(item) for item in path if item)

    active_chunk_ids = {row["id"] for row in chunks}
    fields = [row for row in fields if row.get("source_chunk_id") in active_chunk_ids or row.get("source_chunk_id") is None]
    active_field_ids = {row["id"] for row in fields}
    section_summaries = [
        row
        for row in section_summaries
        if not _json_ids(row.get("covered_chunk_ids_json")) or _json_ids(row.get("covered_chunk_ids_json")) & active_chunk_ids
    ]
    for row in section_summaries:
        section_row = section_by_id.get(row.get("section_id"))
        row["profile"] = profile
        row["doc_name"] = doc_name
        row["section_type"] = section_row.get("section_type") if section_row else None
        row["section_path_text"] = _section_path_text(section_row)
    anchors = [row for row in anchors if row.get("source_chunk_id") in active_chunk_ids or row.get("source_chunk_id") is None]
    for row in anchors:
        section_row = section_by_id.get(row.get("source_section_id"))
        source_chunk = chunk_by_id.get(row.get("source_chunk_id"))
        row["profile"] = profile
        row["doc_name"] = doc_name
        row["source_section_type"] = section_row.get("section_type") if section_row else None
        row["section_path_text"] = _section_path_text(section_row)
        row["primary_chunk_id"] = source_chunk.get("primary_chunk_id") or source_chunk.get("id") if source_chunk else row.get("source_chunk_id")
    knowledge_units = [row for row in knowledge_units if row.get("primary_chunk_id") in active_chunk_ids]
    for row in knowledge_units:
        section_row = section_by_id.get(row.get("source_section_id"))
        row["profile"] = profile
        row["doc_name"] = doc_name
        row["source_section_type"] = section_row.get("section_type") if section_row else None
        row["section_path_text"] = _section_path_text(section_row)
    kept_anchor_ids = {row.get("anchor_id") for row in anchors}
    kept_unit_ids = {row.get("unit_id") for row in knowledge_units}
    relations = [
        row
        for row in relations
        if row.get("source_chunk_id") in active_chunk_ids
        or row.get("from_id") in kept_anchor_ids
        or row.get("to_id") in kept_anchor_ids
        or row.get("from_id") in kept_unit_ids
        or row.get("to_id") in kept_unit_ids
    ]
    mentions = [row for row in mentions if row["field_id"] in active_field_ids and row["chunk_id"] in active_chunk_ids]
    graph_nodes = [row for row in graph_nodes if (row.get("source_chunk_id") in active_chunk_ids or row.get("source_chunk_id") is None)]
    graph_edges = [
        row
        for row in graph_edges
        if (row.get("source_chunk_id") in active_chunk_ids or row.get("source_chunk_id") is None)
        and (row.get("source_field_id") in active_field_ids or row.get("source_field_id") is None)
    ]
    return {
        "file_node": file_node,
        "parse_generation": effective,
        "chunks": chunks,
        "sections": sections,
        "section_summaries": section_summaries,
        "section_summary_evidence": section_summary_evidence,
        "fields": fields,
        "mentions": mentions,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "qa_rows": qa_rows,
        "anchors": anchors,
        "knowledge_units": knowledge_units,
        "relations": relations,
    }


def mark_index_started(kb_id: int, file_node_id: int, parse_generation: str, index_generation: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_index_pointer(id, kb_id, file_node_id, current_parse_generation, current_index_generation, status)
                VALUES (%s, %s, %s, %s, NULL, 'indexing')
                ON DUPLICATE KEY UPDATE current_parse_generation=VALUES(current_parse_generation), status=IF(current_index_generation IS NULL, 'indexing', status), update_time=CURRENT_TIMESTAMP
                """,
                (new_id(), kb_id, file_node_id, parse_generation),
            )
            cur.execute("UPDATE kb_file_node SET index_status='indexing' WHERE id=%s AND kb_id=%s", (file_node_id, kb_id))
            cur.execute("UPDATE kb_file_task SET stage='index', index_sync_status='syncing', index_generation=%s WHERE file_node_id=%s", (index_generation, file_node_id))
            cur.execute(
                """
                INSERT INTO kb_file_task_history(id, kb_id, file_node_id, task_type, stage, status, parse_generation, index_generation)
                VALUES (%s, %s, %s, 'index', 'index', 'running', %s, %s)
                """,
                (new_id(), kb_id, file_node_id, parse_generation, index_generation),
            )
        conn.commit()


def try_acquire_index_lock(kb_id: int, file_node_id: int, index_generation: str, ttl_seconds: int = 1800) -> bool:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieve_index_state(id, kb_id, file_node_id, parse_generation, index_generation, target_type, status, indexed_count, error_msg)
                VALUES (%s, %s, %s, NULL, %s, 'lock', 'running', 0, NULL)
                ON DUPLICATE KEY UPDATE
                  status = IF(update_time < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL %s SECOND), 'running', status),
                  update_time = IF(update_time < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL %s SECOND), CURRENT_TIMESTAMP, update_time)
                """,
                (new_id(), kb_id, file_node_id, index_generation, ttl_seconds, ttl_seconds),
            )
            cur.execute(
                """
                SELECT COUNT(*) AS running_count
                FROM retrieve_index_state
                WHERE kb_id=%s AND file_node_id=%s AND target_type='lock' AND status='running'
                  AND index_generation <> %s
                  AND update_time >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL %s SECOND)
                """,
                (kb_id, file_node_id, index_generation, ttl_seconds),
            )
            running_count = int((cur.fetchone() or {}).get("running_count") or 0)
        conn.commit()
    return running_count == 0


def release_index_lock(kb_id: int, file_node_id: int, index_generation: str, success: bool, error_msg: str | None = None) -> None:
    status = "success" if success else "failed"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE retrieve_index_state
                SET status=%s, error_msg=%s, update_time=CURRENT_TIMESTAMP
                WHERE kb_id=%s AND file_node_id=%s AND index_generation=%s AND target_type='lock'
                """,
                (status, error_msg, kb_id, file_node_id, index_generation),
            )
        conn.commit()


def upsert_index_state(kb_id: int, file_node_id: int, parse_generation: str, index_generation: str, target_type: str, status: str, indexed_count: int, error_msg: str | None = None) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieve_index_state(id, kb_id, file_node_id, parse_generation, index_generation, target_type, status, indexed_count, error_msg)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE status=VALUES(status), indexed_count=VALUES(indexed_count), error_msg=VALUES(error_msg), update_time=CURRENT_TIMESTAMP
                """,
                (new_id(), kb_id, file_node_id, parse_generation, index_generation, target_type, status, indexed_count, error_msg),
            )
        conn.commit()


def mark_index_finished(kb_id: int, file_node_id: int, parse_generation: str, index_generation: str, indexed_chunk_count: int, success: bool, error_msg: str | None = None) -> None:
    index_status = "synced" if success else "failed"
    active_generation = index_generation if success else None
    pointer_status = "active" if success else "failed"
    with connect() as conn:
        with conn.cursor() as cur:
            if success:
                cur.execute("SELECT current_index_generation FROM file_index_pointer WHERE kb_id=%s AND file_node_id=%s", (kb_id, file_node_id))
                previous_generation = (cur.fetchone() or {}).get("current_index_generation")
                cur.execute("UPDATE kb_chunk SET index_sync_status=%s, index_generation=%s WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s AND del_flag=0", (index_status, active_generation, kb_id, file_node_id, parse_generation))
                cur.execute("UPDATE kb_file_node SET index_status=%s, current_index_generation=%s WHERE id=%s AND kb_id=%s", (index_status, active_generation, file_node_id, kb_id))
                cur.execute("UPDATE kb_file_task SET stage='done', index_sync_status=%s, indexed_chunk_count=%s, index_generation=%s, error_msg=%s WHERE file_node_id=%s", (index_status, indexed_chunk_count, active_generation, error_msg, file_node_id))
                cur.execute(
                    """
                    INSERT INTO file_index_pointer(id, kb_id, file_node_id, current_parse_generation, current_index_generation, previous_index_generation, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE current_parse_generation=VALUES(current_parse_generation), current_index_generation=VALUES(current_index_generation), previous_index_generation=VALUES(previous_index_generation), status=VALUES(status), update_time=CURRENT_TIMESTAMP
                    """,
                    (new_id(), kb_id, file_node_id, parse_generation, active_generation, previous_generation, pointer_status),
                )
            else:
                cur.execute("UPDATE kb_file_node SET index_status=%s WHERE id=%s AND kb_id=%s", (index_status, file_node_id, kb_id))
                cur.execute("UPDATE kb_file_task SET stage='done', index_sync_status=%s, indexed_chunk_count=%s, error_msg=%s WHERE file_node_id=%s", (index_status, indexed_chunk_count, error_msg, file_node_id))
                cur.execute(
                    """
                    INSERT INTO file_index_pointer(id, kb_id, file_node_id, current_parse_generation, current_index_generation, status)
                    VALUES (%s, %s, %s, %s, NULL, %s)
                    ON DUPLICATE KEY UPDATE current_parse_generation=VALUES(current_parse_generation), status=IF(current_index_generation IS NULL, VALUES(status), 'active'), update_time=CURRENT_TIMESTAMP
                    """,
                    (new_id(), kb_id, file_node_id, parse_generation, pointer_status),
                )
            cur.execute(
                """
                INSERT INTO kb_file_task_history(id, kb_id, file_node_id, task_type, stage, status, parse_generation, index_generation, error_msg, payload_json)
                VALUES (%s, %s, %s, 'index', 'done', %s, %s, %s, %s, %s)
                """,
                (new_id(), kb_id, file_node_id, index_status, parse_generation, index_generation, error_msg, _j({"indexed_chunk_count": indexed_chunk_count})),
            )
        conn.commit()


def load_section_tree(kb_id: int, file_node_id: int, parse_generation: str | None = None) -> dict[str, Any]:
    """Query kb_section and reconstruct a nested tree for a single file."""
    with connect() as conn:
        with conn.cursor() as cur:
            if not parse_generation:
                cur.execute(
                    "SELECT current_parse_generation FROM kb_file_node WHERE kb_id=%s AND id=%s AND del_flag=0",
                    (kb_id, file_node_id),
                )
                row = cur.fetchone()
                parse_generation = row["current_parse_generation"] if row else None
            if not parse_generation:
                return {"kb_id": kb_id, "file_node_id": file_node_id, "sections": [], "error": "no parse generation found"}
            cur.execute(
                "SELECT * FROM kb_section WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s ORDER BY seq_start, id",
                (kb_id, file_node_id, parse_generation),
            )
            rows = cur.fetchall()

    # Build tree from flat list
    sections_by_id: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in rows:
        sid = str(row.get("section_id") or "")
        node = {
            "section_id": sid,
            "parent_section_id": str(row.get("parent_section_id") or ""),
            "title": row.get("section_title") or "",
            "section_type": row.get("section_type") or "",
            "level": int(row.get("section_level") or 0),
            "page_start": row.get("page_start"),
            "page_end": row.get("page_end"),
            "chunk_count": len(json.loads(str(row.get("covered_chunk_ids_json") or "[]"))),
            "children": [],
        }
        sections_by_id[sid] = node

    for sid, node in sections_by_id.items():
        parent_id = node["parent_section_id"]
        if parent_id and parent_id in sections_by_id:
            sections_by_id[parent_id]["children"].append(node)
        else:
            roots.append(node)

    # Sort children by level + page
    for node in sections_by_id.values():
        node["children"].sort(key=lambda c: (c.get("page_start") or 0, c.get("section_id") or ""))
    roots.sort(key=lambda r: (r.get("page_start") or 0, r.get("section_id") or ""))

    # Clean up empty parent_section_id
    for node in sections_by_id.values():
        if not node["parent_section_id"]:
            del node["parent_section_id"]

    return {
        "kb_id": kb_id,
        "file_node_id": file_node_id,
        "parse_generation": parse_generation,
        "section_count": len(rows),
        "sections": roots,
    }


def load_knowledge_base_profile(kb_id: int) -> str | None:
    """读取知识库创建时保存的 profile（当前落在 kb_knowledge_base.type）。"""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT type FROM kb_knowledge_base WHERE id=%s AND del_flag=0",
                (kb_id,),
            )
            row = cur.fetchone()
    if not row or not row.get("type"):
        return None
    return str(row["type"]).strip() or None


def load_active_index_scope(kb_id: int, file_node_ids: list[int] | None = None) -> dict[str, Any]:
    """解析检索文件范围。

    调用方显式传了 file_node_ids 时，直接以它为准（不强制要求 file_index_pointer
    active 状态）—— 用户明确指定检索哪些文件时应该被尊重。只有在未传文件范围时，
    才回退到 file_index_pointer 中 status='active' 的记录。
    """
    if file_node_ids:
        with connect() as conn:
            with conn.cursor() as cur:
                placeholders = ",".join(["%s"] * len(file_node_ids))
                cur.execute(
                    f"""
                    SELECT file_node_id, current_index_generation
                    FROM file_index_pointer
                    WHERE kb_id=%s AND file_node_id IN ({placeholders})
                      AND status='active' AND current_index_generation IS NOT NULL
                    """,
                    [kb_id, *file_node_ids],
                )
                rows = cur.fetchall()
        active_rows = {int(row["file_node_id"]): row for row in rows}
        # 显式传入的文件，即使 pointer 无 active 记录也纳入范围（生成期取 pointer 值，缺失时用空）
        return {
            "file_node_ids": [int(fid) for fid in file_node_ids],
            "index_generations": [
                active_rows[int(fid)]["current_index_generation"]
                for fid in file_node_ids
                if int(fid) in active_rows and active_rows[int(fid)].get("current_index_generation")
            ],
        }
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_node_id, current_index_generation
                FROM file_index_pointer
                WHERE kb_id=%s AND status='active' AND current_index_generation IS NOT NULL
                """,
                (kb_id,),
            )
            rows = cur.fetchall()
    return {
        "file_node_ids": [row["file_node_id"] for row in rows],
        "index_generations": [row["current_index_generation"] for row in rows if row.get("current_index_generation")],
    }


def load_retrieval_profile_config(kb_id: int, profile: str | None = None) -> dict[str, Any]:
    """Load KB/profile retrieval strategy JSON from MySQL.

    The current schema stores flexible strategy data in kb_knowledge_base.model_profile.
    Supported shapes:
    - {"retrieval_fusion": {...}}
    - {"profiles": {"business_plan": {"retrieval_fusion": {...}}}}
    - {"business_plan": {"retrieval_fusion": {...}}}
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT model_profile FROM kb_knowledge_base WHERE id=%s AND del_flag=0",
                (kb_id,),
            )
            row = cur.fetchone() or {}
    raw = row.get("model_profile")
    if not raw:
        return {}
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    if profile:
        profile_payload = {}
        profiles = payload.get("profiles")
        if isinstance(profiles, dict) and isinstance(profiles.get(profile), dict):
            profile_payload = profiles.get(profile) or {}
        elif isinstance(payload.get(profile), dict):
            profile_payload = payload.get(profile) or {}
        merged = {**payload, **profile_payload}
        merged.pop("profiles", None)
        return merged
    return payload


def load_related_chunks(
    kb_id: int,
    file_node_ids: list[int],
    chunk_ids: list[int],
    index_generations: list[str] | None = None,
    relation_types: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    relation_types = relation_types or ["adjacent_next", "same_section_type"]
    with connect() as conn:
        with conn.cursor() as cur:
            params: list[Any] = [kb_id]
            sql = """
                SELECT DISTINCT
                       c.id AS chunk_id,
                       c.kb_id,
                       c.file_node_id,
                       c.seq_no,
                       c.chunk_type,
                       c.section_type,
                       c.section_id,
                       c.chunk_group_id,
                       c.parse_generation,
                       c.index_generation,
                       c.page_start,
                       c.page_end,
                       c.content,
                       c.summary,
                       r.title,
                       rel.weight AS relation_weight,
                       rel.relation_type,
                       CASE WHEN rel.from_chunk_id IN ({chunk_placeholders}) THEN rel.from_chunk_id ELSE rel.to_chunk_id END AS source_chunk_id
                FROM file_chunk_relations rel
                JOIN kb_chunk c
                  ON c.kb_id=rel.kb_id
                 AND c.file_node_id=rel.file_node_id
                 AND c.parse_generation COLLATE utf8mb4_general_ci = rel.parse_generation COLLATE utf8mb4_general_ci
                 AND c.id = CASE WHEN rel.from_chunk_id IN ({chunk_placeholders}) THEN rel.to_chunk_id ELSE rel.from_chunk_id END
                JOIN kb_chunk_revision r ON r.id = COALESCE(c.published_revision_id, c.latest_revision_id)
                LEFT JOIN file_index_pointer p ON p.kb_id=c.kb_id AND p.file_node_id=c.file_node_id
                WHERE rel.kb_id=%s
                  AND (rel.from_chunk_id IN ({chunk_placeholders}) OR rel.to_chunk_id IN ({chunk_placeholders}))
                  AND c.del_flag=0
                  AND c.enabled=1
                  AND c.audit_status='approved'
            """
            placeholders = ",".join(["%s"] * len(chunk_ids))
            sql = sql.replace("{chunk_placeholders}", placeholders)
            params = [*chunk_ids, *chunk_ids, kb_id, *chunk_ids, *chunk_ids]
            if file_node_ids:
                sql += f" AND c.file_node_id IN ({','.join(['%s'] * len(file_node_ids))})"
                params.extend(file_node_ids)
            if index_generations:
                sql += f" AND p.current_index_generation COLLATE utf8mb4_general_ci IN ({','.join(['%s'] * len(index_generations))})"
                params.extend(index_generations)
            if relation_types:
                sql += f" AND rel.relation_type COLLATE utf8mb4_general_ci IN ({','.join(['%s'] * len(relation_types))})"
                params.extend(relation_types)
            sql += " ORDER BY rel.weight DESC, c.seq_no LIMIT %s"
            params.append(max(0, int(limit)))
            cur.execute(sql, params)
            rows = cur.fetchall()
    return rows


def load_chunks_by_ids(
    kb_id: int,
    file_node_ids: list[int],
    chunk_ids: list[int],
    index_generations: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    unique_chunk_ids = sorted({int(item) for item in chunk_ids if item})
    with connect() as conn:
        with conn.cursor() as cur:
            params: list[Any] = [kb_id, *unique_chunk_ids]
            sql = f"""
                SELECT DISTINCT
                       c.id AS chunk_id,
                       c.kb_id,
                       c.file_node_id,
                       c.seq_no,
                       c.chunk_type,
                       c.section_type,
                       c.section_id,
                       c.chunk_group_id,
                       c.parse_generation,
                       c.index_generation,
                       c.page_start,
                       c.page_end,
                       c.content,
                       c.summary,
                       c.metadata_json,
                       r.title,
                       'graph_context_plan' AS relation_type,
                       c.id AS source_chunk_id
                FROM kb_chunk c
                JOIN kb_chunk_revision r ON r.id = COALESCE(c.published_revision_id, c.latest_revision_id)
                LEFT JOIN file_index_pointer p ON p.kb_id=c.kb_id AND p.file_node_id=c.file_node_id
                WHERE c.kb_id=%s
                  AND c.id IN ({','.join(['%s'] * len(unique_chunk_ids))})
                  AND c.del_flag=0
                  AND c.enabled=1
                  AND c.audit_status='approved'
            """
            if file_node_ids:
                sql += f" AND c.file_node_id IN ({','.join(['%s'] * len(file_node_ids))})"
                params.extend(file_node_ids)
            if index_generations:
                sql += f" AND p.current_index_generation COLLATE utf8mb4_general_ci IN ({','.join(['%s'] * len(index_generations))})"
                params.extend(index_generations)
            sql += " ORDER BY c.file_node_id, c.seq_no LIMIT %s"
            params.append(max(0, min(int(limit), 200)))
            cur.execute(sql, params)
            return cur.fetchall()


def load_section_summaries_by_chunk_ids(
    kb_id: int,
    chunk_ids: list[int],
    file_node_ids: list[int] | None = None,
    index_generations: list[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    unique_chunk_ids = sorted({int(item) for item in chunk_ids if item})
    with connect() as conn:
        with conn.cursor() as cur:
            params: list[Any] = [kb_id, *unique_chunk_ids]
            sql = f"""
                SELECT DISTINCT
                       c.id AS chunk_id,
                       c.kb_id,
                       c.file_node_id,
                       c.section_id,
                       ss.section_title,
                       ss.section_path,
                       ss.section_level,
                       ss.summary_type,
                       ss.node_summary,
                       ss.structured_summary_json,
                       ss.covered_chunk_ids_json,
                       ss.summary_source,
                       ss.confidence
                FROM kb_chunk c
                JOIN kb_section_summary ss
                  ON ss.kb_id=c.kb_id
                 AND ss.file_node_id=c.file_node_id
                 AND ss.parse_generation COLLATE utf8mb4_general_ci = c.parse_generation COLLATE utf8mb4_general_ci
                 AND ss.section_id COLLATE utf8mb4_general_ci = c.section_id COLLATE utf8mb4_general_ci
                LEFT JOIN file_index_pointer p ON p.kb_id=c.kb_id AND p.file_node_id=c.file_node_id
                WHERE c.kb_id=%s
                  AND c.id IN ({','.join(['%s'] * len(unique_chunk_ids))})
                  AND c.del_flag=0
                  AND c.enabled=1
                  AND c.audit_status='approved'
            """
            if file_node_ids:
                sql += f" AND c.file_node_id IN ({','.join(['%s'] * len(file_node_ids))})"
                params.extend(file_node_ids)
            if index_generations:
                sql += f" AND p.current_index_generation COLLATE utf8mb4_general_ci IN ({','.join(['%s'] * len(index_generations))})"
                params.extend(index_generations)
            sql += " ORDER BY ss.section_level DESC, ss.id LIMIT %s"
            params.append(max(0, min(int(limit), 500)))
            cur.execute(sql, params)
            return cur.fetchall()


def filter_snapshot_by_chunk_ids(snapshot: dict[str, Any], chunk_ids: list[int]) -> dict[str, Any]:
    def _json_ids(value: Any) -> set[int]:
        if not value:
            return set()
        try:
            rows = json.loads(value) if isinstance(value, str) else value
            return {int(item) for item in rows or [] if item}
        except Exception:
            return set()

    if not chunk_ids:
        return {
            **snapshot,
            "chunks": [],
            "sections": [],
            "section_summaries": [],
            "fields": [],
            "mentions": [],
            "graph_nodes": [],
            "graph_edges": [],
            "anchors": [],
            "knowledge_units": [],
            "relations": [],
        }
    chunk_ids_set = set(chunk_ids)
    field_ids = {row["id"] for row in snapshot["fields"] if row.get("source_chunk_id") in chunk_ids_set}
    chunks = [row for row in snapshot["chunks"] if row["id"] in chunk_ids_set]
    sections = [
        row
        for row in snapshot.get("sections", [])
        if _json_ids(row.get("covered_chunk_ids_json")) & chunk_ids_set
    ]
    section_ids = {row.get("section_id") for row in sections}
    section_summaries = [
        row
        for row in snapshot.get("section_summaries", [])
        if row.get("section_id") in section_ids
        or _json_ids(row.get("covered_chunk_ids_json")) & chunk_ids_set
    ]
    fields = [row for row in snapshot["fields"] if row["id"] in field_ids]
    mentions = [row for row in snapshot["mentions"] if row["chunk_id"] in chunk_ids_set and row["field_id"] in field_ids]
    graph_nodes = [
        row
        for row in snapshot["graph_nodes"]
        if row.get("source_chunk_id") in chunk_ids_set
        or row.get("source_chunk_id") is None and row.get("source_field_id") in field_ids
    ]
    graph_edges = [
        row
        for row in snapshot["graph_edges"]
        if row.get("source_chunk_id") in chunk_ids_set
        or row.get("source_field_id") in field_ids
    ]
    anchors = [row for row in snapshot.get("anchors", []) if row.get("source_chunk_id") in chunk_ids_set]
    knowledge_units = [row for row in snapshot.get("knowledge_units", []) if row.get("primary_chunk_id") in chunk_ids_set]
    kept_anchor_ids = {row.get("anchor_id") for row in anchors}
    kept_unit_ids = {row.get("unit_id") for row in knowledge_units}
    relations = [
        row
        for row in snapshot.get("relations", [])
        if row.get("source_chunk_id") in chunk_ids_set
        or row.get("from_id") in kept_anchor_ids
        or row.get("to_id") in kept_anchor_ids
        or row.get("from_id") in kept_unit_ids
        or row.get("to_id") in kept_unit_ids
    ]
    return {
        **snapshot,
        "chunks": chunks,
        "sections": sections,
        "section_summaries": section_summaries,
        "fields": fields,
        "mentions": mentions,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "anchors": anchors,
        "knowledge_units": knowledge_units,
        "relations": relations,
    }


def load_chunk_snapshot(kb_id: int, file_node_id: int, chunk_ids: list[int], parse_generation: str | None = None) -> dict[str, Any]:
    snapshot = load_index_snapshot(kb_id, file_node_id, parse_generation)
    return filter_snapshot_by_chunk_ids(snapshot, chunk_ids)


def load_qa_snapshot(kb_id: int, qa_ids: list[int] | None = None, file_node_ids: list[int] | None = None) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT * FROM kb_qa_pair
                WHERE kb_id=%s AND audit_status='approved' AND del_flag=0
            """
            params: list[Any] = [kb_id]
            if file_node_ids:
                sql += f" AND (file_node_id IS NULL OR file_node_id IN ({','.join(['%s'] * len(file_node_ids))}))"
                params.extend(file_node_ids)
            if qa_ids:
                sql += f" AND id IN ({','.join(['%s'] * len(qa_ids))})"
                params.extend(qa_ids)
            sql += " ORDER BY id"
            cur.execute(sql, params)
            qa_rows = cur.fetchall()
    return {"qa_rows": qa_rows}


def save_qa_pairs(
    kb_id: int,
    file_node_id: int | None,
    qa_pairs: list[dict[str, Any]],
    *,
    audit_status: str = "pending",
) -> list[int]:
    if audit_status not in {"pending", "approved"}:
        audit_status = "pending"
    saved_ids: list[int] = []
    with connect() as conn:
        with conn.cursor() as cur:
            for qa in qa_pairs:
                question = str(qa.get("question") or "").strip()
                answer = str(qa.get("answer") or "").strip()
                if not question or not answer:
                    continue
                qa_id = new_id()
                cur.execute(
                    """
                    INSERT INTO kb_qa_pair(
                      id, kb_id, file_node_id, question, answer, audit_status, index_sync_status,
                      extended_questions, answer_type, generation_source, source_type,
                      source_chunk_ids_json, source_field_ids_json, evidence_quotes_json,
                      confidence, priority, manual_override, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'none', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        qa_id,
                        kb_id,
                        file_node_id,
                        question,
                        answer,
                        audit_status,
                        _j(qa.get("extended_questions") or []),
                        qa.get("answer_type") or "auto_qa",
                        qa.get("generation_source") or "auto_pregenerated",
                        qa.get("source_type"),
                        _j(qa.get("source_chunk_ids") or []),
                        _j(qa.get("source_field_ids") or []),
                        _j(qa.get("evidence_quotes") or []),
                        qa.get("confidence"),
                        int(qa.get("priority") or 0),
                        1 if qa.get("manual_override") else 0,
                        _j(qa.get("metadata") or {}),
                    ),
                )
                saved_ids.append(qa_id)
        conn.commit()
    return saved_ids


def load_field_snapshot(kb_id: int, file_node_id: int, field_id: int, parse_generation: str | None = None) -> dict[str, Any]:
    snapshot = load_index_snapshot(kb_id, file_node_id, parse_generation)
    field_rows = [row for row in snapshot["fields"] if row["id"] == field_id]
    if not field_rows:
        raise RuntimeError(f"field not found in active snapshot: kb_id={kb_id}, file_node_id={file_node_id}, field_id={field_id}")
    chunk_ids = {row.get("source_chunk_id") for row in field_rows if row.get("source_chunk_id") is not None}
    mention_rows = [row for row in snapshot["mentions"] if row["field_id"] == field_id]
    chunk_rows = [row for row in snapshot["chunks"] if row["id"] in chunk_ids]
    graph_nodes = [row for row in snapshot["graph_nodes"] if row.get("source_field_id") == field_id]
    graph_edges = [row for row in snapshot["graph_edges"] if row.get("source_field_id") == field_id]
    return {
        **snapshot,
        "chunks": chunk_rows,
        "fields": field_rows,
        "mentions": mention_rows,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
    }


def mark_file_index_deleted(kb_id: int, file_node_id: int) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kb_chunk
                SET index_sync_status='none', index_generation=NULL
                WHERE kb_id=%s AND file_node_id=%s AND del_flag=0
                """,
                (kb_id, file_node_id),
            )
            cur.execute(
                """
                UPDATE kb_file_node
                SET index_status='none', current_index_generation=NULL
                WHERE id=%s AND kb_id=%s
                """,
                (file_node_id, kb_id),
            )
            cur.execute(
                """
                UPDATE kb_file_task
                SET stage='done', index_sync_status='none', index_generation=NULL
                WHERE file_node_id=%s
                """,
                (file_node_id,),
            )
            cur.execute(
                """
                INSERT INTO file_index_pointer(id, kb_id, file_node_id, current_parse_generation, current_index_generation, status)
                VALUES (%s, %s, %s, NULL, NULL, 'deleted')
                ON DUPLICATE KEY UPDATE current_index_generation=NULL, status='deleted', update_time=CURRENT_TIMESTAMP
                """,
                (new_id(), kb_id, file_node_id),
            )
        conn.commit()


def mark_chunk_index_state(kb_id: int, file_node_id: int, chunk_ids: list[int], index_generation: str | None, success: bool, error_msg: str | None = None) -> None:
    if not chunk_ids:
        return
    status = "synced" if success else "failed"
    with connect() as conn:
        with conn.cursor() as cur:
            sql = f"""
                UPDATE kb_chunk
                SET index_sync_status=%s, index_generation=%s
                WHERE kb_id=%s AND file_node_id=%s AND id IN ({','.join(['%s'] * len(chunk_ids))})
            """
            cur.execute(sql, [status, index_generation if success else None, kb_id, file_node_id, *chunk_ids])
            if success:
                cur.execute(
                    """
                    UPDATE kb_file_node
                    SET index_status='synced', current_index_generation=%s
                    WHERE id=%s AND kb_id=%s
                    """,
                    (index_generation, file_node_id, kb_id),
                )
                cur.execute(
                    """
                    INSERT INTO file_index_pointer(id, kb_id, file_node_id, current_parse_generation, current_index_generation, status)
                    VALUES (%s, %s, %s, (SELECT current_parse_generation FROM kb_file_node WHERE id=%s), %s, 'active')
                    ON DUPLICATE KEY UPDATE current_index_generation=VALUES(current_index_generation), status='active', update_time=CURRENT_TIMESTAMP
                    """,
                    (new_id(), kb_id, file_node_id, file_node_id, index_generation),
                )
            cur.execute(
                """
                INSERT INTO retrieve_index_state(id, kb_id, file_node_id, parse_generation, index_generation, target_type, status, indexed_count, error_msg)
                VALUES (%s, %s, %s, (SELECT current_parse_generation FROM kb_file_node WHERE id=%s), %s, 'chunk_partial', %s, %s, %s)
                ON DUPLICATE KEY UPDATE status=VALUES(status), indexed_count=VALUES(indexed_count), error_msg=VALUES(error_msg), update_time=CURRENT_TIMESTAMP
                """,
                (new_id(), kb_id, file_node_id, file_node_id, index_generation or "", status, len(chunk_ids), error_msg),
            )
        conn.commit()


def mark_qa_index_state(kb_id: int, qa_ids: list[int], index_generation: str | None, success: bool, error_msg: str | None = None) -> None:
    if not qa_ids:
        return
    status = "synced" if success else "failed"
    with connect() as conn:
        with conn.cursor() as cur:
            sql = f"""
                UPDATE kb_qa_pair
                SET index_sync_status=%s, index_record_id=%s, sync_error_message=%s
                WHERE kb_id=%s AND id IN ({','.join(['%s'] * len(qa_ids))})
            """
            cur.execute(sql, [status, index_generation if success else None, error_msg, kb_id, *qa_ids])
        conn.commit()


def get_index_status(kb_id: int, file_node_id: int) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT n.id, n.parse_status, n.index_status, n.current_parse_generation, n.current_index_generation,
                       p.previous_index_generation, n.update_time
                FROM kb_file_node n
                LEFT JOIN file_index_pointer p ON p.kb_id=n.kb_id AND p.file_node_id=n.id
                WHERE n.kb_id=%s AND n.id=%s
                """,
                (kb_id, file_node_id),
            )
            file_row = cur.fetchone()
            if not file_row:
                raise RuntimeError(f"file_node not found: kb_id={kb_id}, file_node_id={file_node_id}")
            cur.execute(
                """
                SELECT target_type, status, indexed_count, error_msg, update_time
                FROM retrieve_index_state
                WHERE kb_id=%s AND file_node_id=%s
                ORDER BY update_time DESC
                """,
                (kb_id, file_node_id),
            )
            index_rows = cur.fetchall()
    return {
        "kb_id": kb_id,
        "file_node_id": file_node_id,
        "parse_status": file_row["parse_status"],
        "index_status": file_row["index_status"],
        "current_parse_generation": file_row["current_parse_generation"],
        "current_index_generation": file_row["current_index_generation"],
        "previous_index_generation": file_row.get("previous_index_generation"),
        "targets": index_rows,
        "updated_at": file_row["update_time"],
    }


def load_review_extractions(kb_id: int, file_node_id: int, parse_generation: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM kb_file_node WHERE kb_id=%s AND id=%s AND del_flag=0", (kb_id, file_node_id))
            file_node = cur.fetchone()
            if not file_node:
                raise RuntimeError(f"file_node not found: kb_id={kb_id}, file_node_id={file_node_id}")
            effective = parse_generation or file_node.get("current_parse_generation")
            cur.execute(
                """
                SELECT f.*, m.id AS mention_id, m.chunk_id, m.revision_id, m.evidence_text, m.char_start, m.char_end, m.alignment_status, m.page_no, m.block_ids, m.bbox_json,
                       c.seq_no, r.title_path, c.section_type, c.content AS chunk_content
                FROM file_structured_field f
                LEFT JOIN file_field_mentions m ON m.kb_id=f.kb_id AND m.file_node_id=f.file_node_id AND m.parse_generation=f.parse_generation AND m.field_id=f.id
                LEFT JOIN kb_chunk c ON c.id=m.chunk_id
                LEFT JOIN kb_chunk_revision r ON r.id=COALESCE(c.latest_revision_id, c.published_revision_id)
                WHERE f.kb_id=%s AND f.file_node_id=%s AND f.parse_generation=%s AND f.del_flag=0
                ORDER BY f.id, m.id
                """,
                (kb_id, file_node_id, effective),
            )
            rows = cur.fetchall()
            cur.execute(
                """
                SELECT target_type, status, indexed_count, error_msg, index_generation, update_time
                FROM retrieve_index_state
                WHERE kb_id=%s AND file_node_id=%s
                ORDER BY update_time DESC
                """,
                (kb_id, file_node_id),
            )
            index_state = cur.fetchall()
    fields_by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        field = fields_by_id.setdefault(
            row["id"],
            {
                "field_id": row["id"],
                "field_code": row["field_code"],
                "field_name_cn": row["field_name_cn"],
                "value_text": row.get("value_text"),
                "aliases": json.loads(row["aliases_json"]) if isinstance(row.get("aliases_json"), str) else row.get("aliases_json"),
                "normalized_json": json.loads(row["normalized_json"]) if isinstance(row.get("normalized_json"), str) else row.get("normalized_json"),
                "source_chunk_id": row.get("source_chunk_id"),
                "source_section_type": row.get("source_section_type"),
                "mentions": [],
            },
        )
        if row.get("mention_id"):
            field["mentions"].append(
                {
                    "mention_id": row["mention_id"],
                    "chunk_id": row.get("chunk_id"),
                    "revision_id": row.get("revision_id"),
                    "evidence_text": row.get("evidence_text"),
                    "char_start": row.get("char_start"),
                    "char_end": row.get("char_end"),
                    "alignment_status": row.get("alignment_status"),
                    "page_no": row.get("page_no"),
                    "block_ids": json.loads(row["block_ids"]) if isinstance(row.get("block_ids"), str) else row.get("block_ids"),
                    "bbox": json.loads(row["bbox_json"]) if isinstance(row.get("bbox_json"), str) else row.get("bbox_json"),
                    "section_type": row.get("section_type"),
                    "chunk_seq_no": row.get("seq_no"),
                    "chunk_content_preview": (row.get("chunk_content") or "")[:500],
                }
            )
    return {
        "kb_id": kb_id,
        "file_node_id": file_node_id,
        "parse_generation": effective,
        "index_generation": file_node.get("current_index_generation"),
        "fields": list(fields_by_id.values()),
        "index_state": index_state,
    }


def load_char_map(kb_id: int, file_node_id: int, parse_generation: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            if not parse_generation:
                cur.execute("SELECT current_parse_generation FROM kb_file_node WHERE kb_id=%s AND id=%s AND del_flag=0", (kb_id, file_node_id))
                parse_generation = (cur.fetchone() or {}).get("current_parse_generation")
            if not parse_generation:
                raise RuntimeError(f"parse_generation not found: kb_id={kb_id}, file_node_id={file_node_id}")
            cur.execute(
                """
                SELECT span_id, text_version, global_char_start, global_char_end, page_no, block_id, line_no, bbox_json, positions_json, source_type, block_type, text
                FROM file_char_map
                WHERE kb_id=%s AND file_node_id=%s AND parse_generation=%s
                ORDER BY global_char_start, id
                """,
                (kb_id, file_node_id, parse_generation),
            )
            rows = cur.fetchall()
    normalized_text = ""
    if rows:
        parts: list[str] = []
        last_end = 0
        for row in rows:
            start = int(row["global_char_start"])
            if start > last_end:
                parts.append("\n" * (start - last_end))
            parts.append(row.get("text") or "")
            last_end = int(row["global_char_end"])
        normalized_text = "".join(parts)
    return {
        "kb_id": kb_id,
        "file_node_id": file_node_id,
        "parse_generation": parse_generation,
        "text_version": rows[0]["text_version"] if rows else "norm_v1",
        "normalized_text": normalized_text,
        "spans": [
            {
                "span_id": row["span_id"],
                "global_char_start": row["global_char_start"],
                "global_char_end": row["global_char_end"],
                "page_no": row["page_no"],
                "block_id": row["block_id"],
                "line_no": row.get("line_no"),
                "bbox": json.loads(row["bbox_json"]) if isinstance(row.get("bbox_json"), str) else row.get("bbox_json"),
                "positions": json.loads(row["positions_json"]) if isinstance(row.get("positions_json"), str) else row.get("positions_json"),
                "source_type": row.get("source_type"),
                "block_type": row["block_type"],
                "text": row["text"],
            }
            for row in rows
        ],
    }


def search_file_tables(
    kb_id: int,
    query: str,
    file_node_ids: list[int] | None = None,
    parse_generation: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    terms = [item for item in str(query or "").split() if item]
    if not terms and query:
        terms = [str(query).strip()]
    with connect() as conn:
        with conn.cursor() as cur:
            params: list[Any] = [kb_id]
            sql = """
                SELECT
                    t.id AS table_id,
                    t.file_node_id,
                    t.parse_generation,
                    t.table_key,
                    t.page_no,
                    t.title,
                    t.markdown,
                    t.metadata_json,
                    r.id AS row_id,
                    r.row_index,
                    r.row_json
                FROM file_tables t
                LEFT JOIN file_table_rows r ON r.table_id = t.id
                WHERE t.kb_id=%s
            """
            if file_node_ids:
                sql += f" AND t.file_node_id IN ({','.join(['%s'] * len(file_node_ids))})"
                params.extend(file_node_ids)
            if parse_generation:
                sql += " AND t.parse_generation=%s"
                params.append(parse_generation)
            if terms:
                like_parts: list[str] = []
                for term in terms[:5]:
                    like_parts.append("(t.title LIKE %s OR t.markdown LIKE %s OR CAST(r.row_json AS CHAR) LIKE %s)")
                    pattern = f"%{term}%"
                    params.extend([pattern, pattern, pattern])
                sql += " AND (" + " OR ".join(like_parts) + ")"
            sql += " ORDER BY t.file_node_id, t.page_no, t.table_key, r.row_index LIMIT %s"
            params.append(max(1, min(int(limit), 200)))
            cur.execute(sql, params)
            rows = cur.fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        row_json = row.get("row_json")
        metadata = row.get("metadata_json")
        results.append(
            {
                "table_id": row["table_id"],
                "file_node_id": row["file_node_id"],
                "parse_generation": row["parse_generation"],
                "table_key": row["table_key"],
                "page_no": row.get("page_no"),
                "title": row.get("title"),
                "markdown_preview": (row.get("markdown") or "")[:1000],
                "metadata": json.loads(metadata) if isinstance(metadata, str) else metadata,
                "row_id": row.get("row_id"),
                "row_index": row.get("row_index"),
                "row": json.loads(row_json) if isinstance(row_json, str) else row_json,
            }
        )
    return results


def update_field_value(
    kb_id: int,
    file_node_id: int,
    field_id: int,
    new_value_text: str,
    new_normalized_json: dict[str, Any] | None = None,
    reason: str | None = None,
    reviewer: str | None = None,
    review_status: str | None = None,
    evidence_chunk_id: int | None = None,
    evidence_quote: str | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM file_structured_field
                WHERE kb_id=%s AND file_node_id=%s AND id=%s AND del_flag=0
                """,
                (kb_id, file_node_id, field_id),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"field not found: kb_id={kb_id}, file_node_id={file_node_id}, field_id={field_id}")
            cur.execute(
                """
                INSERT INTO field_review_history(id, kb_id, file_node_id, field_id, old_value_text, new_value_text, old_normalized_json, new_normalized_json, reason, reviewer, review_status, evidence_chunk_id, evidence_quote)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    new_id(),
                    kb_id,
                    file_node_id,
                    field_id,
                    row.get("value_text"),
                    new_value_text,
                    row.get("normalized_json"),
                    _j(new_normalized_json),
                    reason,
                    reviewer,
                    review_status,
                    evidence_chunk_id,
                    evidence_quote,
                ),
            )
            cur.execute(
                """
                UPDATE file_structured_field
                SET value_text=%s,
                    normalized_json=%s,
                    update_time=CURRENT_TIMESTAMP
                WHERE kb_id=%s AND file_node_id=%s AND id=%s
                """,
                (new_value_text, _j(new_normalized_json), kb_id, file_node_id, field_id),
            )
        conn.commit()
    return {
        "field_id": field_id,
        "value_text": new_value_text,
        "normalized_json": new_normalized_json,
        "reviewer": reviewer,
        "review_status": review_status,
    }


def review_chunk(
    *,
    kb_id: int,
    file_node_id: int,
    chunk_id: int,
    action: str,
    content: str | None = None,
    summary: str | None = None,
    reviewer: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    action = action.strip().lower()
    if action not in {"approve", "reject"}:
        raise RuntimeError("chunk review action must be approve or reject")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.*, r.id AS revision_id, r.revision_no, r.title, r.title_path, r.content_for_embedding, r.content_for_bm25,
                       r.page_start AS revision_page_start, r.page_end AS revision_page_end, r.block_ids AS revision_block_ids,
                       r.bbox_json AS revision_bbox_json, r.metadata_json AS revision_metadata_json
                FROM kb_chunk c
                JOIN kb_chunk_revision r ON r.id = COALESCE(c.latest_revision_id, c.published_revision_id)
                WHERE c.kb_id=%s AND c.file_node_id=%s AND c.id=%s AND c.del_flag=0
                """,
                (kb_id, file_node_id, chunk_id),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError(f"chunk not found: kb_id={kb_id}, file_node_id={file_node_id}, chunk_id={chunk_id}")

            if action == "reject":
                cur.execute(
                    """
                    UPDATE kb_chunk
                    SET enabled=0,
                        audit_status='rejected',
                        reject_reason=%s,
                        index_sync_status='none',
                        index_generation=NULL,
                        update_time=CURRENT_TIMESTAMP
                    WHERE kb_id=%s AND file_node_id=%s AND id=%s
                    """,
                    (reason, kb_id, file_node_id, chunk_id),
                )
                conn.commit()
                return {
                    "chunk_id": chunk_id,
                    "action": action,
                    "audit_status": "rejected",
                    "enabled": False,
                    "reject_reason": reason,
                }

            new_content = content if content is not None else row.get("content")
            new_summary = summary if summary is not None else row.get("summary")
            content_changed = new_content != row.get("content") or new_summary != row.get("summary")
            published_revision_id = row.get("published_revision_id") or row.get("revision_id")
            latest_revision_id = row.get("latest_revision_id") or row.get("revision_id")
            if content_changed:
                new_revision_id = new_id()
                cur.execute(
                    """
                    INSERT INTO kb_chunk_revision(
                        id, kb_id, file_node_id, chunk_id, base_revision_id, revision_no, revision_source,
                        editor_name, edit_reason, content, summary, content_for_embedding, content_for_bm25,
                        title, title_path, page_start, page_end, block_ids, bbox_json, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 'review', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        new_revision_id,
                        kb_id,
                        file_node_id,
                        chunk_id,
                        latest_revision_id,
                        int(row.get("revision_no") or 1) + 1,
                        reviewer,
                        reason,
                        new_content,
                        new_summary,
                        new_content,
                        new_content,
                        row.get("title"),
                        row.get("title_path"),
                        row.get("revision_page_start") or row.get("page_start"),
                        row.get("revision_page_end") or row.get("page_end"),
                        row.get("revision_block_ids") or row.get("block_ids"),
                        row.get("revision_bbox_json"),
                        row.get("revision_metadata_json") or row.get("metadata_json"),
                    ),
                )
                latest_revision_id = new_revision_id
                published_revision_id = new_revision_id

            content_hash = hashlib.sha1((new_content or "").encode("utf-8")).hexdigest()
            cur.execute(
                """
                UPDATE kb_chunk
                SET content=%s,
                    summary=%s,
                    enabled=1,
                    audit_status='approved',
                    reject_reason=NULL,
                    published_revision_id=%s,
                    latest_revision_id=%s,
                    draft_revision_id=NULL,
                    content_hash=%s,
                    sim_hash=%s,
                    index_sync_status='none',
                    update_time=CURRENT_TIMESTAMP
                WHERE kb_id=%s AND file_node_id=%s AND id=%s
                """,
                (new_content, new_summary, published_revision_id, latest_revision_id, content_hash, content_hash, kb_id, file_node_id, chunk_id),
            )
        conn.commit()
    return {
        "chunk_id": chunk_id,
        "action": action,
        "audit_status": "approved",
        "enabled": True,
        "revision_id": published_revision_id,
        "content_changed": content_changed,
    }


def review_file(
    *,
    kb_id: int,
    file_node_id: int,
    action: str,
    reviewer: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    action = action.strip().lower()
    if action not in {"approve", "reject"}:
        raise RuntimeError("file review action must be approve or reject")
    audit_status = "approved" if action == "approve" else "rejected"
    enabled = 1 if action == "approve" else 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_parse_generation FROM kb_file_node WHERE kb_id=%s AND id=%s AND del_flag=0",
                (kb_id, file_node_id),
            )
            file_row = cur.fetchone()
            if not file_row:
                raise RuntimeError(f"file_node not found: kb_id={kb_id}, file_node_id={file_node_id}")
            parse_generation = file_row.get("current_parse_generation")
            cur.execute(
                """
                UPDATE kb_file_node
                SET audit_status=%s,
                    index_status=IF(%s=1, index_status, 'none'),
                    current_index_generation=IF(%s=1, current_index_generation, NULL),
                    update_time=CURRENT_TIMESTAMP
                WHERE kb_id=%s AND id=%s
                """,
                (audit_status, enabled, enabled, kb_id, file_node_id),
            )
            cur.execute(
                """
                UPDATE kb_chunk
                SET enabled=%s,
                    audit_status=%s,
                    reject_reason=IF(%s=1, NULL, %s),
                    index_sync_status='none',
                    index_generation=IF(%s=1, index_generation, NULL),
                    update_time=CURRENT_TIMESTAMP
                WHERE kb_id=%s AND file_node_id=%s AND del_flag=0
                """,
                (enabled, audit_status, enabled, reason, enabled, kb_id, file_node_id),
            )
            if action == "reject":
                cur.execute(
                    """
                    UPDATE file_index_pointer
                    SET current_index_generation=NULL,
                        status='rejected',
                        update_time=CURRENT_TIMESTAMP
                    WHERE kb_id=%s AND file_node_id=%s
                    """,
                    (kb_id, file_node_id),
                )
            cur.execute(
                """
                INSERT INTO kb_file_task_history(id, kb_id, file_node_id, task_type, stage, status, parse_generation, error_msg, payload_json)
                VALUES (%s, %s, %s, 'review', 'file_review', %s, %s, %s, %s)
                """,
                (
                    new_id(),
                    kb_id,
                    file_node_id,
                    audit_status,
                    parse_generation,
                    None if action == "approve" else reason,
                    _j({"reviewer": reviewer, "reason": reason, "action": action}),
                ),
            )
            cur.execute(
                "SELECT COUNT(*) AS count FROM kb_chunk WHERE kb_id=%s AND file_node_id=%s AND del_flag=0",
                (kb_id, file_node_id),
            )
            chunk_count = int((cur.fetchone() or {}).get("count") or 0)
        conn.commit()
    return {
        "kb_id": kb_id,
        "file_node_id": file_node_id,
        "action": action,
        "audit_status": audit_status,
        "enabled": bool(enabled),
        "parse_generation": parse_generation,
        "affected_chunks": chunk_count,
        "reviewer": reviewer,
        "reason": reason,
    }
