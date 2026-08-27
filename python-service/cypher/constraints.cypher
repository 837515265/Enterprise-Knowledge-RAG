CREATE CONSTRAINT file_identity IF NOT EXISTS
FOR (n:File) REQUIRE (n.kb_id, n.file_node_id) IS UNIQUE;

CREATE CONSTRAINT chunk_identity IF NOT EXISTS
FOR (n:Chunk) REQUIRE (n.kb_id, n.file_node_id, n.chunk_id) IS UNIQUE;

CREATE CONSTRAINT plan_identity IF NOT EXISTS
FOR (n:BusinessPlan) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT field_identity IF NOT EXISTS
FOR (n:BusinessField) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT region_identity IF NOT EXISTS
FOR (n:Region) REQUIRE (n.kb_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT industry_identity IF NOT EXISTS
FOR (n:Industry) REQUIRE (n.kb_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT organization_identity IF NOT EXISTS
FOR (n:Organization) REQUIRE (n.kb_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT entity_identity IF NOT EXISTS
FOR (n:Entity) REQUIRE (n.kb_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT concept_identity IF NOT EXISTS
FOR (n:Concept) REQUIRE (n.kb_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT document_identity IF NOT EXISTS
FOR (n:Document) REQUIRE (n.kb_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT assertion_identity IF NOT EXISTS
FOR (n:Assertion) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT requirement_identity IF NOT EXISTS
FOR (n:Requirement) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT condition_identity IF NOT EXISTS
FOR (n:Condition) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT process_step_identity IF NOT EXISTS
FOR (n:ProcessStep) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT attribute_identity IF NOT EXISTS
FOR (n:Attribute) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT metric_identity IF NOT EXISTS
FOR (n:Metric) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT value_identity IF NOT EXISTS
FOR (n:Value) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT time_identity IF NOT EXISTS
FOR (n:Time) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT location_identity IF NOT EXISTS
FOR (n:Location) REQUIRE (n.kb_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT section_identity IF NOT EXISTS
FOR (n:Section) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT person_role_identity IF NOT EXISTS
FOR (n:PersonRole) REQUIRE (n.kb_id, n.file_node_id, n.node_key) IS UNIQUE;

CREATE CONSTRAINT graph_community_identity IF NOT EXISTS
FOR (n:GraphCommunity) REQUIRE (n.kb_id, n.community_key) IS UNIQUE;

CREATE INDEX entity_name_idx IF NOT EXISTS
FOR (n:Entity) ON (n.name_cn);

CREATE INDEX concept_name_idx IF NOT EXISTS
FOR (n:Concept) ON (n.name_cn);

CREATE INDEX assertion_relation_idx IF NOT EXISTS
FOR (n:Assertion) ON (n.relation_type);

CREATE INDEX field_code_idx IF NOT EXISTS
FOR (n:BusinessField) ON (n.field_code);

CREATE INDEX plan_name_idx IF NOT EXISTS
FOR (n:BusinessPlan) ON (n.name_cn);
