package com.ludan.app.controller.openapi;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.model.PageResult;
import com.central.common.model.Result;
import com.ludan.app.dto.openapi.*;
import com.ludan.app.dto.req.KbCreateReqDTO;
import com.ludan.app.dto.req.KbUpdateReqDTO;
import com.ludan.app.entity.KbFileNode;
import com.ludan.app.entity.KbQaPair;
import com.ludan.app.service.*;
import com.ludan.common.interf.management.annotation.Open;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@RestController
@RequestMapping("/open-api/v1")
@Api(tags = "开放API（外部服务调用）")
@RequiredArgsConstructor
public class OpenApiController {

    private static final DateTimeFormatter DTF = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final Set<String> VALID_TYPES =
            new HashSet<>(Arrays.asList("business_plan", "governance_rule", "project_doc", "sql_analytics"));
    private static final Set<String> VALID_VISIBILITIES =
            new HashSet<>(Arrays.asList("public", "private"));

    private final KbKnowledgeBaseService kbService;
    private final KbFileNodeService fileNodeService;
    private final KbQaPairService qaPairService;
    private final KbChatService chatService;
    private final KbParseTaskQueryService parseTaskQueryService;
    private final RetrievalEngineClient retrievalEngineClient;

    // ======================== 知识库（5） ========================

    @ApiOperation("创建知识库")
    @PostMapping("/knowledge-bases")
    public Result<KbResponse> createKb(@RequestBody KbCreateRequest req) {
        KbCreateReqDTO dto = new KbCreateReqDTO();
        dto.setName(req.getName());
        dto.setDescription(req.getDescription());
        dto.setType(validType(req.getType()));
        dto.setVisibility(validVisibility(req.getVisibility()));
        dto.setFileAuditEnabled(0);
        dto.setQaAuditEnabled(0);
        com.ludan.app.entity.KbKnowledgeBase kb = kbService.createKb(dto);
        return Result.succeed(toKbResponse(kb), "创建成功");
    }

    @ApiOperation("删除知识库（含级联删除文件、QA、索引）")
    @DeleteMapping("/knowledge-bases/{kbId}")
    public Result<Void> deleteKb(@PathVariable Long kbId) {
        List<KbFileNode> tree = fileNodeService.getFileTree(kbId);
        if (tree != null) {
            for (KbFileNode n : tree) {
                try {
                    fileNodeService.deleteNode(kbId, n.getId());
                } catch (RuntimeException e) {
                    log.warn("级联删文件失败 kbId={} nodeId={}: {}", kbId, n.getId(), e.getMessage());
                }
            }
        }
        Map<String, Object> params = new HashMap<>();
        params.put("kbId", kbId);
        params.put("pageSize", 100000);
        Page<KbQaPair> qas = qaPairService.findList(params);
        if (qas != null && !qas.getRecords().isEmpty()) {
            List<Long> qaIds = qas.getRecords().stream()
                    .map(KbQaPair::getId).collect(Collectors.toList());
            qaPairService.removeByIds(qaIds);
            try {
                retrievalEngineClient.rebuildQaIndex(kbId);
            } catch (Exception e) {
                log.warn("KB删除后清空QA索引失败 kbId={}: {}", kbId, e.getMessage());
            }
        }
        kbService.removeById(kbId);
        return Result.succeed(null, "删除成功");
    }

    @ApiOperation("知识库列表")
    @GetMapping("/knowledge-bases")
    public PageResult<KbResponse> listKbs(@RequestParam Map<String, Object> params) {
        Page<com.ludan.app.dto.resp.KbListRespDTO> page = kbService.findList(params);
        List<KbResponse> list = new ArrayList<>();
        if (page != null && page.getRecords() != null) {
            for (com.ludan.app.dto.resp.KbListRespDTO d : page.getRecords()) {
                KbResponse r = new KbResponse();
                r.setId(d.getId());
                r.setName(d.getName());
                r.setType(d.getType());
                r.setVisibility(d.getVisibility());
                if (d.getCreateTime() != null) {
                    r.setCreateTime(DTF.format(
                            d.getCreateTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime()));
                }
                list.add(r);
            }
        }
        return PageResult.<KbResponse>builder()
                .data(list).code(0).count(page != null ? page.getTotal() : 0).build();
    }

    @ApiOperation("知识库详情")
    @GetMapping("/knowledge-bases/{kbId}")
    public Result<KbResponse> getKb(@PathVariable Long kbId) {
        com.ludan.app.dto.resp.KbListRespDTO d = kbService.getKbDetail(kbId);
        if (d == null) {
            return Result.failed("知识库不存在");
        }
        return Result.succeed(toDetailResponse(d), "查询成功");
    }

    @ApiOperation("更新知识库")
    @PutMapping("/knowledge-bases/{kbId}")
    public Result<Void> updateKb(@PathVariable Long kbId, @RequestBody KbCreateRequest req) {
        KbUpdateReqDTO dto = new KbUpdateReqDTO();
        dto.setName(req.getName());
        dto.setDescription(req.getDescription());
        kbService.updateKb(kbId, dto);
        return Result.succeed(null, "更新成功");
    }

    // ======================== 文档/文件（3） ========================

    @ApiOperation("批量创建文件（自动触发解析）")
    @PostMapping("/knowledge-bases/{kbId}/documents")
    public Result<List<DocumentResponse>> createDocuments(@PathVariable Long kbId,
                                                          @RequestBody DocumentCreateRequest req) {
        List<DocumentResponse> results = new ArrayList<>();
        for (DocumentCreateRequest.FileItem file : req.getFiles()) {
            try {
                KbFileNode node = fileNodeService.createFileNode(
                        kbId, req.getParentId(),
                        file.getFileId(), file.getFileName(),
                        file.getOriginalName() != null ? file.getOriginalName() : file.getFileName(),
                        file.getFileSize(), file.getMimeType(), file.getFileExt(),
                        null, null, null);
                DocumentResponse resp = new DocumentResponse();
                resp.setFileId(file.getFileId());
                resp.setFileName(file.getFileName());
                resp.setStatus("SUCCESS");
                resp.setFileNodeId(node.getId());
                results.add(resp);
            } catch (RuntimeException e) {
                log.warn("文件入库失败: kbId={}, fileId={}, msg={}", kbId, file.getFileId(), e.getMessage());
                DocumentResponse resp = new DocumentResponse();
                resp.setFileId(file.getFileId());
                resp.setFileName(file.getFileName());
                resp.setStatus("FAILED");
                resp.setMessage(e.getMessage());
                results.add(resp);
            }
        }
        return Result.succeed(results, "上传完成");
    }

    @ApiOperation("批量删除文件")
    @DeleteMapping("/knowledge-bases/{kbId}/documents")
    public Result<BatchDeleteResponse> deleteDocuments(@PathVariable Long kbId,
                                                        @RequestBody BatchDeleteRequest req) {
        int count = 0;
        for (Long fileNodeId : req.getIds()) {
            try {
                KbFileNode node = fileNodeService.getById(fileNodeId);
                if (node == null || !kbId.equals(node.getKbId())) {
                    log.warn("删除文件跳过：fileNodeId={} 不属于 kbId={}", fileNodeId, kbId);
                    continue;
                }
                fileNodeService.deleteNode(kbId, fileNodeId);
                count++;
            } catch (RuntimeException e) {
                log.warn("删除文件失败: kbId={}, fileNodeId={}, msg={}", kbId, fileNodeId, e.getMessage());
            }
        }
        BatchDeleteResponse resp = new BatchDeleteResponse();
        resp.setDeletedCount(count);
        return Result.succeed(resp, "删除完成");
    }

    @ApiOperation("重新解析")
    @PostMapping("/knowledge-bases/{kbId}/documents/{fileId}/reparse")
    public Result<Void> reparseDocument(@PathVariable Long kbId, @PathVariable Long fileId) {
        fileNodeService.triggerReparse(kbId, fileId);
        return Result.succeed(null, "已触发重解析");
    }

    // ======================== QA 对（5） ========================

    @ApiOperation("创建QA对")
    @PostMapping("/knowledge-bases/{kbId}/qa-pairs")
    public Result<QaResponse> createQa(@PathVariable Long kbId, @RequestBody QaRequest req) {
        KbQaPair qa = qaPairService.createQa(kbId, req.getQuestion(), req.getAnswer());
        return Result.succeed(toQaResponse(qa), "创建成功");
    }

    @ApiOperation("更新QA对")
    @PutMapping("/knowledge-bases/{kbId}/qa-pairs/{qaId}")
    public Result<Void> updateQa(@PathVariable Long kbId, @PathVariable Long qaId,
                                  @RequestBody QaRequest req) {
        KbQaPair qa = qaPairService.getById(qaId);
        if (qa == null) {
            return Result.failed("问答对不存在");
        }
        if (!kbId.equals(qa.getKbId())) {
            return Result.failed("问答对不属于该知识库");
        }
        qaPairService.updateQa(qaId, req.getQuestion(), req.getAnswer());
        return Result.succeed(null, "更新成功");
    }

    @ApiOperation("批量删除QA对")
    @DeleteMapping("/knowledge-bases/{kbId}/qa-pairs")
    public Result<BatchDeleteResponse> deleteQas(@PathVariable Long kbId,
                                                  @RequestBody BatchDeleteRequest req) {
        int count = qaPairService.deleteQas(kbId, req.getIds());
        BatchDeleteResponse resp = new BatchDeleteResponse();
        resp.setDeletedCount(count);
        return Result.succeed(resp, "删除完成");
    }

    @ApiOperation("QA列表")
    @GetMapping("/knowledge-bases/{kbId}/qa-pairs")
    public PageResult<QaResponse> listQas(@PathVariable Long kbId,
                                           @RequestParam Map<String, Object> params) {
        params.put("kbId", kbId);
        Page<KbQaPair> page = qaPairService.findList(params);
        List<QaResponse> list = new ArrayList<>();
        if (page != null && page.getRecords() != null) {
            for (KbQaPair q : page.getRecords()) {
                list.add(toQaResponse(q));
            }
        }
        return PageResult.<QaResponse>builder()
                .data(list).code(0).count(page != null ? page.getTotal() : 0).build();
    }

    @ApiOperation("CSV批量导入QA")
    @PostMapping("/knowledge-bases/{kbId}/qa-pairs/import")
    public Result<Map<String, Object>> importQas(@PathVariable Long kbId,
                                                  @RequestParam("file") MultipartFile file) {
        int count = qaPairService.importCsv(kbId, file);
        Map<String, Object> data = new HashMap<>();
        data.put("count", count);
        return Result.succeed(data, "导入成功，共 " + count + " 条");
    }

    // ======================== 检索与任务（3） ========================

    @ApiOperation("多库检索")
    @PostMapping("/retrieval")
    public Result<List<Map<String, Object>>> retrieval(@RequestBody Map<String, Object> body) {
        @SuppressWarnings("unchecked")
        List<Long> kbIds = (List<Long>) body.get("kbIds");
        String query = (String) body.get("query");
        Integer topK = body.get("topK") != null ? ((Number) body.get("topK")).intValue() : null;
        @SuppressWarnings("unchecked")
        Map<String, Object> options = body.get("options") instanceof Map
                ? new HashMap<>((Map<String, Object>) body.get("options")) : new HashMap<>();
        if (body.containsKey("graph")) {
            options.put("graph", Boolean.valueOf(String.valueOf(body.get("graph"))));
        }
        return Result.succeed(chatService.retrievalTestMulti(kbIds, query, topK, options), "检索成功");
    }

    @ApiOperation("LLM上下文检索")
    @PostMapping("/retrieval/llm-context")
    @Open(url = "/api/v1/kb/retrieval-test", name = "多库检索", serviceCode = "LD000262", version = "v1.0",
            urlPrefix = "/api-knowledge", description = "多库检索", limit = 3000, timeout = 30,
            token = false, encrypt = true)
    public Result<Map<String, Object>> retrievalLlmContext(@RequestBody Map<String, Object> body) {
        try {

            List<Long> kbIds = (List<Long>) body.get("kbIds");
            if (kbIds == null || kbIds.isEmpty()) {
                return Result.failed("kbIds 不能为空");
            }
            String query = body.get("query") != null ? body.get("query").toString().trim() : "";
            if (query.isEmpty()) {
                return Result.failed("query 不能为空");
            }
            Integer topK = body.get("topK") != null ? ((Number) body.get("topK")).intValue() : 5;
            if (topK <= 0 || topK > 100) {
                return Result.failed("topK 取值范围为 1-100");
            }

            Map<String, Object> options = body.get("options") instanceof Map
                    ? new HashMap<>((Map<String, Object>) body.get("options")) : new HashMap<>();
            if (body.get("fileNodeIds") instanceof List) {
                options.put("fileNodeIds", body.get("fileNodeIds"));
            }
            if (body.containsKey("graph")) {
                options.put("graph", Boolean.valueOf(String.valueOf(body.get("graph"))));
            }

            String llmContext = retrievalEngineClient.retrieveLlmContext(kbIds, query, topK, options);
            Map<String, Object> data = new HashMap<>();
            data.put("llmContext", llmContext != null ? llmContext : "");
            return Result.succeed(data, "成功");
        } catch (NumberFormatException e) {
            return Result.failed("参数格式不正确");
        } catch (RuntimeException e) {
            log.warn("LLM上下文检索失败: msg={}", e.getMessage());
            return Result.failed(e.getMessage() != null ? e.getMessage() : "检索失败");
        }
    }

    @ApiOperation("解析任务列表")
    @GetMapping("/knowledge-bases/{kbId}/parse-tasks")
    public Result<List<Map<String, Object>>> parseTasks(@PathVariable Long kbId,
                                                         @RequestParam(value = "status", required = false) String status,
                                                         @RequestParam(value = "fileNodeId", required = false) Long fileNodeId,
                                                         @RequestParam(value = "limit", required = false) Integer limit) {
        return Result.succeed(parseTaskQueryService.listParseTasks(status, kbId, fileNodeId, limit), "查询成功");
    }

    @ApiOperation("QA全部索引")
    @PostMapping("/knowledge-bases/{kbId}/qa-pairs/reindex")
    public Result<Map<String, Object>> reindexQas(@PathVariable Long kbId) {
        try {
            String indexGeneration = retrievalEngineClient.rebuildQaIndex(kbId);
            Map<String, Object> data = new HashMap<>();
            data.put("indexGeneration", indexGeneration);
            return Result.succeed(data, "已触发 QA 全部索引");
        } catch (RuntimeException e) {
            log.warn("QA 全部索引失败: kbId={}, msg={}", kbId, e.getMessage());
            return Result.failed(e.getMessage());
        }
    }

    // ======================== 私有映射方法 ========================

    private KbResponse toKbResponse(com.ludan.app.entity.KbKnowledgeBase kb) {
        KbResponse resp = new KbResponse();
        resp.setId(kb.getId());
        resp.setName(kb.getName());
        resp.setType(kb.getType());
        resp.setVisibility(kb.getVisibility());
        if (kb.getCreateTime() != null) {
            resp.setCreateTime(DTF.format(
                    kb.getCreateTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime()));
        }
        return resp;
    }

    private KbResponse toDetailResponse(com.ludan.app.dto.resp.KbListRespDTO d) {
        KbResponse resp = new KbResponse();
        resp.setId(d.getId());
        resp.setName(d.getName());
        resp.setType(d.getType());
        resp.setVisibility(d.getVisibility());
        if (d.getCreateTime() != null) {
            resp.setCreateTime(DTF.format(
                    d.getCreateTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime()));
        }
        return resp;
    }

    private QaResponse toQaResponse(KbQaPair qa) {
        QaResponse resp = new QaResponse();
        resp.setId(qa.getId());
        resp.setQuestion(qa.getQuestion());
        resp.setAnswer(qa.getAnswer());
        resp.setAuditStatus(qa.getAuditStatus());
        if (qa.getCreateTime() != null) {
            resp.setCreateTime(DTF.format(
                    qa.getCreateTime().toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime()));
        }
        return resp;
    }

    private String validType(String type) {
        return type != null && VALID_TYPES.contains(type) ? type : "business_plan";
    }

    private String validVisibility(String visibility) {
        return visibility != null && VALID_VISIBILITIES.contains(visibility) ? visibility : "public";
    }
}
