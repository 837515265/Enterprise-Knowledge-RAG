# Catalog Chunker 解析质量问题分析报告

## 问题现象

博兴县数字设施渔业产业园担保服务方案.pdf 解析后，"二、准入条件" 下的 9 条内容丢失 items 1-6、8、9，只剩 item 7 的碎片。其他文件（按揭农业贷—邹城市草莓产业集群担保服务方案等）也有类似问题。

## 完整问题链条

```
OCR (MinerU) → _normalize_mineru_middle_json → catalog_chunker → chunks → MySQL
     ✓                    ✓                      ✗ ← 问题在这里
```

### Step 1: OCR — 正常

MinerU 返回的 `md_content` 和 `middle_json` 都包含完整的 9 个 items。

### Step 2: Block 提取 — 修复过（commit 14d6019）

**问题：** list 类型 block 的内容在 `block["blocks"]` 子数组中，`_extract_block_text_from_lines()` 只看顶层 `block["lines"]`，导致列表项文本为空。

**修复：** 递归提取 list block 的子项。

修复后 block 数据正确，Page 2 block [4] 包含完整列表文本。

### Step 3: Catalog Chunker — 两个问题

#### 问题 3a: LLM catalog 调用返回垃圾输出

**请求：**

```
POST http://124.128.251.51:21081/v1/chat/completions
Model: qwen2.5-32b
Body size: 15,596 bytes
max_tokens: 未设置（None，不传给模型）
请求内容：
{
  "body_json": {
    "messages": [
      {
        "content": "你是企业知识库 RAG-Doc 的目录规划模型。\n你的任务不是回答问题，也不是输出 chunk 正文，而是根据文档文本生成稳定、可映射、可校验的结构目录。\n\n必须遵守：\n1. 只输出 JSON object，不要输出 Markdown。\n2. 每个目录节点只输出 candidate_id、level、title、title_source、section_type、confidence；只有没有候选标题可用时才补充 start_anchor。\n3. candidate_id 必须优先来自输入的 heading_candidates；不要编造 candidate_id。\n4. 如果原文有真实标题，title_source=explicit；如果是语义标题，title_source=inferred。\n5. 不要输出 block_id、page_no、bbox、数据库 id。\n6. 不要省略附件、表格、接口、错误码、关键条款。\n7. 同名标题不能简单合并；例如多个“准入条件”要分别输出。\n8. section_type 必须从当前 profile 的白名单选择，无法判断时写 text_section。\n",
        "role": "system"
      },
      {
        "content": "## Profile\n当前 profile: business_plan\n\nsection_type 只能从下面白名单选择，不能创造新类型：\n- document_meta（文档基本信息）：方案名称、文号、发文背景、总体目标、政策依据等总览性内容。  典型标题/内容：方案名称、政策依据、背景说明、总体目标\n- service_object（服务对象）：方案明确面向的客户、主体、产业经营者或适用人群。  典型标题/内容：服务对象、支持对象、客户范围、适用主体\n- business_scope（适用范围/业务范围）：方案覆盖的地区、产业、业务场景、品类、客户类型或业务边界。  典型标题/内容：适用范围、业务范围、产业范围、区域范围\n- admission_requirement（准入条件）：申请主体必须满足的资质、经营、信用、资产负债、合规等准入要求。  典型标题/内容：准入条件、客户准入、基本条件、申请条件\n- credit_limit（授信/担保额度）：单户、单笔、最高、最低额度，额度测算公式，资产负债率约束等。  典型标题/内容：授信额度、担保额度、单户额度、额度测算\n- guarantee_term（期限）：贷款期限、担保期限、授信期限、续保期限等时间长度约束。  典型标题/内容：授信期限、担保期限、贷款期限\n- credit_purpose（资金用途）：贷款、授信或担保资金允许或禁止用于哪些生产经营事项。  典型标题/内容：贷款用途、授信用途、资金用途\n- fee_rate（费率/收费标准）：担保费率、年化费率、服务费、优惠费率、收费方式等。  典型标题/内容：担保费率、收费标准、费率优惠\n- risk_mitigation（风险缓释/风控措施）：风险分担、风险补偿、保证金、质押率、监测预警、贷后管理等。  典型标题/内容：风险缓释、风险分担、贷后管理、风险控制\n- counter_guarantee（反担保）：抵押、质押、保证人、免抵押、追加担保等反担保安排。  典型标题/内容：反担保、抵质押、保证措施\n- material_requirement（申请材料）：申请、准入、审批、放款所需提交的材料清单。  典型标题/内容：申请材料、资料清单、所需材料\n- procedure（办理流程）：申请、受理、尽调、审批、签约、放款、备案等流程步骤。  典型标题/内容：办理流程、操作流程、业务流程、审批流程\n- cooperation_org（合作机构/职责分工）：银行、担保机构、政府部门、平台方等参与主体及职责分工。  典型标题/内容：合作机构、职责分工、参与主体\n- appendix（附件）：附件、模板、表单、补充说明、附录等。  典型标题/内容：附件、附表、申请表\n- text_section（普通正文）：无法稳定归入上述业务类别，但仍需保留的正文段落。  典型标题/内容：其他说明、一般正文\n\n分类判定规则：\n1. 优先按章节标题和正文首段的真实语义分类，不要只看关键词。\n2. 只要不能稳定判断，就输出 text_section，不能猜测。\n3. 同一个父级下重复出现的同名小节要分别保留，不要合并。\n4. section_type 只影响检索路由，不影响原文保留；宁可保守，也不要跨 profile 误分类。\n\n## 当前窗口\nwindow_index: 1\nwindow_count: 1\nchar_range: 0-1915\n\n## 已有目录摘要\n无\n\n## 滚动窗口要求\n1. 如果当前窗口开头承接上一个窗口的章节，不要重复输出已经出现过的目录节点，除非当前窗口出现新的真实标题。\n2. 如果当前窗口继续展开上一窗口最后一个父级章节，请保持 level 连续，不要把子级误提成一级。\n3. overlap 区域中的重复标题只保留一次。\n\n## 输出 JSON Schema\n{\n  \"sections\": [\n    {\n      \"candidate_id\": \"h_00001\",\n      \"level\": 1,\n      \"title\": \"标题\",\n      \"title_source\": \"explicit|inferred\",\n      \"section_type\": \"document_meta|service_object|business_scope|admission_requirement|credit_limit|guarantee_term|credit_purpose|fee_rate|risk_mitigation|counter_guarantee|material_requirement|procedure|cooperation_org|appendix|text_section\",\n      \"confidence\": 0.95\n    }\n  ],\n  \"warnings\": []\n}\n\n## heading_candidates\n[{\"candidate_id\":\"h_00001\",\"text\":\"山东省农业发展信贷担保有限责任公司 关于印发《博兴县数字设施渔业产业园 担保服务方案》的通知\",\"title\":\"山东省农业发展信贷担保有限责任公司 关于印发《博兴县数字设施渔业产业园 担保服务方案》的通知\",\"level_guess\":1,\"numbering_type\":\"layout_title\",\"page_no\":1,\"block_id\":\"p1_b001\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00002\",\"text\":\"博兴县数字设施渔业产业园担保服务方案\",\"title\":\"博兴县数字设施渔业产业园担保服务方案\",\"level_guess\":1,\"numbering_type\":\"layout_title\",\"page_no\":2,\"block_id\":\"p2_b001\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00003\",\"text\":\"一、服务对象\",\"title\":\"一、服务对象\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":2,\"block_id\":\"p2_b002\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00004\",\"text\":\"二、准入条件\",\"title\":\"二、准入条件\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":2,\"block_id\":\"p2_b004\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00005\",\"text\":\"7.养殖车间主体建设完成后，客户与千乘文旅签订《购买协\",\"title\":\"7.养殖车间主体建设完成后，客户与千乘文旅签订《购买协\",\"level_guess\":3,\"numbering_type\":\"num_dot\",\"page_no\":2,\"block_id\":\"p2_b005\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00006\",\"text\":\"三、额度测算\",\"title\":\"三、额度测算\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":3,\"block_id\":\"p3_b003\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00007\",\"text\":\"四、贷款期限及还款方式\",\"title\":\"四、贷款期限及还款方式\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":3,\"block_id\":\"p3_b007\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00008\",\"text\":\"五、授信用途\",\"title\":\"五、授信用途\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":3,\"block_id\":\"p3_b009\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00009\",\"text\":\"六、担保费收取\",\"title\":\"六、担保费收取\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":3,\"block_id\":\"p3_b011\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00010\",\"text\":\"七、反担保措施\",\"title\":\"七、反担保措施\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":3,\"block_id\":\"p3_b013\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00011\",\"text\":\"八、风险缓释措施\",\"title\":\"八、风险缓释措施\",\"level_guess\":1,\"numbering_type\":\"cn_top\",\"page_no\":4,\"block_id\":\"p4_b002\",\"content_role\":\"main_body\"},{\"candidate_id\":\"h_00012\",\"text\":\"附件：1.党组织领办合作社名单\",\"title\":\"附件1.党组织领办合作社名单\",\"level_guess\":1,\"numbering_type\":\"appendix\",\"page_no\":5,\"block_id\":\"p5_b002\",\"content_role\":\"appendix\"},{\"candidate_id\":\"h_00013\",\"text\":\"2. 客户推荐函\",\"title\":\"2.客户推荐函\",\"level_guess\":3,\"numbering_type\":\"num_dot\",\"page_no\":5,\"block_id\":\"p5_b003\",\"content_role\":\"appendix\"},{\"candidate_id\":\"h_00014\",\"text\":\"3. 资料清单\",\"title\":\"3.资料清单\",\"level_guess\":3,\"numbering_type\":\"num_dot\",\"page_no\":5,\"block_id\":\"p5_b004\",\"content_role\":\"appendix\"},{\"candidate_id\":\"h_00015\",\"text\":\"附件 2\",\"title\":\"附件 2\",\"level_guess\":1,\"numbering_type\":\"appendix\",\"page_no\":9,\"block_id\":\"p9_b001\",\"content_role\":\"appendix\"},{\"candidate_id\":\"h_00016\",\"text\":\"客户推荐函\",\"title\":\"客户推荐函\",\"level_guess\":1,\"numbering_type\":\"layout_title\",\"page_no\":9,\"block_id\":\"p9_b002\",\"content_role\":\"appendix\"},{\"candidate_id\":\"h_00017\",\"text\":\"附件 3\",\"title\":\"附件 3\",\"level_guess\":1,\"numbering_type\":\"appendix\",\"page_no\":10,\"block_id\":\"p10_b001\",\"content_role\":\"appendix\"}]\n\n## 文档窗口文本\n[p1_b000][p1][title] %E5%8D%9A%E5%85%B4%E5%8E%BF%E6%95%B0%E5%AD%97%E8%AE%BE%E6%96%BD%E6%B8%94%E4%B8%9A%E4%BA%A7%E4%B8%9A%E5%9B%AD%E6%8B%85%E4%BF%9D%E6%9C%8D%E5%8A%A1%E6%96%B9%E6%A1%88\n[p1_b001][p1][title] 山东省农业发展信贷担保有限责任公司 关于印发《博兴县数字设施渔业产业园 担保服务方案》的通知\n[p1_b002][p1][text] 滨州管理中心:\n[p1_b003][p1][text] 《博兴县数字设施渔业产业园担保服务方案》已于2024年3月22日经公司评审会审批通过，并于即日起施行，现予印发，请认真抓好贯彻落实。\n[p1_b004][p1][text] 山东省农业发展信贷担保有限责任公司\n[p1_b005][p1][text] 2024年3月27日\n[p2_b001][p2][title] 博兴县数字设施渔业产业园担保服务方案\n[p2_b002][p2][title] 一、服务对象\n[p2_b003][p2][text] 博兴县政府部门推荐的与博兴县千乘文旅体育产业集团有限公司（以下简称千乘文旅）签订购买协议的村党支部领办合作社（附件1）。\n[p2_b004][p2][title] 二、准入条件\n[p2_b005][p2][text] 1. 村党支部领办合作社须持有效营业执照，章程规范、合规，财务制度健全，资信良好；\n2.有固定的生产经营场所，能够正常开展生产经营活动；\n3.村党支部领办合作社理事长年龄加贷款期限不得超65岁，村党支部领办合作社信用状况良好，无重大涉诉未执行终结案件、无失信或被执行未履行信息；\n4.村党支部领办合作社贷款及对外担保五级分类无“正常”之外的状态、最近24个月内不存在连续90天以上或累计6次以上的逾期记录；\n5.须明确村集体占股或参与收益分配;\n6. 博兴县乡村振兴局出具推荐名单及县委常委会或县政府会议纪要（会议纪要中需明确养殖池确权及确权后资产质押等相关事项）;\n7.养殖车间主体建设完成后，客户与千乘文旅签订《购买协\n[p3_b001][p3][text] 议》，明确固定资产建设、确权事宜；\n[p3_b002][p3][text] 8. 博兴县数字设施渔业产业园满足防疫、环保、用地合规等条件；\n9. 滨州管理中心利用遥感技术做好虾池、鱼池圈地工作。\n[p3_b003][p3][title] 三、额度测算\n[p3_b004][p3][text] 总授信额度为 8500 万元。单户担保额度：10 万元（含）至 300 万元（含）。客户授信前资产负债率不超过 50%，授信后资产负债率不超过 70%。\n[p3_b005][p3][text] 单户测算额度=(虾池数量×单个虾池建设成本+鱼池数量×单个鱼池建设成本)×80%-同类存量贷款。建设成本单个虾池17万元、单个鱼池成本12万元。\n[p3_b006][p3][text] 虾池、鱼池建设规模按照推荐函中建设规模确定；自筹资金需事先由博兴县乡村振兴局或合作银行核实确认。\n[p3_b007][p3][title] 四、贷款期限及还款方式\n[p3_b008][p3][text] 贷款期限最长不超过8年，不可循环使用。按照投资回收期采取分期还款方式。\n[p3_b009][p3][title] 五、授信用途\n[p3_b010][p3][text] 贷款用途仅限用于虾池、鱼池及配套设施建设。\n[p3_b011][p3][title] 六、担保费收取\n[p3_b012][p3][text] 按照贷款金额的 0.75%/年收取。\n[p3_b013][p3][title] 七、反担保措施\n[p3_b014][p3][text] 由村党支部领办合作社理事长个人提供连带责任反担保，如\n[p4_b001][p4][text] 遇理事长变更，继任理事长个人须提供连带责任反担保，博兴县乡村振兴局负责协调办理反担保人变更手续。\n[p4_b002][p4][title] 八、风险缓释措施\n[p4_b003][p4][text] 1. 千乘文旅提供50%连带责任反担保。若推荐的客户未能按照合作银行借款合同约定按时偿还贷款本息的，双方共同追偿；追偿的款项无法全部清偿银行贷款导致山东农担发生代偿后，山东农担向千乘文旅发送代偿通知，千乘文旅收到代偿通知后15日内，按照山东农担代偿本息及相关费用偿还代偿款；\n[p4_b004][p4][text] 千乘文旅签署《反担保保证函》，为推荐的客户向山东农担提供连带责任反担保，不再逐笔签署《反担保保证函》；\n[p4_b005][p4][text] 2. 数字设施渔业产业园建成后，由创新发展部对接产业园智慧系统。对接后，保后管理部可对产业园运营及养殖情况进行实时保后；\n3. 数字设施渔业产业园项目纳入“鲁担惠农兴博共富贷”内，博兴县按照 40% 的比例对辖区内的“鲁担惠农兴博共富贷”项目发生的代偿进行最终分担，并统筹安排财政资金 500 万元，专项用于支付博兴县分担的农业信贷担保贷款相关代偿；\n4. 数字设施渔业产业园项目建成项目验收合格后，由博兴县乡村振兴局、千乘文旅配合村党支部领办合作社在“滨州市农村集体资产管理系统”（省级农村集体“三资”监管平台市级管理系统）进行确权，并出具《资产卡片》。合作银行通过博兴县不动产登记中心办理抵押手续；\n[p5_b001][p5][text] 5.省级农村集体“三资”监管平台对接后，管理中心对村党支部领办合作社资产进行监管。\n[p5_b002][p5][text] 附件：1.党组织领办合作社名单\n[p5_b003][p5][text] 2. 客户推荐函\n[p5_b004][p5][text] 3. 资料清单\n[p9_b001][p9][text] 附件 2\n[p9_b002][p9][title] 客户推荐函\n[p9_b003][p9][text] 山东省农业发展信贷担保有限责任公司：\n[p9_b004][p9][text] 现推荐以下村党组织领办合作社给贵司，我单位确认表中均为党组织领办合作社，且具有虾池、鱼池建设贷款需求，望贵单位予以提供金融服务为盼。\n[p9_b005][p9][text] 推荐单位（公章）：\n[p9_b006][p9][text] 年 月 日\n[p10_b001][p10][title] 附件 3\n[p10_b002][p10][text] 抄送：公司领导、各部室，各管理中心、办事处，有关合作银行。\n",
        "role": "user"
      }
    ],
    "model": "qwen2.5-32b",
    "response_format": {
      "type": "json_object"
    },
    "stream": false,
    "temperature": 0
  },
  "body_text": "{\"messages\":[{\"content\":\"你是企业知识库 RAG-Doc 的目录规划模型。\\n你的任务不是回答问题，也不是输出 chunk 正文，而是根据文档文本生成稳定、可映射、可校验的结构目录。\\n\\n必须遵守：\\n1. 只输出 JSON object，不要输出 Markdown。\\n2. 每个目录节点只输出 candidate_id、level、title、title_source、section_type、confidence；只有没有候选标题可用时才补充 start_anchor。\\n3. candidate_id 必须优先来自输入的 heading_candidates；不要编造 candidate_id。\\n4. 如果原文有真实标题，title_source=explicit；如果是语义标题，title_source=inferred。\\n5. 不要输出 block_id、page_no、bbox、数据库 id。\\n6. 不要省略附件、表格、接口、错误码、关键条款。\\n7. 同名标题不能简单合并；例如多个“准入条件”要分别输出。\\n8. section_type 必须从当前 profile 的白名单选择，无法判断时写 text_section。\\n\",\"role\":\"system\"},{\"content\":\"## Profile\\n当前 profile: business_plan\\n\\nsection_type 只能从下面白名单选择，不能创造新类型：\\n- document_meta（文档基本信息）：方案名称、文号、发文背景、总体目标、政策依据等总览性内容。  典型标题/内容：方案名称、政策依据、背景说明、总体目标\\n- service_object（服务对象）：方案明确面向的客户、主体、产业经营者或适用人群。  典型标题/内容：服务对象、支持对象、客户范围、适用主体\\n- business_scope（适用范围/业务范围）：方案覆盖的地区、产业、业务场景、品类、客户类型或业务边界。  典型标题/内容：适用范围、业务范围、产业范围、区域范围\\n- admission_requirement（准入条件）：申请主体必须满足的资质、经营、信用、资产负债、合规等准入要求。  典型标题/内容：准入条件、客户准入、基本条件、申请条件\\n- credit_limit（授信/担保额度）：单户、单笔、最高、最低额度，额度测算公式，资产负债率约束等。  典型标题/内容：授信额度、担保额度、单户额度、额度测算\\n- guarantee_term（期限）：贷款期限、担保期限、授信期限、续保期限等时间长度约束。  典型标题/内容：授信期限、担保期限、贷款期限\\n- credit_purpose（资金用途）：贷款、授信或担保资金允许或禁止用于哪些生产经营事项。  典型标题/内容：贷款用途、授信用途、资金用途\\n- fee_rate（费率/收费标准）：担保费率、年化费率、服务费、优惠费率、收费方式等。  典型标题/内容：担保费率、收费标准、费率优惠\\n- risk_mitigation（风险缓释/风控措施）：风险分担、风险补偿、保证金、质押率、监测预警、贷后管理等。  典型标题/内容：风险缓释、风险分担、贷后管理、风险控制\\n- counter_guarantee（反担保）：抵押、质押、保证人、免抵押、追加担保等反担保安排。  典型标题/内容：反担保、抵质押、保证措施\\n- material_requirement（申请材料）：申请、准入、审批、放款所需提交的材料清单。  典型标题/内容：申请材料、资料清单、所需材料\\n- procedure（办理流程）：申请、受理、尽调、审批、签约、放款、备案等流程步骤。  典型标题/内容：办理流程、操作流程、业务流程、审批流程\\n- cooperation_org（合作机构/职责分工）：银行、担保机构、政府部门、平台方等参与主体及职责分工。  典型标题/内容：合作机构、职责分工、参与主体\\n- appendix（附件）：附件、模板、表单、补充说明、附录等。  典型标题/内容：附件、附表、申请表\\n- text_section（普通正文）：无法稳定归入上述业务类别，但仍需保留的正文段落。  典型标题/内容：其他说明、一般正文\\n\\n分类判定规则：\\n1. 优先按章节标题和正文首段的真实语义分类，不要只看关键词。\\n2. 只要不能稳定判断，就输出 text_section，不能猜测。\\n3. 同一个父级下重复出现的同名小节要分别保留，不要合并。\\n4. section_type 只影响检索路由，不影响原文保留；宁可保守，也不要跨 profile 误分类。\\n\\n## 当前窗口\\nwindow_index: 1\\nwindow_count: 1\\nchar_range: 0-1915\\n\\n## 已有目录摘要\\n无\\n\\n## 滚动窗口要求\\n1. 如果当前窗口开头承接上一个窗口的章节，不要重复输出已经出现过的目录节点，除非当前窗口出现新的真实标题。\\n2. 如果当前窗口继续展开上一窗口最后一个父级章节，请保持 level 连续，不要把子级误提成一级。\\n3. overlap 区域中的重复标题只保留一次。\\n\\n## 输出 JSON Schema\\n{\\n  \\\"sections\\\": [\\n    {\\n      \\\"candidate_id\\\": \\\"h_00001\\\",\\n      \\\"level\\\": 1,\\n      \\\"title\\\": \\\"标题\\\",\\n      \\\"title_source\\\": \\\"explicit|inferred\\\",\\n      \\\"section_type\\\": \\\"document_meta|service_object|business_scope|admission_requirement|credit_limit|guarantee_term|credit_purpose|fee_rate|risk_mitigation|counter_guarantee|material_requirement|procedure|cooperation_org|appendix|text_section\\\",\\n      \\\"confidence\\\": 0.95\\n    }\\n  ],\\n  \\\"warnings\\\": []\\n}\\n\\n## heading_candidates\\n[{\\\"candidate_id\\\":\\\"h_00001\\\",\\\"text\\\":\\\"山东省农业发展信贷担保有限责任公司 关于印发《博兴县数字设施渔业产业园 担保服务方案》的通知\\\",\\\"title\\\":\\\"山东省农业发展信贷担保有限责任公司 关于印发《博兴县数字设施渔业产业园 担保服务方案》的通知\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"layout_title\\\",\\\"page_no\\\":1,\\\"block_id\\\":\\\"p1_b001\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00002\\\",\\\"text\\\":\\\"博兴县数字设施渔业产业园担保服务方案\\\",\\\"title\\\":\\\"博兴县数字设施渔业产业园担保服务方案\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"layout_title\\\",\\\"page_no\\\":2,\\\"block_id\\\":\\\"p2_b001\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00003\\\",\\\"text\\\":\\\"一、服务对象\\\",\\\"title\\\":\\\"一、服务对象\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":2,\\\"block_id\\\":\\\"p2_b002\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00004\\\",\\\"text\\\":\\\"二、准入条件\\\",\\\"title\\\":\\\"二、准入条件\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":2,\\\"block_id\\\":\\\"p2_b004\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00005\\\",\\\"text\\\":\\\"7.养殖车间主体建设完成后，客户与千乘文旅签订《购买协\\\",\\\"title\\\":\\\"7.养殖车间主体建设完成后，客户与千乘文旅签订《购买协\\\",\\\"level_guess\\\":3,\\\"numbering_type\\\":\\\"num_dot\\\",\\\"page_no\\\":2,\\\"block_id\\\":\\\"p2_b005\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00006\\\",\\\"text\\\":\\\"三、额度测算\\\",\\\"title\\\":\\\"三、额度测算\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":3,\\\"block_id\\\":\\\"p3_b003\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00007\\\",\\\"text\\\":\\\"四、贷款期限及还款方式\\\",\\\"title\\\":\\\"四、贷款期限及还款方式\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":3,\\\"block_id\\\":\\\"p3_b007\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00008\\\",\\\"text\\\":\\\"五、授信用途\\\",\\\"title\\\":\\\"五、授信用途\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":3,\\\"block_id\\\":\\\"p3_b009\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00009\\\",\\\"text\\\":\\\"六、担保费收取\\\",\\\"title\\\":\\\"六、担保费收取\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":3,\\\"block_id\\\":\\\"p3_b011\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00010\\\",\\\"text\\\":\\\"七、反担保措施\\\",\\\"title\\\":\\\"七、反担保措施\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":3,\\\"block_id\\\":\\\"p3_b013\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00011\\\",\\\"text\\\":\\\"八、风险缓释措施\\\",\\\"title\\\":\\\"八、风险缓释措施\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"cn_top\\\",\\\"page_no\\\":4,\\\"block_id\\\":\\\"p4_b002\\\",\\\"content_role\\\":\\\"main_body\\\"},{\\\"candidate_id\\\":\\\"h_00012\\\",\\\"text\\\":\\\"附件：1.党组织领办合作社名单\\\",\\\"title\\\":\\\"附件1.党组织领办合作社名单\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"appendix\\\",\\\"page_no\\\":5,\\\"block_id\\\":\\\"p5_b002\\\",\\\"content_role\\\":\\\"appendix\\\"},{\\\"candidate_id\\\":\\\"h_00013\\\",\\\"text\\\":\\\"2. 客户推荐函\\\",\\\"title\\\":\\\"2.客户推荐函\\\",\\\"level_guess\\\":3,\\\"numbering_type\\\":\\\"num_dot\\\",\\\"page_no\\\":5,\\\"block_id\\\":\\\"p5_b003\\\",\\\"content_role\\\":\\\"appendix\\\"},{\\\"candidate_id\\\":\\\"h_00014\\\",\\\"text\\\":\\\"3. 资料清单\\\",\\\"title\\\":\\\"3.资料清单\\\",\\\"level_guess\\\":3,\\\"numbering_type\\\":\\\"num_dot\\\",\\\"page_no\\\":5,\\\"block_id\\\":\\\"p5_b004\\\",\\\"content_role\\\":\\\"appendix\\\"},{\\\"candidate_id\\\":\\\"h_00015\\\",\\\"text\\\":\\\"附件 2\\\",\\\"title\\\":\\\"附件 2\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"appendix\\\",\\\"page_no\\\":9,\\\"block_id\\\":\\\"p9_b001\\\",\\\"content_role\\\":\\\"appendix\\\"},{\\\"candidate_id\\\":\\\"h_00016\\\",\\\"text\\\":\\\"客户推荐函\\\",\\\"title\\\":\\\"客户推荐函\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"layout_title\\\",\\\"page_no\\\":9,\\\"block_id\\\":\\\"p9_b002\\\",\\\"content_role\\\":\\\"appendix\\\"},{\\\"candidate_id\\\":\\\"h_00017\\\",\\\"text\\\":\\\"附件 3\\\",\\\"title\\\":\\\"附件 3\\\",\\\"level_guess\\\":1,\\\"numbering_type\\\":\\\"appendix\\\",\\\"page_no\\\":10,\\\"block_id\\\":\\\"p10_b001\\\",\\\"content_role\\\":\\\"appendix\\\"}]\\n\\n## 文档窗口文本\\n[p1_b000][p1][title] %E5%8D%9A%E5%85%B4%E5%8E%BF%E6%95%B0%E5%AD%97%E8%AE%BE%E6%96%BD%E6%B8%94%E4%B8%9A%E4%BA%A7%E4%B8%9A%E5%9B%AD%E6%8B%85%E4%BF%9D%E6%9C%8D%E5%8A%A1%E6%96%B9%E6%A1%88\\n[p1_b001][p1][title] 山东省农业发展信贷担保有限责任公司 关于印发《博兴县数字设施渔业产业园 担保服务方案》的通知\\n[p1_b002][p1][text] 滨州管理中心:\\n[p1_b003][p1][text] 《博兴县数字设施渔业产业园担保服务方案》已于2024年3月22日经公司评审会审批通过，并于即日起施行，现予印发，请认真抓好贯彻落实。\\n[p1_b004][p1][text] 山东省农业发展信贷担保有限责任公司\\n[p1_b005][p1][text] 2024年3月27日\\n[p2_b001][p2][title] 博兴县数字设施渔业产业园担保服务方案\\n[p2_b002][p2][title] 一、服务对象\\n[p2_b003][p2][text] 博兴县政府部门推荐的与博兴县千乘文旅体育产业集团有限公司（以下简称千乘文旅）签订购买协议的村党支部领办合作社（附件1）。\\n[p2_b004][p2][title] 二、准入条件\\n[p2_b005][p2][text] 1. 村党支部领办合作社须持有效营业执照，章程规范、合规，财务制度健全，资信良好；\\n2.有固定的生产经营场所，能够正常开展生产经营活动；\\n3.村党支部领办合作社理事长年龄加贷款期限不得超65岁，村党支部领办合作社信用状况良好，无重大涉诉未执行终结案件、无失信或被执行未履行信息；\\n4.村党支部领办合作社贷款及对外担保五级分类无“正常”之外的状态、最近24个月内不存在连续90天以上或累计6次以上的逾期记录；\\n5.须明确村集体占股或参与收益分配;\\n6. 博兴县乡村振兴局出具推荐名单及县委常委会或县政府会议纪要（会议纪要中需明确养殖池确权及确权后资产质押等相关事项）;\\n7.养殖车间主体建设完成后，客户与千乘文旅签订《购买协\\n[p3_b001][p3][text] 议》，明确固定资产建设、确权事宜；\\n[p3_b002][p3][text] 8. 博兴县数字设施渔业产业园满足防疫、环保、用地合规等条件；\\n9. 滨州管理中心利用遥感技术做好虾池、鱼池圈地工作。\\n[p3_b003][p3][title] 三、额度测算\\n[p3_b004][p3][text] 总授信额度为 8500 万元。单户担保额度：10 万元（含）至 300 万元（含）。客户授信前资产负债率不超过 50%，授信后资产负债率不超过 70%。\\n[p3_b005][p3][text] 单户测算额度=(虾池数量×单个虾池建设成本+鱼池数量×单个鱼池建设成本)×80%-同类存量贷款。建设成本单个虾池17万元、单个鱼池成本12万元。\\n[p3_b006][p3][text] 虾池、鱼池建设规模按照推荐函中建设规模确定；自筹资金需事先由博兴县乡村振兴局或合作银行核实确认。\\n[p3_b007][p3][title] 四、贷款期限及还款方式\\n[p3_b008][p3][text] 贷款期限最长不超过8年，不可循环使用。按照投资回收期采取分期还款方式。\\n[p3_b009][p3][title] 五、授信用途\\n[p3_b010][p3][text] 贷款用途仅限用于虾池、鱼池及配套设施建设。\\n[p3_b011][p3][title] 六、担保费收取\\n[p3_b012][p3][text] 按照贷款金额的 0.75%/年收取。\\n[p3_b013][p3][title] 七、反担保措施\\n[p3_b014][p3][text] 由村党支部领办合作社理事长个人提供连带责任反担保，如\\n[p4_b001][p4][text] 遇理事长变更，继任理事长个人须提供连带责任反担保，博兴县乡村振兴局负责协调办理反担保人变更手续。\\n[p4_b002][p4][title] 八、风险缓释措施\\n[p4_b003][p4][text] 1. 千乘文旅提供50%连带责任反担保。若推荐的客户未能按照合作银行借款合同约定按时偿还贷款本息的，双方共同追偿；追偿的款项无法全部清偿银行贷款导致山东农担发生代偿后，山东农担向千乘文旅发送代偿通知，千乘文旅收到代偿通知后15日内，按照山东农担代偿本息及相关费用偿还代偿款；\\n[p4_b004][p4][text] 千乘文旅签署《反担保保证函》，为推荐的客户向山东农担提供连带责任反担保，不再逐笔签署《反担保保证函》；\\n[p4_b005][p4][text] 2. 数字设施渔业产业园建成后，由创新发展部对接产业园智慧系统。对接后，保后管理部可对产业园运营及养殖情况进行实时保后；\\n3. 数字设施渔业产业园项目纳入“鲁担惠农兴博共富贷”内，博兴县按照 40% 的比例对辖区内的“鲁担惠农兴博共富贷”项目发生的代偿进行最终分担，并统筹安排财政资金 500 万元，专项用于支付博兴县分担的农业信贷担保贷款相关代偿；\\n4. 数字设施渔业产业园项目建成项目验收合格后，由博兴县乡村振兴局、千乘文旅配合村党支部领办合作社在“滨州市农村集体资产管理系统”（省级农村集体“三资”监管平台市级管理系统）进行确权，并出具《资产卡片》。合作银行通过博兴县不动产登记中心办理抵押手续；\\n[p5_b001][p5][text] 5.省级农村集体“三资”监管平台对接后，管理中心对村党支部领办合作社资产进行监管。\\n[p5_b002][p5][text] 附件：1.党组织领办合作社名单\\n[p5_b003][p5][text] 2. 客户推荐函\\n[p5_b004][p5][text] 3. 资料清单\\n[p9_b001][p9][text] 附件 2\\n[p9_b002][p9][title] 客户推荐函\\n[p9_b003][p9][text] 山东省农业发展信贷担保有限责任公司：\\n[p9_b004][p9][text] 现推荐以下村党组织领办合作社给贵司，我单位确认表中均为党组织领办合作社，且具有虾池、鱼池建设贷款需求，望贵单位予以提供金融服务为盼。\\n[p9_b005][p9][text] 推荐单位（公章）：\\n[p9_b006][p9][text] 年 月 日\\n[p10_b001][p10][title] 附件 3\\n[p10_b002][p10][text] 抄送：公司领导、各部室，各管理中心、办事处，有关合作银行。\\n\",\"role\":\"user\"}],\"model\":\"qwen2.5-32b\",\"response_format\":{\"type\":\"json_object\"},\"stream\":false,\"temperature\":0}",
  "content_type": "application/json",
  "headers": {
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Content-Length": "15596",
    "Content-Type": "application/json",
    "Host": "124.128.251.51:21081",
    "User-Agent": "Go-http-client/1.1"
  },
  "method": "POST",
  "path": "/v1/chat/completions",
  "query_string": ""
}
```

**响应：**

```json
{
  "body_chars": 3500,
  "body_text": "{\"id\":\"chatcmpl-26b6ac9fda8d4bb48c7c0904449cfd43\",\"object\":\"chat.completion\",\"created\":1779719760,\"model\":\"qwen2.5-32b\",\"choices\":[{\"index\":0,\"message\":{\"role\":\"assistant\",\"content\":\"{\\n  \\\"sections\\\": [\\n    {\\n      \\\"candidate_id\\\": \\\"h_00001\\\",\\n      \\\"level\\\": 1,\\n      \\\"title\\\": \\\"山东省农业发展信贷担保有限责任公司 关于印发《博兴县数字设施渔业产业园 担保服务方案》的通知\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"document_meta\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00002\\\",\\n      \\\"level\\\": 1,\\n      \\\"title\\\": \\\"博兴县数字设施渔业产业园担保服务方案\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"document_meta\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00003\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"一、服务对象\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"service_object\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00004\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"二、准入条件\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"admission_requirement\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00006\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"三、额度测算\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"credit_limit\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00007\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"四、贷款期限及还款方式\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"guarantee_term\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00008\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"五、授信用途\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"credit_purpose\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00009\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"六、担保费收取\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"fee_rate\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00010\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"七、反担保措施\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"counter_guarantee\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00011\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"八、风险缓释措施\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"risk_mitigation\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00012\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"附件1.党组织领办合作社名单\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"appendix\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00016\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"客户推荐函\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"appendix\\\",\\n      \\\"confidence\\\": 0.95\\n    },\\n    {\\n      \\\"candidate_id\\\": \\\"h_00017\\\",\\n      \\\"level\\\": 2,\\n      \\\"title\\\": \\\"附件 3\\\",\\n      \\\"title_source\\\": \\\"explicit\\\",\\n      \\\"section_type\\\": \\\"appendix\\\",\\n      \\\"confidence\\\": 0.95\\n    }\\n  ],\\n  \\\"warnings\\\": []\\n}\",\"refusal\":null,\"annotations\":null,\"audio\":null,\"function_call\":null,\"tool_calls\":[],\"reasoning_content\":null},\"logprobs\":null,\"finish_reason\":\"stop\",\"stop_reason\":null,\"token_ids\":null}],\"service_tier\":null,\"system_fingerprint\":null,\"usage\":{\"prompt_tokens\":4194,\"total_tokens\":5062,\"completion_tokens\":868,\"prompt_tokens_details\":null},\"prompt_logprobs\":null,\"prompt_token_ids\":null,\"kv_transfer_params\":null}",
  "error": "",
  "headers": {},
  "status_code": 200
}
```

**分析：**

- 模型返回 200 但 content 是 `{\n  mpt_tokens_details":null}` — vLLM 内部元数据，不是有效 JSON
- 不是 max_tokens 截断（那会返回不完整的 JSON，而不是元数据）
- 可能原因：prompt 过长（15KB）、模型状态异常、或 vLLM 调度问题
- vLLM 健康检查显示 `NO_AVAILABLE_INSTANCE` 错误

**修复（commit c39a5d3）：** 添加 `max_tokens=4000`。但实际根因可能是模型本身的问题。

#### 问题 3b: 脚本 heading 检测误判编号条款为标题

LLM 失败后，回退到 `_catalog_from_heading_candidates()` 脚本生成 catalog。

**问题正则：**

```python
# catalog_chunker.py line 122
("num_dot", re.compile(r"^([0-9]{1,2}[.．、])\s*(.{1,100})$"), 3)
```

这个正则把编号条款 `1. xxx；` `2. xxx；` 匹配为 level 3 标题。

**误判结果：**

```
HEADING [num_dot] L3: 1. 村党支部领办合作社须持有效营业执照...  ← 应该是内容
HEADING [num_dot] L3: 2.有固定的生产经营场所...               ← 应该是内容
...
```

被误判的 items 在后续处理中被当作 "title-only leaf" 丢弃：

```
catalog_title_only_leaf_dropped:2.有固定的生产经营场所...
catalog_title_only_leaf_dropped:3.村党支部领办合作社理事长年龄...
catalog_title_only_leaf_dropped:4.村党支部领办合作社贷款...
catalog_title_only_leaf_dropped:5.须明确村集体占股...
catalog_title_only_leaf_dropped:6.博兴县乡村振兴局出具推荐名单...
catalog_title_only_leaf_dropped:8.博兴县数字设施渔业产业园...
catalog_title_only_leaf_dropped:9.滨州管理中心利用遥感技术...
```

**修复（commit d7cc62c）：** 正则增加尾部标点排除：

```python
("num_dot", re.compile(r"^([0-9]{1,2}[.．、])\s*(.{1,100}[^；。,，：:、;.,])$"), 3)
```

### Step 4: 最终 chunks — 修复后应正常

修复后，catalog 要么 LLM 成功返回正确目录，要么脚本 heading 检测不再误判编号条款。

## 中间产物验证

容器内路径：`/app/data/parsed/2058898375458750466/2058898718280187906/file_2058898718280187906_2/process/`

| 文件                           | 内容                           |
| ------------------------------ | ------------------------------ |
| `01_middle_document.json`    | OCR 解析结果（block 结构正确） |
| `02_catalog_chunking.json`   | catalog + chunks（问题所在）   |
| `03_sections.json`           | 章节划分                       |
| `04_section_summaries.json`  | 章节摘要                       |
| `05_profile_extraction.json` | 结构化提取                     |

`02_catalog_chunking.json` 中的关键数据：

- `catalog_source: "script_heading_candidates"` — 说明 LLM 失败，用了脚本
- `warnings` 包含 17 条 `catalog_title_only_leaf_dropped` — items 被丢弃
- `mapped_coverage_low:0.0000` — 脚本 catalog 覆盖率为 0

## 三个修复 Commit

| Commit      | 文件                   | 修复内容                           |
| ----------- | ---------------------- | ---------------------------------- |
| `14d6019` | `document_parser.py` | list block 嵌套结构提取            |
| `d7cc62c` | `catalog_chunker.py` | heading 检测正则排除编号条款       |
| `c39a5d3` | `catalog_chunker.py` | catalog LLM 调用加 max_tokens=4000 |

## 待解决问题

**LLM catalog 为什么返回垃圾输出？**

需要排查：

1. qwen2.5-32b 模型是否正常（vLLM 显示 NO_AVAILABLE_INSTANCE）
2. 15KB 的 prompt 是否超出模型上下文窗口
3. 是否需要换模型（qwen3.5-27b-zf？）

## 验证方法

部署后重新解析博兴县文件，检查：

1. `02_catalog_chunking.json` 的 `catalog_source` 是否为 `llm_catalog`（不再是 script）
2. `warnings` 中是否还有 `catalog_title_only_leaf_dropped`
3. chunks 中 "准入条件" section 是否包含完整的 9 个 items
